#!/usr/bin/env python3
"""Screenshot the episode page at desktop and phone width (needs the preview server running).

    python pipeline/screenshots.py before            # -> design/screenshots/before-*.png
    python pipeline/screenshots.py after --theme light
The paused quiz state is captured by pipeline/test_quiz_gate.py instead (it needs a fake audio clock).

Headless Chrome can't make a window narrower than ~500px, so each view is rendered
inside an iframe of the exact size and the parent page drives scrolling and clicks.
"""
import argparse, os, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
EP = "episode-12"

# name: (width, height, hash, action)
VIEWS = {
    "desktop-top":        (1440, 900, "#t=47", "top"),
    "desktop-transcript": (1440, 900, "#t=160", "transcript"),
    "desktop-quiz":       (1440, 900, "", "quiz"),
    "mobile-top":         (390, 844, "#t=47", "top"),
    "mobile-transcript":  (390, 844, "#t=160", "transcript"),
    "mobile-quiz":        (390, 844, "", "quiz"),
}

HARNESS = """<!doctype html><body style="margin:0;background:#000">
<script>
try { localStorage.clear(); %(theme)s } catch (e) {}
const f = document.createElement("iframe");
f.width = %(w)d; f.height = %(h)d; f.style.border = "0";
f.src = "%(ep)s/%(hash)s";
document.body.appendChild(f);
f.onload = () => setTimeout(() => {
  const w = f.contentWindow, d = w.document;
  if ("%(action)s" === "transcript") {
    const cur = d.querySelector(".line.current") || d.getElementById("transcript");
    w.scrollTo(0, cur.getBoundingClientRect().top + w.scrollY - %(h)d * 0.45);
  }
  if ("%(action)s" === "quiz") {
    const cards = d.querySelectorAll(".qcard");
    cards[0].querySelectorAll(".opt")[2].click();
    cards[1].querySelectorAll(".opt")[1].click();
    w.scrollTo(0, d.getElementById("quiz").getBoundingClientRect().top + w.scrollY - 16);
  }
}, 1500);
</script></body>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prefix")
    ap.add_argument("--theme", choices=["light", "dark", "system"], default="system")
    ap.add_argument("--only", nargs="*", help="view names to capture")
    args = ap.parse_args()
    out_dir = os.path.join(ROOT, "design", "screenshots")
    os.makedirs(out_dir, exist_ok=True)
    harness = os.path.join(ROOT, "site", "_shot.html")
    theme = "" if args.theme == "system" else f'localStorage.setItem("dd-theme", "{args.theme}");'
    try:
        for name, (w, h, hash_, action) in VIEWS.items():
            if args.only and name not in args.only:
                continue
            open(harness, "w", encoding="utf-8").write(
                HARNESS % dict(w=w, h=h, ep=EP, hash=hash_, action=action, theme=theme))
            out = os.path.join(out_dir, f"{args.prefix}-{name}.png")
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            "--virtual-time-budget=9000", f"--window-size={max(w, 500)},{h}",
                            f"--screenshot={out}", "http://localhost:8000/_shot.html"],
                           check=True, capture_output=True)
            if w < 500:  # crop the iframe out of the minimum-width window
                from PIL import Image
                Image.open(out).crop((0, 0, w, h)).save(out)
            print(" ", os.path.relpath(out, ROOT))
    finally:
        if os.path.exists(harness):
            os.remove(harness)


if __name__ == "__main__":
    main()
