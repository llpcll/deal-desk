#!/usr/bin/env python3
"""Render a Deal Desk script to MP3 plus a JSON of per-line timestamps.

    python pipeline/render.py scripts/episode-12-precedent-transactions.md
    python pipeline/render.py <script> --engine kokoro      # force the free fallback
    python pipeline/render.py <script> --dry-run            # show cost estimate only

Each MARCO/SOFIA line is rendered separately (Gemini TTS, single speaker), so we
know exactly where every line starts and ends. Rendered lines are cached on disk,
so re-running costs nothing for lines that haven't changed.

Spending cap: every Gemini call is logged to pipeline/usage.json by month, using
the token counts the API returns. If this month's spend plus the episode's
estimate would pass MONTHLY_CAP_USD, the whole episode is rendered with Kokoro
instead (we never mix engines inside one episode).
"""
import argparse, base64, datetime, hashlib, io, json, os, re, shutil, subprocess, sys, threading, time
import urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPE = os.path.join(ROOT, "pipeline")
CACHE_DIR = os.path.join(PIPE, "cache")
MODELS_DIR = os.path.join(PIPE, "models")
LEDGER = os.path.join(PIPE, "usage.json")
OUT_DIR = os.path.join(ROOT, "audio")

# --- Voices (approved: sample C2) -------------------------------------------
MODEL = os.environ.get("TTS_MODEL", "gemini-3.8-flash-tts")
GEMINI = {
    "MARCO": ("Sadaltager", "a senior London mergers and acquisitions banker in his late thirties, presenting a "
                            "finance podcast; slightly lower, deeper register than usual; measured, informative and "
                            "authoritative, like an FT or Bloomberg presenter explaining to a smart listener; "
                            "clear and composed, warm but never sarcastic, smug or casual"),
    "SOFIA": ("Autonoe", "a curious young university student; bright and engaged, conversational"),
}
KOKORO = {"MARCO": ("bm_george", 1.0, "en-gb"), "SOFIA": ("af_heart", 1.05, "en-us")}

# --- Budget ------------------------------------------------------------------
# USD per 1M tokens (standard tier). Prices double on 2027-01-01.
def prices(today):
    return (0.50, 9.00) if today < datetime.date(2027, 1, 1) else (1.00, 18.00)
# $8 is a little under EUR 8 while the euro is worth more than the dollar.
MONTHLY_CAP_USD = float(os.environ.get("TTS_MONTHLY_CAP_USD", "8.0"))
# Docs say 25 audio tokens/sec; episode 12 measured 2.25 output tokens per character
# of text (about 264 input tokens per request). Both rounded up so estimates run high.
EST_OUTPUT_TOKENS_PER_CHAR = 2.5
EST_INPUT_TOKENS = 300

SR = 24000
GAP_BETWEEN_LINES = 0.35    # seconds of silence between turns
LEAD_IN = 0.4
WORKERS = 4


class BudgetExceeded(Exception):
    pass


# --- Script parsing ------------------------------------------------------------
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
    return t.strip()


# --- Usage ledger ---------------------------------------------------------------
_ledger_lock = threading.Lock()

def month_key():
    return datetime.date.today().strftime("%Y-%m")

def load_ledger():
    if os.path.exists(LEDGER):
        return json.load(open(LEDGER, encoding="utf-8"))
    return {}

def month_usage(ledger=None):
    ledger = load_ledger() if ledger is None else ledger
    return ledger.get(month_key(), {"requests": 0, "chars": 0, "input_tokens": 0,
                                    "output_tokens": 0, "audio_seconds": 0.0, "usd": 0.0})

def record_usage(chars, in_tok, out_tok, seconds):
    p_in, p_out = prices(datetime.date.today())
    usd = in_tok * p_in / 1e6 + out_tok * p_out / 1e6
    with _ledger_lock:
        ledger = load_ledger()
        m = month_usage(ledger)
        m["requests"] += 1
        m["chars"] += chars
        m["input_tokens"] += in_tok
        m["output_tokens"] += out_tok
        m["audio_seconds"] = round(m["audio_seconds"] + seconds, 2)
        m["usd"] = round(m["usd"] + usd, 6)
        ledger[month_key()] = m
        tmp = LEDGER + ".tmp"
        json.dump(ledger, open(tmp, "w", encoding="utf-8"), indent=2)
        os.replace(tmp, LEDGER)

def estimate_usd(chars, requests):
    p_in, p_out = prices(datetime.date.today())
    out_tok = chars * EST_OUTPUT_TOKENS_PER_CHAR
    return requests * EST_INPUT_TOKENS * p_in / 1e6 + out_tok * p_out / 1e6


# --- Audio helpers ------------------------------------------------------------
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

def cache_path(*parts):
    h = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:24]
    return os.path.join(CACHE_DIR, h + ".wav")


# --- Gemini --------------------------------------------------------------------
_spend_lock = threading.Lock()
_reserved = [0.0]   # estimated spend of requests currently in flight

def gemini_line(speaker, text, key):
    voice, style = GEMINI[speaker]
    path = cache_path("gemini", MODEL, voice, style, text)
    if os.path.exists(path):
        return sf.read(path, dtype="float32")[0]

    est = estimate_usd(len(text), 1)
    with _spend_lock:
        if month_usage()["usd"] + _reserved[0] + est > MONTHLY_CAP_USD:
            raise BudgetExceeded()
        _reserved[0] += est
    try:
        body = {
            "model": MODEL,
            "input": [{"type": "user_input", "content": [{
                "type": "text", "text": text,
                "annotations": [{"type": "speech_metadata", "style": style}]}]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice}]},
        }
        for attempt in range(6):
            try:
                req = urllib.request.Request(
                    "https://generativelanguage.googleapis.com/v1beta/interactions",
                    data=json.dumps(body).encode(), method="POST",
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"})
                resp = json.load(urllib.request.urlopen(req, timeout=180))
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                    time.sleep(2 ** attempt * 2); continue
                raise RuntimeError(f"Gemini HTTP {e.code}: {e.read().decode()[:500]}")
            except (urllib.error.URLError, TimeoutError):
                if attempt < 5:
                    time.sleep(2 ** attempt * 2); continue
                raise

            u = resp.get("usage", {})
            data = next((c["data"] for st in resp.get("steps", []) for c in (st.get("content") or [])
                         if c.get("data")), None)
            audio = trim(decode(base64.b64decode(data))) if data else np.zeros(0, np.float32)
            secs = len(audio) / SR
            record_usage(len(text), u.get("total_input_tokens", 0), u.get("total_output_tokens", 0), secs)

            # Guard against truncated or rambling output: plausible speech is 7-30 chars/sec.
            # Skipped for short lines ("Quiz?"), where the rate is meaningless.
            rate = len(text) / secs if secs else 0
            if len(text) < 40 or 7 <= rate <= 30 or attempt == 5:
                os.makedirs(CACHE_DIR, exist_ok=True)
                sf.write(path, audio, SR)
                return audio
            print(f"  retry (odd speech rate {rate:.0f} chars/s): {text[:50]}...", file=sys.stderr)
    finally:
        with _spend_lock:
            _reserved[0] -= est


# --- Kokoro --------------------------------------------------------------------
_kokoro = None

def kokoro_line(speaker, text):
    global _kokoro
    voice, speed, lang = KOKORO[speaker]
    path = cache_path("kokoro", voice, str(speed), text)
    if os.path.exists(path):
        return sf.read(path, dtype="float32")[0]
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(os.path.join(MODELS_DIR, "kokoro-v1.0.onnx"),
                         os.path.join(MODELS_DIR, "voices-v1.0.bin"))
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


# --- Main ----------------------------------------------------------------------
def render_all(lines, engine, key):
    texts = [(l["speaker"], clean(l["text"])) for l in lines]
    if engine == "kokoro":
        return [kokoro_line(s, t) for s, t in texts]
    with ThreadPoolExecutor(WORKERS) as ex:
        return list(ex.map(lambda st: gemini_line(st[0], st[1], key), texts))


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
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-dir", default=OUT_DIR)
    args = ap.parse_args()

    title, hook, lines = parse_script(args.script)
    stem = os.path.splitext(os.path.basename(args.script))[0]
    m = re.search(r"episode-(\d+)", stem)
    ep_id = f"episode-{m.group(1)}" if m else stem

    # Pre-flight: estimate cost of lines not already cached.
    todo = [(l["speaker"], clean(l["text"])) for l in lines]
    todo = [t for s, t in todo if not os.path.exists(cache_path("gemini", MODEL, *GEMINI[s], t))]
    est = estimate_usd(sum(map(len, todo)), len(todo))
    spent = month_usage()["usd"]
    print(f"{title}\n  {len(lines)} lines, {len(todo)} uncached; estimate ${est:.2f}; "
          f"spent this month ${spent:.2f} of ${MONTHLY_CAP_USD:.2f}")

    engine = args.engine
    if engine == "auto":
        engine = "gemini" if spent + est <= MONTHLY_CAP_USD else "kokoro"
        if engine == "kokoro":
            print("  monthly cap would be exceeded: using Kokoro")
    if args.dry_run:
        print(f"  would render with {engine}"); return

    key = None
    if engine == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        env = os.path.join(ROOT, ".env")
        if not key and os.path.exists(env):
            for l in open(env, encoding="utf-8"):
                k, _, v = l.strip().partition("=")
                if k == "GEMINI_API_KEY":
                    key = v.strip().strip('"')
        if not key:
            sys.exit("GEMINI_API_KEY not set")

    t0 = time.time()
    try:
        clips = render_all(lines, engine, key)
    except BudgetExceeded:
        if args.engine == "gemini":
            sys.exit("Monthly cap reached mid-render; rerun with --engine kokoro or raise the cap")
        print("  monthly cap reached mid-render: re-rendering whole episode with Kokoro")
        engine = "kokoro"
        clips = render_all(lines, engine, key)

    # Assemble with timestamps.
    gap = np.zeros(int(GAP_BETWEEN_LINES * SR), np.float32)
    parts, pos, out_lines = [np.zeros(int(LEAD_IN * SR), np.float32)], int(LEAD_IN * SR), []
    for i, (l, clip) in enumerate(zip(lines, clips)):
        out_lines.append({"i": i, "speaker": l["speaker"], "text": l["text"],
                          "start": round(pos / SR, 3), "end": round((pos + len(clip)) / SR, 3)})
        parts += [clip, gap]
        pos += len(clip) + len(gap)
    wav = np.concatenate(parts)

    os.makedirs(args.out_dir, exist_ok=True)
    mp3 = os.path.join(args.out_dir, ep_id + ".mp3")
    tmp_wav = os.path.join(CACHE_DIR, f"_{ep_id}_full.wav")
    os.makedirs(CACHE_DIR, exist_ok=True)
    sf.write(tmp_wav, wav, SR)
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", tmp_wav,
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-ac", "1",
                    "-b:a", "96k", mp3], check=True)
    os.remove(tmp_wav)

    meta = {
        "id": ep_id, "title": title, "hook": hook,
        "engine": engine, "model": MODEL if engine == "gemini" else "kokoro-v1.0",
        "voices": {s: (GEMINI if engine == "gemini" else KOKORO)[s][0] for s in ("MARCO", "SOFIA")},
        "rendered": datetime.datetime.now().isoformat(timespec="seconds"),
        "duration": round(len(wav) / SR, 3),
        "audio": os.path.basename(mp3),
        "lines": out_lines,
    }
    json.dump(meta, open(os.path.join(args.out_dir, ep_id + ".json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

    u = month_usage()
    print(f"  {mp3}: {meta['duration']/60:.1f} min, {engine}, {time.time()-t0:.0f}s render")
    print(f"  month {month_key()}: {u['chars']:,} chars, ${u['usd']:.3f} of ${MONTHLY_CAP_USD:.2f}")


if __name__ == "__main__":
    main()
