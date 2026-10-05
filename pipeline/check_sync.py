#!/usr/bin/env python3
"""Check an episode's line timings against its audio (needs the preview server for --browser).

    python pipeline/check_sync.py 1 2 3            # audio check: does each line start where we say?
    python pipeline/check_sync.py 12 --browser     # also: do visuals land on their lines in the page?

Audio check: transcribe the 2.8 s starting at each line's start and compare with the
line's first words. Browser check: open the page at each visual's line and read the
highlighted line and the figure shown.
"""
import argparse, json, os, re, subprocess, sys, warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import numpy as np  # noqa: E402
import align  # noqa: E402
from render import ffmpeg_exe  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def audio_check(ep_id):
    meta = json.load(open(os.path.join(ROOT, "audio", ep_id + ".json"), encoding="utf-8"))
    mp3 = os.path.join(ROOT, "site", "audio", ep_id + ".mp3")
    raw = subprocess.run([ffmpeg_exe(), "-loglevel", "error", "-i", mp3, "-f", "f32le", "-ac", "1", "-ar", "24000", "-"],
                         capture_output=True).stdout
    audio = np.frombuffer(raw, np.float32)
    bad = []
    for l in meta["lines"]:
        a = int(max(0, l["start"] - 0.1) * 24000)
        heard = [w for w, _, _ in align.transcribe(audio[a:a + int(2.8 * 24000)])][:5]
        want = align.norm_words(align.spell_numbers(l["text"]))[:4]
        if not (len(set(heard[:4]) & set(want[:3])) >= min(2, len(want)) or (heard and heard[0] == want[0])):
            bad.append((l["i"], l["start"], " ".join(want), " ".join(heard)))
    return len(meta["lines"]), bad


def browser_check(ep_id):
    html = open(os.path.join(ROOT, "site", ep_id, "index.html"), encoding="utf-8").read()
    D = json.loads(re.search(r'application/json">(.*?)</script>', html, re.S).group(1))
    checks = [(k + 1, v["line"], D["lines"][v["line"]]["start"]) for k, v in enumerate(D["visuals"])]
    harness = ("<!doctype html><body><div id='out'>pending</div><script>"
               "const checks=%s;const out=[];let i=0;function next(){if(i>=checks.length){"
               "document.getElementById('out').textContent=out.join(';');return;}"
               "const [fig,line,t]=checks[i++];const f=document.createElement('iframe');f.width=1200;f.height=800;"
               "f.src='%s/#t='+(t+0.6).toFixed(2);f.onload=()=>setTimeout(()=>{const d=f.contentDocument;"
               "const cur=d.querySelector('.line.current');const idx=cur?[...d.querySelectorAll('.line')].indexOf(cur):-1;"
               "const fc=d.getElementById('fig-count').textContent;out.push(fig+'|'+line+'|'+idx+'|'+fc);f.remove();next();},800);"
               "document.body.appendChild(f);}next();</script></body>") % (json.dumps(checks), ep_id)
    path = os.path.join(ROOT, "site", "_sync.html")
    open(path, "w", encoding="utf-8").write(harness)
    try:
        dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=120000", "--dump-dom",
                              "http://localhost:8000/_sync.html"], capture_output=True, text=True, encoding="utf-8").stdout
    finally:
        os.remove(path)
    rows = re.search(r"<div id=\"out\">(.*?)</div>", dom, re.S).group(1).split(";")
    bad = []
    for r in rows:
        fig, line, idx, fc = r.split("|")
        if line != idx or f"Fig. {fig} " not in fc:
            bad.append(f"Fig {fig}: expected line {line}, highlighted {idx}, panel '{fc.strip()}'")
    return len(checks), bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="+", type=int)
    ap.add_argument("--browser", action="store_true")
    args = ap.parse_args()
    failed = False
    for n in args.episodes:
        ep_id = f"episode-{n:02d}"
        total, bad = audio_check(ep_id)
        msg = f"{ep_id}: {total - len(bad)}/{total} line starts verified in the audio"
        if args.browser:
            vt, vbad = browser_check(ep_id)
            msg += f"; {vt - len(vbad)}/{vt} visuals on the right line"
            bad += [(None, None, b, "") for b in vbad]
        print(msg, flush=True)
        for i, t, want, heard in bad:
            print(f"   line {i} at {t:.2f}s: expected '{want}', heard '{heard}'" if i is not None else f"   {want}")
        failed |= len(bad) > max(1, total // 20)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
