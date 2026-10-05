#!/usr/bin/env python3
"""Render a Deal Desk script to MP3 plus a JSON of per-line timestamps.

    python pipeline/render.py scripts/episode-12-precedent-transactions.md
    python pipeline/render.py <script> --engine gemini --reserve 20   # backfill: Gemini only
    python pipeline/render.py <script> --engine kokoro                # the free fallback
    python pipeline/render.py <script> --dry-run                      # show the chunks and cost

Gemini TTS (Tier 1) allows 100 requests a day and 10K tokens a minute, so an episode
is rendered in about 3-4 minute chunks (target 520 words, at most 600), each one
multi-speaker request with both voices and the same style instructions every time.
Chunks break only where the speaker changes, preferably at a section start
(interview questions, deal of the day, quiz, sign-off). That's about 4-6 requests
an episode.

Each chunk is checked: its length should match 150 words a minute within 25%, and a
local transcription (pipeline/align.py, faster-whisper) must match the script.
A failing chunk is re-rendered, at most twice. The same transcription gives each
line's start time (forced alignment); if it can't, that chunk's time is split by
character count.

Budget: every call is logged to pipeline/usage.json, by month (dollars, from the
token counts the API returns) and by Pacific-time day (requests). With --engine
auto, an episode that would pass the monthly cap is rendered with Kokoro; with
--engine gemini it stops (exit code 2). Exit code 75: daily limit reached.
"""
import argparse, base64, datetime, hashlib, io, json, os, re, shutil, subprocess, sys, time
import urllib.error, urllib.request
import zoneinfo

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(ROOT, "pipeline")
CACHE_DIR = os.path.join(PIPE, "cache")
MODELS_DIR = os.path.join(PIPE, "models")
LEDGER = os.path.join(PIPE, "usage.json")
OUT_DIR = os.path.join(ROOT, "audio")
API = "https://generativelanguage.googleapis.com/v1beta/interactions"

# --- Voices (approved: Sadaltager / Autonoe, Marco's informative tone) ----------------
MODEL = os.environ.get("TTS_MODEL", "gemini-3.8-flash-tts")
GEMINI = {
    "MARCO": ("Sadaltager", "a senior London mergers and acquisitions banker in his late thirties, presenting a "
                            "finance podcast; slightly lower, deeper register than usual; measured, informative and "
                            "authoritative, like an FT or Bloomberg presenter explaining to a smart listener; "
                            "clear and composed, warm but never sarcastic, smug or casual"),
    "SOFIA": ("Autonoe", "a curious young university student; bright and engaged, conversational"),
}
KOKORO = {"MARCO": ("bm_george", 1.0, "en-gb"), "SOFIA": ("af_heart", 1.05, "en-us")}
RENDERER = "chunks-v2"
VOICE_VERSION = "|".join([MODEL, *GEMINI["MARCO"], *GEMINI["SOFIA"], RENDERER])

# --- Limits (models API, 5 Oct 2026: inputTokenLimit 8192, outputTokenLimit 16384) -----
def prices(today):
    """USD per 1M tokens (standard tier). Prices double on 2027-01-01."""
    return (0.50, 9.00) if today < datetime.date(2027, 1, 1) else (1.00, 18.00)

MONTHLY_CAP_USD = float(os.environ.get("TTS_MONTHLY_CAP_USD", "10.5"))   # raised 5 Oct 2026; Google alert at EUR 10
DAILY_REQUEST_LIMIT = int(os.environ.get("TTS_DAILY_REQUESTS", "100"))   # Tier 1, per Pacific day
TOKENS_PER_MINUTE = 10_000
MAX_REQUESTS_PER_MINUTE = 8
OUT_TOKENS_PER_WORD = 13.5     # measured: ~33 audio tokens per second at ~150 words a minute
IN_TOKENS_PER_REQUEST = 1_600  # text + style + the two voice prompts
WORDS_PER_MINUTE = 150
TARGET_WORDS, MAX_WORDS = 520, 600   # ~3.5 and ~4 minutes; 600 words ≈ 9.7K tokens all in
DURATION_TOLERANCE = 0.25
MIN_ALIGN_COVERAGE = 0.75      # below this the chunk is treated as garbled or skipping text
RETRIES = 2
REALIGN = False                # --realign: recompute line timings from cached audio

SR = 24000
CHUNK_GAP = 0.4                # silence between chunks
LEAD_IN = 0.4
PACIFIC = zoneinfo.ZoneInfo("America/Los_Angeles")

# Lines that open a new section of the episode: the preferred places to cut.
SECTION_STARTS = [r"\bwhat they'll ask you\b", r"^(okay\. )?deal of the day\??$", r"\bnow,? the deal of the day\b",
                  r"\bthe deal of the day\. ", r"^(okay\. )?quiz( time)?\??$", r"^quiz\.", r"^answers\."]


class BudgetExceeded(Exception):
    pass


class RateLimited(Exception):
    pass


# --- Script parsing ------------------------------------------------------------------
def parse_script(path):
    title = hook = None
    lines, cur, body = [], None, False
    for raw in open(path, encoding="utf-8"):
        s = raw.strip()
        if not body:
            if s.startswith("#") and title is None:
                title = s.lstrip("#").strip()
            elif s == "---":
                body = True
            elif s and hook is None and title is not None:
                hook = s
            continue
        m = re.match(r"^\**(MARCO|SOFIA)\**\s*:\s*\**\s*(.*)", s)
        if m:
            cur = {"speaker": m.group(1), "text": m.group(2).strip()}
            lines.append(cur)
        elif cur and s and not s.startswith("#"):
            cur["text"] += " " + s
        elif not s:
            cur = None
    return title, hook, [l for l in lines if clean(l["text"])]


def clean(t):
    t = re.sub(r"\bM\s*(?:&|-and-|and)\s*A\b", "mergers and acquisitions", t)
    t = re.sub(r"\*\*|__|\*|`|#", "", t)
    t = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", t)
    t = t.replace("—", ", ").replace("–", "-")
    t = re.sub(r"\((pause|beat|laughs?)\)", "...", t, flags=re.I)
    t = re.sub(r"<[^>]*>", "", t)
    return t.strip()


def words(text):
    return len(text.split())


# --- Chunking --------------------------------------------------------------------------
def is_section_start(text):
    t = text.strip().lower()
    return any(re.search(p, t) for p in SECTION_STARTS)


def make_chunks(items):
    """Split [(speaker, text)] into chunks of about TARGET_WORDS (never over MAX_WORDS
    unless a single line is longer), cutting only where the speaker changes and
    preferring section starts. Dynamic programming over the allowed cut points."""
    n = len(items)
    w = [words(t) for _, t in items]
    cum = np.concatenate([[0], np.cumsum(w)])
    cut_ok = [True] + [items[i][0] != items[i - 1][0] for i in range(1, n)] + [True]
    cut_cost = [0.0] + [0.0 if is_section_start(items[i][1]) else 0.6 for i in range(1, n)] + [0.0]
    best = [np.inf] * (n + 1); back = [0] * (n + 1); best[0] = 0.0
    for j in range(1, n + 1):
        if not cut_ok[j]:
            continue
        for i in range(j - 1, -1, -1):
            size = cum[j] - cum[i]
            if size > MAX_WORDS and j - i > 1:
                break
            if not cut_ok[i] or best[i] == np.inf:
                continue
            cost = best[i] + 4 * ((size - TARGET_WORDS) / TARGET_WORDS) ** 2 + cut_cost[j]
            if cost < best[j]:
                best[j], back[j] = cost, i
    bounds, j = [], n
    while j > 0:
        bounds.append((back[j], j)); j = back[j]
    return [list(range(a, b)) for a, b in reversed(bounds)]


# --- Usage ledger --------------------------------------------------------------------
def month_key():
    return datetime.date.today().strftime("%Y-%m")


def quota_day():
    return datetime.datetime.now(PACIFIC).date().isoformat()


def load_ledger():
    return json.load(open(LEDGER, encoding="utf-8")) if os.path.exists(LEDGER) else {}


def save_ledger(ledger):
    tmp = LEDGER + ".tmp"
    json.dump(ledger, open(tmp, "w", encoding="utf-8"), indent=2)
    os.replace(tmp, LEDGER)


def month_usage(ledger=None):
    ledger = load_ledger() if ledger is None else ledger
    return ledger.get(month_key(), {"requests": 0, "chars": 0, "input_tokens": 0,
                                    "output_tokens": 0, "audio_seconds": 0.0, "usd": 0.0})


def requests_today(ledger=None):
    ledger = load_ledger() if ledger is None else ledger
    return ledger.get("requests_by_pacific_day", {}).get(quota_day(), 0)


def record_request(chars=0, in_tok=0, out_tok=0, seconds=0.0):
    p_in, p_out = prices(datetime.date.today())
    ledger = load_ledger()
    m = month_usage(ledger)
    m["requests"] += 1
    m["chars"] += chars
    m["input_tokens"] += in_tok
    m["output_tokens"] += out_tok
    m["audio_seconds"] = round(m["audio_seconds"] + seconds, 2)
    m["usd"] = round(m["usd"] + in_tok * p_in / 1e6 + out_tok * p_out / 1e6, 6)
    ledger[month_key()] = m
    days = ledger.setdefault("requests_by_pacific_day", {})
    days[quota_day()] = days.get(quota_day(), 0) + 1
    for d in sorted(days)[:-14]:
        del days[d]
    ledger.pop("requests_by_utc_day", None)
    save_ledger(ledger)


def est_tokens(n_words):
    return IN_TOKENS_PER_REQUEST + n_words * OUT_TOKENS_PER_WORD


def estimate_usd(n_words, requests):
    p_in, p_out = prices(datetime.date.today())
    return requests * IN_TOKENS_PER_REQUEST * p_in / 1e6 + n_words * OUT_TOKENS_PER_WORD * p_out / 1e6


# --- Audio helpers -------------------------------------------------------------------
def decode(data):
    audio, sr = sf.read(io.BytesIO(data), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SR:
        raise RuntimeError(f"unexpected sample rate {sr}")
    return audio


def trim(audio, thresh=0.01, pad=0.06):
    idx = np.where(np.abs(audio) > thresh)[0]
    if not len(idx):
        return audio
    p = int(pad * SR)
    return audio[max(0, idx[0] - p): idx[-1] + p]


def cache_path(*parts, ext=".wav"):
    h = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:24]
    return os.path.join(CACHE_DIR, h + ext)


def chunk_key(items):
    return cache_path("gemini-chunk", VOICE_VERSION, "\x1e".join(f"{s}:{t}" for s, t in items))


def api_key():
    key = os.environ.get("GEMINI_API_KEY")
    env = os.path.join(ROOT, ".env")
    if not key and os.path.exists(env):
        for l in open(env, encoding="utf-8"):
            k, _, v = l.strip().partition("=")
            if k == "GEMINI_API_KEY":
                key = v.strip().strip('"')
    if not key:
        sys.exit("GEMINI_API_KEY not set")
    return key


# --- Gemini --------------------------------------------------------------------------
class Gemini:
    def __init__(self, key, reserve, log=print):
        self.key, self.reserve, self.log = key, reserve, log
        self.recent = []          # (time, estimated tokens) of requests in the last minute
        self.requests = 0

    def _throttle(self, tokens):
        while True:
            now = time.time()
            self.recent = [(t, k) for t, k in self.recent if now - t < 60]
            if (len(self.recent) < MAX_REQUESTS_PER_MINUTE and
                    sum(k for _, k in self.recent) + tokens <= TOKENS_PER_MINUTE):
                break
            time.sleep(max(1.0, 60 - (now - self.recent[0][0]) + 0.5))
        self.recent.append((time.time(), tokens))

    def request(self, body, n_chars, n_words):
        for attempt in range(6):
            if requests_today() >= DAILY_REQUEST_LIMIT - self.reserve:
                raise RateLimited(f"daily request budget used ({requests_today()} of {DAILY_REQUEST_LIMIT}, "
                                  f"{self.reserve} kept in reserve)")
            if month_usage()["usd"] + estimate_usd(n_words, 1) > MONTHLY_CAP_USD:
                raise BudgetExceeded()
            self._throttle(est_tokens(n_words))
            try:
                req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
                                             headers={"x-goog-api-key": self.key, "Content-Type": "application/json"})
                resp = json.load(urllib.request.urlopen(req, timeout=600))
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")[:600]
                if e.code == 429:
                    if "per day" in msg:
                        raise RateLimited(f"Gemini says: {msg[:200]}")
                    wait = min(300, 20 * 2 ** attempt)       # per-minute limit: back off and retry
                    self.log(f"  429, backing off {wait}s"); time.sleep(wait); continue
                record_request()
                if e.code in (500, 502, 503, 504) and attempt < 5:
                    time.sleep(min(240, 15 * 2 ** attempt)); continue
                raise RuntimeError(f"Gemini HTTP {e.code}: {msg}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < 5:
                    self.log(f"  network error ({e}); retrying"); time.sleep(min(240, 15 * 2 ** attempt)); continue
                raise
            u = resp.get("usage", {})
            data = next((c["data"] for st in resp.get("steps", []) for c in (st.get("content") or [])
                         if c.get("data")), None)
            audio = decode(base64.b64decode(data)) if data else np.zeros(0, np.float32)
            record_request(n_chars, u.get("total_input_tokens", 0), u.get("total_output_tokens", 0), len(audio) / SR)
            self.requests += 1
            return audio
        raise RuntimeError("Gemini request failed repeatedly")

    def chunk(self, items):
        """Render one chunk; returns (audio, line starts within it, report)."""
        path = chunk_key(items)
        meta_path = path[:-4] + ".json"
        import align
        if os.path.exists(path) and os.path.exists(meta_path):
            audio = sf.read(path, dtype="float32")[0]
            cached = json.load(open(meta_path, encoding="utf-8"))
            if REALIGN:
                starts, info = align.align(audio, items, 0.06)
                cached["starts"] = starts
                cached["report"].update(info)
                json.dump(cached, open(meta_path, "w", encoding="utf-8"))
            return audio, cached["starts"], cached["report"]
        body = {"model": MODEL,
                "input": [{"type": "user_input", "content": [
                    {"type": "text", "text": t,
                     "annotations": [{"type": "speech_metadata", "speaker": s, "style": GEMINI[s][1]}]}
                    for s, t in items]}],
                "response_format": {"type": "audio"},
                "generation_config": {"speech_config": {"mode": "conversational", "speakers": [
                    {"speaker": "MARCO", "voice": GEMINI["MARCO"][0]},
                    {"speaker": "SOFIA", "voice": GEMINI["SOFIA"][0]}]}}}
        n_words = sum(words(t) for _, t in items)
        n_chars = sum(len(t) for _, t in items)
        expected = n_words / WORDS_PER_MINUTE * 60
        best = None
        for attempt in range(RETRIES + 1):
            audio = trim(self.request(body, n_chars, n_words))
            secs = len(audio) / SR
            starts, info = align.align(audio, items, 0.06)
            ratio = secs / expected if expected else 1
            problems = []
            if abs(ratio - 1) > DURATION_TOLERANCE:
                problems.append(f"length {secs:.0f}s vs about {expected:.0f}s expected")
            if info["coverage"] < MIN_ALIGN_COVERAGE:
                problems.append(f"transcript matches only {info['coverage']:.0%} of the script (garbled or skipped)")
            report = {"words": n_words, "seconds": round(secs, 1), "expected": round(expected, 1),
                      "attempts": attempt + 1, **info, "problems": problems}
            score = len(problems) * 10 + abs(ratio - 1)
            if best is None or score < best[0]:
                best = (score, audio, starts, report)
            if not problems:
                break
            self.log(f"  chunk ({n_words} words) attempt {attempt + 1}: {'; '.join(problems)}"
                     + ("; re-rendering" if attempt < RETRIES else "; keeping the best attempt"))
        _, audio, starts, report = best
        os.makedirs(CACHE_DIR, exist_ok=True)
        sf.write(path, audio, SR)
        json.dump({"starts": starts, "report": report}, open(meta_path, "w", encoding="utf-8"))
        return audio, starts, report


# --- Kokoro --------------------------------------------------------------------------
_kokoro = None

def kokoro_line(speaker, text):
    global _kokoro
    voice, speed, lang = KOKORO[speaker]
    path = cache_path("kokoro", voice, str(speed), text)
    if os.path.exists(path):
        return sf.read(path, dtype="float32")[0]
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(os.path.join(MODELS_DIR, "kokoro-v1.0.onnx"), os.path.join(MODELS_DIR, "voices-v1.0.bin"))
    parts, buf, out = re.split(r"(?<=[.!?])\s+", text), "", []
    for p in parts + [None]:
        if p is not None and len(buf) + len(p) < 400:
            buf = (buf + " " + p).strip(); continue
        if buf:
            audio, sr = _kokoro.create(buf, voice=voice, speed=speed, lang=lang)
            assert sr == SR
            out += [trim(audio.astype(np.float32)), np.zeros(int(SR * 0.18), np.float32)]
        buf = p or ""
    audio = np.concatenate(out[:-1])
    os.makedirs(CACHE_DIR, exist_ok=True)
    sf.write(path, audio, SR)
    return audio


# --- Main ----------------------------------------------------------------------------
def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--engine", choices=["auto", "gemini", "kokoro"], default="auto")
    ap.add_argument("--reserve", type=int, default=0, help="daily requests to leave unused")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--realign", action="store_true", help="recompute line timings from cached chunks (no API calls)")
    args = ap.parse_args()
    global REALIGN
    REALIGN = args.realign

    title, hook, lines = parse_script(args.script)
    m = re.search(r"episode-(\d+)", os.path.basename(args.script))
    ep_id = f"episode-{m.group(1)}" if m else os.path.splitext(os.path.basename(args.script))[0]
    items = [(l["speaker"], clean(l["text"])) for l in lines]
    chunks = make_chunks(items)
    todo = [c for c in chunks if not os.path.exists(chunk_key([items[i] for i in c]))]
    n_words = sum(words(items[i][1]) for c in todo for i in c)
    est = estimate_usd(n_words, len(todo))
    spent, used = month_usage()["usd"], requests_today()
    print(f"{title}\n  {len(lines)} lines, {sum(words(t) for _, t in items)} words in {len(chunks)} chunks "
          f"({', '.join(str(sum(words(items[i][1]) for i in c)) for c in chunks)} words); {len(todo)} to render; "
          f"estimate ${est:.2f}; month ${spent:.2f} of ${MONTHLY_CAP_USD:.2f}; "
          f"requests today {used} of {DAILY_REQUEST_LIMIT}")

    engine = args.engine
    if engine == "auto":
        engine = "gemini" if spent + est <= MONTHLY_CAP_USD else "kokoro"
        if engine == "kokoro":
            print("  monthly cap would be exceeded: using Kokoro")
    elif engine == "gemini" and spent + est > MONTHLY_CAP_USD:
        print("  stopping: this episode would pass the monthly cap (raise TTS_MONTHLY_CAP_USD to continue)")
        return 2
    if args.dry_run:
        for c in chunks:
            first = items[c[0]][1][:60]
            print(f"    lines {c[0]:2d}-{c[-1]:2d}: {sum(words(items[i][1]) for i in c):3d} words, starts: {first!r}")
        print(f"  would render with {engine}")
        return 0

    t0 = time.time()
    gap = np.zeros(int(CHUNK_GAP * SR), np.float32)
    parts, out_lines, reports = [np.zeros(int(LEAD_IN * SR), np.float32)], [], []
    pos = LEAD_IN
    requests = 0
    try:
        if engine == "kokoro":
            for i, (s, t) in enumerate(items):
                clip = kokoro_line(s, t)
                out_lines.append({"i": i, "start": pos, "end": pos + len(clip) / SR})
                parts += [clip, np.zeros(int(0.35 * SR), np.float32)]
                pos += len(clip) / SR + 0.35
        else:
            g = Gemini(api_key(), args.reserve)
            for c in chunks:
                audio, starts, report = g.chunk([items[i] for i in c])
                reports.append(report)
                dur = len(audio) / SR
                for k, i in enumerate(c):
                    end = starts[k + 1] - 0.05 if k + 1 < len(c) else dur - 0.06
                    out_lines.append({"i": i, "start": pos + starts[k], "end": pos + max(end, starts[k] + 0.2)})
                parts += [audio, gap]
                pos += dur + CHUNK_GAP
            requests = g.requests
    except RateLimited as e:
        print(f"  stopped: {e}. Chunks rendered so far are cached; run again after the daily reset.")
        return 75
    except BudgetExceeded:
        if args.engine == "gemini":
            print("  stopped: monthly cap reached mid-render"); return 2
        print("  monthly cap reached mid-render: re-run with --engine kokoro"); return 2

    wav = np.concatenate(parts)
    os.makedirs(args.out_dir, exist_ok=True)
    mp3 = os.path.join(args.out_dir, ep_id + ".mp3")
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp_wav = os.path.join(CACHE_DIR, f"_{ep_id}_full.wav")
    sf.write(tmp_wav, wav, SR)
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", tmp_wav,
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-ac", "1", "-b:a", "96k", mp3],
                   check=True)
    os.remove(tmp_wav)
    meta = {"id": ep_id, "title": title, "hook": hook, "engine": engine,
            "model": MODEL if engine == "gemini" else "kokoro-v1.0",
            "voices": {s: (GEMINI if engine == "gemini" else KOKORO)[s][0] for s in ("MARCO", "SOFIA")},
            "voice_version": VOICE_VERSION if engine == "gemini" else "kokoro",
            "rendered": datetime.datetime.now().isoformat(timespec="seconds"),
            "duration": round(len(wav) / SR, 3), "audio": os.path.basename(mp3),
            "chunks": reports,
            "lines": [{"i": o["i"], "speaker": lines[o["i"]]["speaker"], "text": lines[o["i"]]["text"],
                       "start": round(o["start"], 3), "end": round(o["end"], 3)} for o in out_lines]}
    json.dump(meta, open(os.path.join(args.out_dir, ep_id + ".json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    u = month_usage()
    print(f"  {mp3}: {meta['duration'] / 60:.1f} min, {engine}, {requests} requests this run, "
          f"{time.time() - t0:.0f}s; month ${u['usd']:.3f} of ${MONTHLY_CAP_USD:.2f}; "
          f"requests today {requests_today()}")
    for k, r in enumerate(reports):
        print(f"    chunk {k + 1}: {r['words']} words, {r['seconds']}s (expected {r['expected']}s), "
              f"{r['attempts']} attempt(s), alignment {r['method']} {r['coverage']:.0%}"
              + (f", issues: {r['problems']}" if r["problems"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
