#!/usr/bin/env python3
"""Check the quiz questions in content/episode-NN.json for the usual multiple-choice giveaways.

    python pipeline/check_quiz.py            # every episode
    python pipeline/check_quiz.py 9 12       # some episodes
    python pipeline/check_quiz.py --migrate  # convert old-format questions (options as strings,
                                             # correct as a position) to ids

Question format:
    {"id": "q1", "q": "...", "options": [{"id": "a", "text": "..."}, ...], "correct": "b",
     "explain": "...", "explain_at": "<words quoted from the line where Marco teaches it>"}

Flags (exit code 1 if any):
- the correct answer is more than 30% longer than the average distractor;
- the correct answer is noticeably more specific (numbers, technical terms) than every distractor;
- a distractor looks absurd: absolute wording ("always", "never", "only", "nothing", "guaranteed"),
  or a number more than 12x away from the correct one (a 10x slip is a real mistake);
- the correct answer sits in the same position in more than 40% of an episode's questions
  (the page shuffles options on every load, but the source order shouldn't give it away either);
- "all of the above" / "none of the above";
- a missing or very short explanation, or an explain_at that isn't in the script;
- not exactly four distinct options, or a correct id that isn't an option.
Also reported (not a failure): questions where no distractor echoes a mistake Sofia makes in the episode.
"""
import argparse, glob, json, os, re, statistics, sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from render import parse_script  # noqa: E402

ABSOLUTE = re.compile(r"\b(always|never|only|nothing|guaranteed|impossible|every single|can't be)\b", re.I)
ALL_NONE = re.compile(r"\b(all|none) of the (above|options)\b", re.I)
SPECIFIC = re.compile(r"\d|%|£|\$|€|\b[A-Z]{2,}\b|\b(EBITDA|EBIT|LTM|EV|P/E|PP&E|CVR|SG&A)\b")
STOP = set("the a an and or of to in on for is it its it's that this be by with as at are was from but not you your".split())


def numbers(text):
    vals = []
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)\s*(bn|m|k|%|x)?", text):
        v = float(m.group(1).replace(",", ""))
        v *= {"bn": 1e9, "m": 1e6, "k": 1e3}.get(m.group(2) or "", 1)
        vals.append(v)
    return vals


def content_words(text):
    return {w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP and len(w) > 3}


def migrate(q, i):
    if isinstance(q["options"][0], dict):
        return q
    ids = "abcd"
    return {"id": f"q{i + 1}", "q": q["q"],
            "options": [{"id": ids[k], "text": t} for k, t in enumerate(q["options"])],
            "correct": ids[q["correct"]], "explain": q.get("explain", ""), "explain_at": q.get("explain_at", "")}


def check_episode(path):
    n = int(re.search(r"episode-(\d+)", path).group(1))
    content = json.load(open(path, encoding="utf-8"))
    script = glob.glob(os.path.join(ROOT, "scripts", f"episode-{n:02d}-*.md"))
    lines = parse_script(script[0])[2] if script else []
    texts = [l["text"].lower() for l in lines]
    sofia = set().union(*[content_words(l["text"]) for l in lines if l["speaker"] == "SOFIA"]) if lines else set()
    flags, notes = [], []
    qs = content.get("quiz", {}).get("questions", [])
    positions = []
    for i, q in enumerate(qs):
        tag = f"ep {n} {q.get('id', f'q{i + 1}')}"
        if not isinstance(q["options"][0], dict):
            flags.append(f"{tag}: old format (run --migrate)"); continue
        opts = {o["id"]: o["text"] for o in q["options"]}
        if len(opts) != 4 or len(set(opts.values())) != 4:
            flags.append(f"{tag}: needs exactly four distinct options")
        if q.get("correct") not in opts:
            flags.append(f"{tag}: correct id {q.get('correct')!r} is not an option"); continue
        positions.append([o["id"] for o in q["options"]].index(q["correct"]))
        right = opts[q["correct"]]
        wrong = [t for k, t in opts.items() if k != q["correct"]]
        avg = statistics.mean(len(t) for t in wrong)
        # Length only gives an answer away in sentences, not in "1,000" vs "500" or "EV / revenue" vs "P/E".
        if max(len(t) for t in opts.values()) > 15 and len(right) > 1.3 * avg:
            flags.append(f"{tag}: correct answer is {len(right) / avg - 1:.0%} longer than the average distractor")
        if len(SPECIFIC.findall(right)) > max(len(SPECIFIC.findall(t)) for t in wrong) + 1:
            flags.append(f"{tag}: correct answer is more specific than every distractor")
        rn = numbers(right)
        for t in wrong:
            if ABSOLUTE.search(t) and not ABSOLUTE.search(right):
                flags.append(f"{tag}: distractor sounds absurd or absolute: {t!r}")
            for v in numbers(t):
                if rn and rn[0] and (v / rn[0] > 12 or v / rn[0] < 1 / 12) and v:
                    flags.append(f"{tag}: distractor number is wildly off: {t!r}")
                    break
        for t in opts.values():
            if ALL_NONE.search(t):
                flags.append(f"{tag}: uses 'all/none of the above'")
        if len(q.get("explain", "")) < 25:
            flags.append(f"{tag}: explanation missing or too short")
        at = q.get("explain_at", "")
        if not at or not any(at.lower() in t for t in texts):
            flags.append(f"{tag}: explain_at {at!r} not found in the script")
        if sofia and not any(len(content_words(t) & sofia) >= 2 for t in wrong):
            notes.append(f"{tag}: no distractor echoes a mistake Sofia makes")
    if positions:
        top = max(set(positions), key=positions.count)
        if positions.count(top) / len(positions) > 0.4:
            flags.append(f"ep {n}: correct answer is option {'ABCD'[top]} in {positions.count(top)} of {len(positions)} questions")
    return content, flags, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="*", type=int)
    ap.add_argument("--migrate", action="store_true")
    args = ap.parse_args()
    paths = sorted(glob.glob(os.path.join(ROOT, "content", "episode-*.json")))
    if args.episodes:
        paths = [p for p in paths if int(re.search(r"episode-(\d+)", p).group(1)) in args.episodes]
    total = 0
    for p in paths:
        if args.migrate:
            c = json.load(open(p, encoding="utf-8"))
            c["quiz"]["questions"] = [migrate(q, i) for i, q in enumerate(c["quiz"]["questions"])]
            json.dump(c, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        _, flags, notes = check_episode(p)
        total += len(flags)
        for f in flags:
            print("FLAG", f)
        for x in notes:
            print("note", x)
    print(f"{len(paths)} episodes checked, {total} flags")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
