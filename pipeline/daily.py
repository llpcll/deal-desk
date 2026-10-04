#!/usr/bin/env python3
"""The daily job: write, render and publish the next episode.

    python pipeline/daily.py               # what the 6:45 scheduled task runs
    python pipeline/daily.py --no-publish  # stop after rendering; preview with build_site.py --drafts --serve

The next episode is the one after the highest number in published.json. Every step
is skipped if its output already exists, so a failed run can simply be run again:

1. Write   scripts/episode-NN-*.md and content/episode-NN.json with the Claude Code CLI
           (headless, allowed only to read the repo, search the web and write those two files).
2. Check   the script and content against the brief's rules; on failure Claude gets the
           list of problems and fixes them (twice at most), otherwise the run stops.
3. Render  with pipeline/render.py (Gemini within the monthly cap, Kokoro beyond it).
4. Publish add to published.json, rebuild site + feed, commit and push; GitHub Pages deploys.

Logs go to logs/daily-YYYY-MM-DD.log.
"""
import argparse, datetime, glob, json, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import build_site  # noqa: E402
from render import parse_script  # noqa: E402

LOG_DIR = os.path.join(ROOT, "logs")
LOCK = os.path.join(ROOT, "logs", "daily.lock")
FIX_ATTEMPTS = 2

BANNED = ["delve", "dive into", "tapestry", "landscape", "realm", "navigate", "crucial", "pivotal", "vital",
          "robust", "seamless", "holistic", "unlock", "unleash", "empower", "game-changer", "elevate", "embark",
          "journey", "intricate", "nuanced", "multifaceted", "it's important to note", "it's worth noting",
          "it is important to note", "it is worth noting", "let's break it down", "at the end of the day",
          "in a nutshell", "buckle up"]
VISUAL_TYPES = {"tombstone", "keynumbers", "waterfall", "bars", "table", "steps", "formula", "football", "quizcall"}

_log_file = None


def log(msg):
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    if _log_file:
        _log_file.write(line + "\n"); _log_file.flush()


def run(cmd, **kw):
    log("$ " + " ".join(str(c) for c in cmd)[:300])
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    for stream in (p.stdout, p.stderr):
        if stream and stream.strip():
            for l in stream.strip().splitlines()[-40:]:
                log("  " + l)
    if p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {cmd[0]} {cmd[1] if len(cmd) > 1 else ''}")
    return p.stdout


# --- 1. Write -------------------------------------------------------------------------
def claude_exe():
    exe = shutil.which("claude") or os.path.expanduser(r"~\.local\bin\claude.exe")
    if not os.path.exists(exe):
        raise RuntimeError("Claude Code CLI not found")
    return exe


def ask_claude(prompt):
    allowed = ["Read", "Glob", "Grep", "WebSearch", "WebFetch",
               "Write(./scripts/**)", "Edit(./scripts/**)", "Write(./content/**)", "Edit(./content/**)"]
    return run([claude_exe(), "-p", "--allowedTools", *allowed, "--max-turns", "80"],
               input=prompt, timeout=45 * 60)


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
   - "quiz": {{"pause_at": "Pause here if you want to think it through", "answers_at": "Answers.", "questions": [5 items with "q", 4 "options", "correct" (0-based index) and "explain"]}}. The wrong options should be the mistakes students really make.
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
    if len(qs) != 5:
        errors.append(f"quiz has {len(qs)} questions; it needs 5.")
    for i, item in enumerate(qs):
        if len(item.get("options", [])) != 4 or not 0 <= item.get("correct", -1) < 4 or not item.get("explain"):
            errors.append(f"quiz question {i + 1} needs 4 options, a 0-based \"correct\" and \"explain\".")
    src = c.get("sources", [])
    if not 2 <= len(src) <= 5 or any(not s.get("url", "").startswith("http") for s in src):
        errors.append("sources: 3 to 5 items, each with a label and an http(s) url.")
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
    json.dump(published, open(build_site.PUBLISHED, "w", encoding="utf-8"), indent=2)
    build_site.build()
    run(["git", "add", "scripts", "content", "audio", "site", "published.json", "pipeline/usage.json"])
    run(["git", "commit", "-m", f"Episode {n}: {title}"])
    run(["git", "push"])
    log(f"published {ep_id}")


def main():
    global _log_file
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-publish", action="store_true")
    args = ap.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)
    today = datetime.date.today()
    _log_file = open(os.path.join(LOG_DIR, f"daily-{today}.log"), "a", encoding="utf-8")
    if os.path.exists(LOCK) and (datetime.datetime.now().timestamp() - os.path.getmtime(LOCK)) < 3 * 3600:
        log("another run is in progress (logs/daily.lock); stopping"); return 1
    open(LOCK, "w").write(str(os.getpid()))
    try:
        if not args.no_publish:
            run(["git", "pull", "--rebase", "--autostash"])
        published = build_site.load_json(build_site.PUBLISHED, {})
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

        run([sys.executable, os.path.join(ROOT, "pipeline", "render.py"), script])
        try:  # checks the anchors against the rendered lines too
            build_site.build(drafts=True)
        finally:
            build_site.build()  # leave site/ with published episodes only

        title = re.sub(r"^The Deal Desk, episode \d+:\s*", "", parse_script(script)[0])
        if args.no_publish:
            log(f"episode {n} rendered, not published. Preview: python pipeline/build_site.py --drafts --serve")
        else:
            publish(n, title)
        return 0
    except Exception as e:
        log(f"FAILED: {e}")
        return 1
    finally:
        os.remove(LOCK)
        _log_file.close()


if __name__ == "__main__":
    sys.exit(main())
