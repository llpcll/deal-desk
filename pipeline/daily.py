#!/usr/bin/env python3
"""The daily job: write, render and publish the next episode.

    python pipeline/daily.py               # what the 6:45 scheduled task runs
    python pipeline/daily.py --no-publish  # stop after rendering; preview with build_site.py --drafts --serve
    python pipeline/daily.py --dry-run     # test the whole path (lock, power request, network, Claude, render)
                                           # on a six-line script rendered into logs/dryrun/; nothing is published

The task also runs at 7:30 and at logon, so a 6:45 missed while the laptop was asleep or off is caught up;
nothing happens if an episode was already published today.

The next episode is the one after the highest number in published.json. Every step
is skipped if its output already exists, so a failed run can simply be run again:

1. Write   scripts/episode-NN-*.md and content/episode-NN.json with the Claude Code CLI
           (headless, allowed only to read the repo, search the web and write those two files).
2. Check   the script and content against the brief's rules; on failure Claude gets the
           list of problems and fixes them (twice at most), otherwise the run stops.
3. Render  with pipeline/render.py (Gemini within the monthly cap, Kokoro beyond it).
4. Publish add to published.json, rebuild site + feed, commit and push; GitHub Pages deploys.

Logs go to logs/daily-YYYY-MM-DD.log (Claude's progress included), and every run ends by
writing one line, OK or FAILED and why, to logs/last-run.txt.

Nothing can hang: every command has a timeout after which its whole process tree is killed
(Claude 25 minutes, retried once; render 30; git 2), and the run as a whole stops after
RUN_MINUTES, under repolock's 90-minute stale age. While it runs it holds a Windows power
request, because on 2026-10-07 the laptop fell back into Modern Standby 20 seconds after
a wake-up start and froze the run for hours.
"""
import argparse, ctypes, datetime, glob, json, os, re, shutil, socket, subprocess, sys, threading, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import build_site, check_quiz, repolock  # noqa: E402
from render import parse_script  # noqa: E402

LOG_DIR = os.path.join(ROOT, "logs")
FIX_ATTEMPTS = 2
LOCK_WAIT_MINUTES = 90   # if the backfill is running, wait for it rather than skip the day
CLAUDE_TIMEOUT = 25 * 60  # a normal write takes about 5 minutes
RENDER_TIMEOUT = 30 * 60
GIT_TIMEOUT = 2 * 60
RUN_MINUTES = 85          # whole run, after taking the lock; keep it under repolock.STALE_MINUTES
NETWORK_WAIT_MINUTES = 5  # after a wake-up the Wi-Fi can take a while to come back
LAST_RUN = os.path.join(LOG_DIR, "last-run.txt")
WRITER_SETTINGS = os.path.join(ROOT, ".claude", "daily-writer.json")
# The only paths a daily commit may touch. Anything else means something went wrong
# (or a web page talked the writer into something), so the run stops before pushing.
ALLOWED_PATHS = ("scripts/", "content/", "audio/", "site/", "published.json")

BANNED = ["delve", "dive into", "tapestry", "landscape", "realm", "navigate", "crucial", "pivotal", "vital",
          "robust", "seamless", "holistic", "unlock", "unleash", "empower", "game-changer", "elevate", "embark",
          "journey", "intricate", "nuanced", "multifaceted", "it's important to note", "it's worth noting",
          "it is important to note", "it is worth noting", "let's break it down", "at the end of the day",
          "in a nutshell", "buckle up"]
VISUAL_TYPES = {"tombstone", "keynumbers", "waterfall", "bars", "table", "steps", "formula", "football", "quizcall"}

_log_file = None
_deadline = None   # wall clock, so a run frozen by standby is stopped as soon as it thaws
_child = None      # the command running now, for the watchdog to kill


def log(msg):
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    if _log_file:
        _log_file.write(line + "\n"); _log_file.flush()


class StepTimeout(RuntimeError):
    pass


def kill_tree(pid):
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)


def _log_line(line):
    if line.strip():
        log("  " + line)


def run(cmd, timeout, input=None, on_stdout=_log_line, on_stderr=_log_line, **kw):
    """Run cmd, logging its output as it arrives. After timeout seconds (or at the run's
    deadline, if sooner) kill its whole process tree and raise StepTimeout. Waiting on the
    pipes never blocks: subprocess.run(timeout=...) can, when a grandchild keeps them open."""
    global _child
    name = os.path.basename(str(cmd[0]))
    log("$ " + " ".join(str(c) for c in cmd)[:300])
    if _deadline:
        timeout = min(timeout, max(0, _deadline - time.time()))
    p = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace", **kw)
    _child = p
    out = []

    def pump(stream, handler, keep):
        for line in stream:
            if keep:
                out.append(line)
            handler(line.rstrip("\n"))

    def feed():
        try:
            p.stdin.write(input); p.stdin.close()
        except OSError:
            pass

    threads = [threading.Thread(target=pump, args=(p.stdout, on_stdout, True), daemon=True),
               threading.Thread(target=pump, args=(p.stderr, on_stderr, False), daemon=True)]
    if input is not None:
        threads.append(threading.Thread(target=feed, daemon=True))
    for t in threads:
        t.start()
    end = time.time() + timeout
    while p.poll() is None and time.time() < end:
        time.sleep(1)
    timed_out = p.poll() is None
    if timed_out:
        kill_tree(p.pid)
    for t in threads:
        t.join(5)
    _child = None
    if timed_out:
        raise StepTimeout(f"{name} timed out after {timeout / 60:.0f} minutes; killed its process tree")
    if p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {name} {cmd[1] if len(cmd) > 1 else ''}")
    return "".join(out)


def git(*args):
    return run(["git", *args], timeout=GIT_TIMEOUT)


def keep_awake():
    """Ask Windows not to sleep, and not to freeze this process, until the run exits
    (power requests end with the process)."""
    if sys.platform != "win32":
        return

    class _Detailed(ctypes.Structure):
        _fields_ = [("module", ctypes.c_void_p), ("id", ctypes.c_ulong),
                    ("count", ctypes.c_ulong), ("strings", ctypes.c_void_p)]

    class _Reason(ctypes.Union):
        _fields_ = [("detailed", _Detailed), ("simple", ctypes.c_wchar_p)]

    class REASON_CONTEXT(ctypes.Structure):
        _fields_ = [("version", ctypes.c_ulong), ("flags", ctypes.c_ulong), ("reason", _Reason)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.PowerCreateRequest.restype = ctypes.c_void_p
    k32.PowerCreateRequest.argtypes = [ctypes.POINTER(REASON_CONTEXT)]
    k32.PowerSetRequest.argtypes = [ctypes.c_void_p, ctypes.c_int]
    ctx = REASON_CONTEXT(0, 1)  # POWER_REQUEST_CONTEXT_VERSION, POWER_REQUEST_CONTEXT_SIMPLE_STRING
    ctx.reason.simple = "The Deal Desk daily episode"
    h = k32.PowerCreateRequest(ctypes.byref(ctx))
    ok = bool(h) and all(k32.PowerSetRequest(h, kind) for kind in (1, 3))  # SystemRequired, ExecutionRequired
    keep_awake.handle = h  # keep it open for the life of the process
    log("holding power request: system required, execution required" if ok
        else f"could not set the power request (error {ctypes.get_last_error()}); standby may freeze the run")


def wait_for_network(minutes=NETWORK_WAIT_MINUTES):
    hosts = ("github.com", "api.anthropic.com")
    end = time.time() + minutes * 60
    waited = False
    while True:
        try:
            for host in hosts:
                socket.create_connection((host, 443), timeout=5).close()
            if waited:
                log("network is up")
            return
        except OSError as e:
            if time.time() >= end:
                raise RuntimeError(f"network not ready after {minutes} minutes ({e})")
            if not waited:
                log(f"network not ready ({e}); waiting up to {minutes} minutes")
                waited = True
            time.sleep(10)


def watchdog():
    """Backstop for the in-process steps (checks, site build), which run() can't time out."""
    while time.time() < _deadline:
        time.sleep(15)
    log(f"FAILED: the run passed its {RUN_MINUTES}-minute limit; stopping")
    if _child and _child.poll() is None:
        kill_tree(_child.pid)
    write_last_run(f"FAILED: the run passed its {RUN_MINUTES}-minute limit")
    h = repolock.holder()
    if h and h.get("pid") == os.getpid():
        os.remove(repolock.LOCK)
    os._exit(1)


def write_last_run(status):
    try:
        with open(LAST_RUN, "w", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M} {status}\n")
    except OSError as e:
        log(f"could not write {LAST_RUN}: {e}")


# --- 1. Write -------------------------------------------------------------------------
def claude_exe():
    exe = shutil.which("claude") or os.path.expanduser(r"~\.local\bin\claude.exe")
    if not os.path.exists(exe):
        raise RuntimeError("Claude Code CLI not found")
    return exe


def changed_paths():
    out = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8", timeout=GIT_TIMEOUT).stdout
    return {l[3:].strip().strip('"').split(" -> ")[-1].replace("\\", "/") for l in out.splitlines() if l.strip()}


def outside_allowed(paths, allowed):
    return sorted(p for p in paths if not p.startswith(allowed))


def _short(v, n=160):
    v = " ".join(str(v).split())
    return v if len(v) <= n else v[:n] + "..."


class ClaudeProgress:
    """Turns Claude's stream-json output into one log line per step."""
    KEY = {"WebSearch": "query", "WebFetch": "url", "Read": "file_path", "Edit": "file_path",
           "Write": "file_path", "Glob": "pattern", "Grep": "pattern"}

    def __init__(self):
        self.result = None

    def __call__(self, line):
        try:
            ev = json.loads(line)
        except ValueError:
            return _log_line(line)
        kind = ev.get("type")
        if kind == "system" and ev.get("subtype") == "init":
            log(f"  claude: started, model {ev.get('model')}, session {ev.get('session_id')}")
        elif kind == "assistant":
            for c in ev.get("message", {}).get("content", []):
                if c.get("type") == "text" and c.get("text", "").strip():
                    log("  claude: " + _short(c["text"]))
                elif c.get("type") == "tool_use":
                    inp = c.get("input", {})
                    log(f"  claude -> {c.get('name')} {_short(inp.get(self.KEY.get(c.get('name')), inp), 120)}")
        elif kind == "user":
            for c in ev.get("message", {}).get("content", []):
                if isinstance(c, dict) and c.get("is_error"):
                    log("  claude: tool error: " + _short(c.get("content")))
        elif kind == "rate_limit_event":
            info = ev.get("rate_limit_info", {})
            windows = {k: v.get("utilization") for k, v in info.get("unifiedWindows", {}).items()}
            if info.get("status") != "allowed" or any((u or 0) >= 0.9 for u in windows.values()):
                log(f"  claude: usage limit {info.get('status')}: {windows}")
        elif kind == "result":
            self.result = ev
            log(f"  claude: {ev.get('subtype')} after {ev.get('num_turns')} turns, "
                f"{(ev.get('duration_ms') or 0) / 1000:.0f}s, ${ev.get('total_cost_usd') or 0:.2f}"
                + (f": {_short(ev.get('result'))}" if ev.get("is_error") or ev.get("subtype") != "success" else ""))


def ask_claude(prompt):
    """Headless Claude with the daily-writer permissions: read the repo, search and fetch
    the web, write only scripts/ and content/. No shell, no MCP servers or connectors.
    Web pages can carry injected instructions, so its effect on the repo is checked after.
    Killed after CLAUDE_TIMEOUT and retried once."""
    before = changed_paths()
    allowed = ["Read(./**)", "Glob", "Grep", "WebSearch", "WebFetch",
               "Edit(./scripts/**)", "Edit(./content/**)"]   # Edit rules cover every file-writing tool
    env = dict(os.environ, ENABLE_CLAUDEAI_MCP_SERVERS="false")
    env.pop("GEMINI_API_KEY", None)
    cmd = [claude_exe(), "-p", "--settings", WRITER_SETTINGS, "--strict-mcp-config",
           "--allowedTools", *allowed, "--disallowedTools", "Bash", "PowerShell", "NotebookEdit", "Agent",
           "--max-turns", "80", "--output-format", "stream-json", "--verbose"]
    for attempt in (1, 2):
        progress = ClaudeProgress()
        try:
            run(cmd, timeout=CLAUDE_TIMEOUT, input=prompt, env=env,
                on_stdout=progress, on_stderr=lambda l: _log_line("claude stderr: " + l) if l.strip() else None)
            break
        except StepTimeout as e:
            if attempt == 2:
                raise
            log(f"{e}; retrying once")
    r = progress.result or {}
    if r.get("is_error"):
        raise RuntimeError(f"Claude failed: {_short(r.get('result'))}")
    stray = outside_allowed(changed_paths() - before, ("scripts/", "content/"))
    if stray:
        raise RuntimeError(f"the writer changed files outside scripts/ and content/: {stray}; stopping")
    return r.get("result", "")


def episode_files(n):
    scripts = glob.glob(os.path.join(ROOT, "scripts", f"episode-{n:02d}-*.md"))
    content = os.path.join(ROOT, "content", f"episode-{n:02d}.json")
    return (scripts[0] if scripts else None), content


def write_prompt(n, today):
    review = n % 7 == 0
    prev = sorted(glob.glob(os.path.join(ROOT, "scripts", "episode-*.md")))[-2:]
    prev_rel = ", ".join(os.path.relpath(p, ROOT).replace("\\", "/") for p in prev)
    return f"""You are writing episode {n} of The Deal Desk, a daily corporate finance podcast. Today is {today:%A %d %B %Y}.

Read first:
- PROJECT_BRIEF.md: the characters, script rules, banned words and the syllabus. Episode {n}'s topic comes from the syllabus.{" This is a REVIEW episode: review the previous six episodes, Sunday-style, as episode 7 did." if review else ""}
- The two most recent scripts ({prev_rel}) for voice, length and continuity. The last one ends with a teaser for this episode; deliver on it.
- DESIGN.md (section "Components" > "Visuals") and content/episode-12.json: the format of the visuals, quiz and sources file.

Then write exactly two files, and change nothing else:

1. scripts/episode-{n:02d}-<short-slug>.md, following every rule in the brief:
   - First line "# The Deal Desk, episode {n:02d}: <title>", then a one-line hook, then "---", then only lines starting "MARCO: " or "SOFIA: ", separated by blank lines.
   - Structure: cold open with a real deal story, the concept with a worked example in round numbers, "What they'll ask you" (2 to 3 interview questions; Sofia answers imperfectly, Marco gives the strong answer), deal of the day, a 5-question quiz, a teaser for episode {n + 1}.
   - Deal of the day: a real deal announced between {today - datetime.timedelta(days=7):%d %B} and {today:%d %B %Y}, preferably European. Find it with WebSearch and confirm every figure and date from at least one primary or reputable source with WebFetch. Never invent a number; if you can't verify a figure, leave it out.
   - Written for the ear: every number spelled out as it is said ("two point three billion pounds", "twenty twenty-five"); no digits and no symbols ($ € £ % & / em dashes) in dialogue; say "mergers and acquisitions", never "M&A"; abbreviations read letter by letter are hyphenated (E-V, D-C-F, L-T-M).
   - No banned words or phrases from the brief.
   - The quiz: Marco reads five questions in one line, then the exact line "MARCO: Pause here if you want to think it through.", then one line starting "MARCO: Answers." with all five answers.
   - About 9,500 to 11,000 characters of dialogue (roughly eleven minutes).

2. content/episode-{n:02d}.json with:
   - "visuals": 10 to 15 items using only these types: {", ".join(sorted(VISUAL_TYPES))}. Each "at" must be a short phrase copied character for character from the script line where the visual should appear. Use at most two tombstones (the cold-open deal and the deal of the day), and only figures that appear in the script.
   - "quiz": {{"pause_at": "Pause here if you want to think it through", "answers_at": "Answers.", "questions": [...]}}, with 5 questions (10 in a review episode), each
     {{"id": "q1", "q": "...", "options": [{{"id": "a", "text": "..."}}, {{"id": "b", ...}}, {{"id": "c", ...}}, {{"id": "d", ...}}], "correct": "<option id>",
       "explain": "one or two sentences on why", "explain_at": "<words copied exactly from the line where Marco teaches it>"}}.
     The wrong options must be real mistakes, ideally ones Sofia makes in the episode. Keep the correct option no longer or more specific than the others,
     vary its position, never use "all/none of the above", and avoid absolute wording (always, never, only, nothing) in wrong options.
     pipeline/check_quiz.py checks all of this.
   - "sources": 3 to 5 {{"label", "url"}} items, primary sources first (company announcements, regulatory filings), each one a page you actually opened.

When both files are written, reply with one line: DONE scripts/episode-{n:02d}-<slug>.md"""


# --- 2. Check -------------------------------------------------------------------------
def check_episode(script, content_path):
    errors = []
    raw = open(script, encoding="utf-8").read()
    head = raw.split("\n---", 1)[0].strip().splitlines()
    if not head or not re.match(r"^# The Deal Desk, episode \d+: .+", head[0]):
        errors.append('First line must be "# The Deal Desk, episode NN: <title>".')
    if "\n---" not in raw:
        errors.append('Missing the "---" line after the hook.')
    body = raw.split("\n---", 1)[1] if "\n---" in raw else ""
    for i, l in enumerate(body.splitlines()):
        if l.strip() and not re.match(r"^(MARCO|SOFIA): ", l):
            errors.append(f'Body line must start with "MARCO: " or "SOFIA: ": {l[:80]!r}')
    title, hook, lines = parse_script(script)
    dialogue = " ".join(l["text"] for l in lines)
    low = dialogue.lower()
    for w in BANNED:
        if re.search(r"\b" + re.escape(w) + r"\b", low):
            errors.append(f"Banned word or phrase: {w!r}")
    if re.search(r"\bM\s*&\s*A\b", dialogue):
        errors.append('Say "mergers and acquisitions", never "M&A".')
    for sym in sorted(set(re.findall(r"[$€£%&/—\d]", dialogue))):
        ctx = re.search(r".{0,30}" + re.escape(sym) + r".{0,30}", dialogue).group(0)
        errors.append(f"Dialogue must not contain {sym!r} (spell it out): ...{ctx}...")
    if not 7000 <= len(dialogue) <= 14000:
        errors.append(f"Dialogue is {len(dialogue)} characters; aim for 9,500 to 11,000.")

    if not os.path.exists(content_path):
        return errors + [f"Missing {os.path.relpath(content_path, ROOT)}."]
    try:
        c = json.load(open(content_path, encoding="utf-8"))
    except ValueError as e:
        return errors + [f"content JSON is invalid: {e}"]
    texts = [l["text"].lower() for l in lines]
    found = lambda q: any(q.lower() in t for t in texts)
    vis = c.get("visuals", [])
    if not 8 <= len(vis) <= 16:
        errors.append(f"{len(vis)} visuals; use 10 to 15.")
    for v in vis:
        if v.get("type") not in VISUAL_TYPES:
            errors.append(f"Unknown visual type {v.get('type')!r}.")
        if not v.get("at") or not found(v["at"]):
            errors.append(f"Visual {v.get('title')!r}: \"at\" {v.get('at')!r} is not in any script line.")
    q = c.get("quiz") or {}
    for key in ("pause_at", "answers_at"):
        if not q.get(key) or not found(q[key]):
            errors.append(f"quiz.{key} {q.get(key)!r} is not in any script line.")
    qs = q.get("questions", [])
    if len(qs) not in (5, 10):
        errors.append(f"quiz has {len(qs)} questions; it needs 5 (10 in a review episode).")
    try:
        errors += check_quiz.check_episode(content_path)[1]
    except (KeyError, IndexError, TypeError, ValueError) as e:
        errors.append(f"quiz questions are malformed ({e}); see the format in pipeline/check_quiz.py")
    src = c.get("sources", [])
    # Fewer is fine when no reliable source exists; a guessed link never is.
    if not 1 <= len(src) <= 5 or any(not s.get("url", "").startswith("https://") or not s.get("label") for s in src):
        errors.append("sources: 1 to 5 items (aim for 3), each with a label and an https url you actually opened.")
    return errors


def fix_prompt(script, content_path, errors):
    rel = lambda p: os.path.relpath(p, ROOT).replace("\\", "/")
    return (f"The Deal Desk episode files {rel(script)} and {rel(content_path)} break these rules:\n\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\n\nFix every problem by editing those two files only (keep the content and verified facts; "
              "if you change a script line, keep any \"at\" anchors in the content file matching it). "
              "Read PROJECT_BRIEF.md if you need the rules. Reply DONE when finished.")


# --- 4. Publish -----------------------------------------------------------------------
def publish(n, title):
    ep_id = f"episode-{n:02d}"
    published = build_site.load_json(build_site.PUBLISHED, {})
    published[ep_id] = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    json.dump(dict(sorted(published.items())), open(build_site.PUBLISHED, "w", encoding="utf-8"), indent=2)
    build_site.build()
    git("add", "-A", "--", *ALLOWED_PATHS)
    git("commit", "-m", f"Episode {n}: {title}")
    # Check everything the push would send (all commits not yet on GitHub), not just today's.
    outgoing = set(git("diff", "--name-only", "@{upstream}..HEAD").split())
    stray = outside_allowed(outgoing, ALLOWED_PATHS)
    if stray:
        raise RuntimeError(f"refusing to push: outgoing changes outside {', '.join(ALLOWED_PATHS)}: {stray}. "
                           "Push those by hand after reviewing them.")
    git("push")
    log(f"published {ep_id}")


DRY_RUN_SCRIPT = os.path.join(ROOT, "scripts", "dryrun-test.md")


def dry_run():
    """Write and render a six-line test script, the way a real run does, then remove it."""
    log("dry run: writing a short test script with Claude...")
    try:
        ask_claude("Write the file scripts/dryrun-test.md and change nothing else. Its first line is "
                   "\"# The Deal Desk, dry run\", then a one-line hook, then a line \"---\", then six short "
                   "dialogue lines alternating \"MARCO: \" and \"SOFIA: \", separated by blank lines, about "
                   "what free cash flow is. No digits or symbols in the dialogue. Reply DONE when written.")
        if not os.path.exists(DRY_RUN_SCRIPT):
            raise RuntimeError("Claude did not write scripts/dryrun-test.md")
        out_dir = os.path.join(LOG_DIR, "dryrun")
        os.makedirs(out_dir, exist_ok=True)
        run([sys.executable, os.path.join(ROOT, "pipeline", "render.py"), DRY_RUN_SCRIPT, "--out-dir", out_dir],
            timeout=RENDER_TIMEOUT)
        mp3 = os.path.join(out_dir, "dryrun-test.mp3")
        if not os.path.exists(mp3):
            raise RuntimeError("render finished but wrote no logs/dryrun/dryrun-test.mp3")
        log(f"dry run rendered {os.path.relpath(mp3, ROOT)} ({os.path.getsize(mp3) // 1024} KB)")
        return 0, "OK: dry run wrote and rendered a test script (nothing published)"
    finally:
        if os.path.exists(DRY_RUN_SCRIPT):
            os.remove(DRY_RUN_SCRIPT)


def published_today(today):
    published = build_site.load_json(build_site.PUBLISHED, {})
    return [k for k, v in published.items() if v[:10] == today.isoformat()]


def main():
    status = "FAILED: stopped before finishing"
    try:
        rc, status = _main()
        return rc
    finally:
        write_last_run(status)


def _main():
    global _log_file, _deadline
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-publish", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="write and render a short test script; publish nothing")
    args = ap.parse_args()
    args.no_publish = args.no_publish or args.dry_run

    os.makedirs(LOG_DIR, exist_ok=True)
    today = datetime.date.today()
    _log_file = open(os.path.join(LOG_DIR, f"daily-{today}.log"), "a", encoding="utf-8")
    log(f"--- daily run{' (dry run)' if args.dry_run else ''}, pid {os.getpid()}")
    # The task runs at 6:45, again at 7:30 and at logon as safety nets, so it must publish at
    # most one a day. Check before waiting for the lock, then again after pulling.
    done = published_today(today)
    if done and not args.no_publish:
        log(f"{done[0]} already published today; nothing to do")
        return 0, f"OK: {done[0]} already published today"
    keep_awake()
    try:
        lock = repolock.hold("daily", wait_minutes=LOCK_WAIT_MINUTES, log=log)
        lock.__enter__()
    except repolock.Busy as e:
        log(f"FAILED: {e}")
        return 1, f"FAILED: {e}"
    _deadline = time.time() + RUN_MINUTES * 60
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        wait_for_network()
        if args.dry_run:
            return dry_run()
        if not args.no_publish:
            git("pull", "--rebase", "--autostash")
        published = build_site.load_json(build_site.PUBLISHED, {})
        done = published_today(today)
        if done and not args.no_publish:
            log(f"{done[0]} already published today; nothing to do")
            return 0, f"OK: {done[0]} already published today"
        n = max(int(k.split("-")[1]) for k in published) + 1
        log(f"next episode: {n}")

        script, content = episode_files(n)
        if not script:
            log("writing with Claude...")
            ask_claude(write_prompt(n, today))
            script, content = episode_files(n)
            if not script:
                raise RuntimeError("Claude did not write a script file")
        else:
            log(f"script exists: {os.path.relpath(script, ROOT)}")

        for attempt in range(FIX_ATTEMPTS + 1):
            errors = check_episode(script, content)
            if not errors:
                log("checks passed"); break
            log(f"{len(errors)} problems:"); [log("  - " + e) for e in errors]
            if attempt == FIX_ATTEMPTS:
                raise RuntimeError("episode still fails the checks; fix it by hand and rerun")
            ask_claude(fix_prompt(script, content, errors))
            script, content = episode_files(n)

        run([sys.executable, os.path.join(ROOT, "pipeline", "render.py"), script], timeout=RENDER_TIMEOUT)
        try:  # checks the anchors against the rendered lines too
            build_site.build(drafts=True)
        finally:
            build_site.build()  # leave site/ with published episodes only

        title = re.sub(r"^The Deal Desk, episode \d+:\s*", "", parse_script(script)[0])
        if args.no_publish:
            log(f"episode {n} rendered, not published. Preview: python pipeline/build_site.py --drafts --serve")
            return 0, f"OK: episode {n} rendered, not published"
        publish(n, title)
        return 0, f"OK: published episode-{n:02d}"
    except Exception as e:
        log(f"FAILED: {e}")
        return 1, f"FAILED: {e}"
    finally:
        lock.__exit__(None, None, None)
        _log_file.close()


if __name__ == "__main__":
    sys.exit(main())
