#!/usr/bin/env python3
"""Browser test for the quiz gate (needs the preview server running).

Headless Chrome won't play real audio, so a fake media clock replaces the <audio>
element's playback. The test plays across Marco's "pause here" line and checks that
the page stops, shows Continue, keeps the answers blurred, then reveals them.
A second run holds the paused state and saves a screenshot of it.

    python pipeline/test_quiz_gate.py [episode-12]
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

FAKE_MEDIA = """<script>
(() => {
  const theme = new URLSearchParams(location.search).get("theme");  // for the screenshots
  if (theme) document.documentElement.dataset.theme = theme;
  const P = HTMLMediaElement.prototype;
  let t = 0, paused = true, timer = null;
  Object.defineProperty(P, "currentTime", { get() { return t; }, set(v) { t = v; setTimeout(() => this.dispatchEvent(new Event("seeked"))); } });
  Object.defineProperty(P, "paused", { get() { return paused; } });
  P.play = function () {
    if (!paused) return Promise.resolve();
    paused = false; this.dispatchEvent(new Event("play"));
    timer = setInterval(() => { if (!paused) { t += 0.05; this.dispatchEvent(new Event("timeupdate")); } }, 50);
    return Promise.resolve();
  };
  P.pause = function () { if (paused) return; paused = true; clearInterval(timer); this.dispatchEvent(new Event("pause")); };
})();
</script>"""

# HOLD: "1" keeps the paused state on screen for a screenshot instead of continuing.
TEST = """<pre id="test-out" hidden></pre>
<script>
(() => {
  const pre = document.getElementById("test-out"), out = [];
  const check = (name, ok) => { out.push((ok ? "PASS " : "FAIL ") + name); pre.textContent = out.join("\\n"); };
  const step = (fn) => () => { try { fn(); } catch (e) { check("step threw: " + e.message, false); } };
  addEventListener("error", (e) => check("script error: " + e.message, false));
  const D = JSON.parse(document.getElementById("episode-data").textContent);
  const a = document.getElementById("audio"), end = D.lines[D.quiz.pauseLine].end;

  setTimeout(step(() => {
    check("answers blurred before playback", !!document.querySelector("li.held .reveal"));
    a.currentTime = end - 1.0; a.play();
  }), 1000);

  setTimeout(step(() => {
    check("audio paused at the pause line", a.paused && Math.abs(a.currentTime - end) < 0.2);
    check("Continue button shown", !!document.getElementById("gate-go"));
    check("answers still blurred while paused", !!document.querySelector("li.held"));
    if (%(hold)s) return;
    document.getElementById("gate-go").click();
    setTimeout(step(() => {
      check("Continue resumes audio", !a.paused);
      check("Continue reveals answers", !document.querySelector("li.held") && !document.getElementById("gate"));
      a.pause(); a.currentTime = end - 1.0; a.play();
      setTimeout(step(() => {
        check("no second pause once answers are revealed", !a.paused);
        check("finished", true);
      }), 2000);
    }), 300);
  }), 3500);
})();
</script>"""


HARNESS = """<!doctype html><body style="margin:0">
<iframe id="f" src="%(src)s" width="%(w)d" height="%(h)d" style="border:0"></iframe>
<script>
setTimeout(() => {
  const w = document.getElementById("f").contentWindow, g = w.document.getElementById("gate");
  if (g) w.scrollTo(0, g.getBoundingClientRect().top + w.scrollY - %(h)d * 0.45);
}, 5000);
</script></body>"""


def page(ep, hold):
    html = open(os.path.join(ROOT, "site", ep, "index.html"), encoding="utf-8").read()
    html = html.replace("<head>", "<head>\n" + FAKE_MEDIA, 1)
    return html.replace("</body>", TEST % dict(hold="true" if hold else "false") + "\n</body>", 1)


def main():
    ep = sys.argv[1] if len(sys.argv) > 1 else "episode-12"
    test_path = os.path.join(ROOT, "site", ep, "_gate_test.html")
    harness = os.path.join(ROOT, "site", "_gate_shot.html")
    url = f"http://localhost:8000/{ep}/_gate_test.html"
    shots = os.path.join(ROOT, "design", "screenshots")
    try:
        open(test_path, "w", encoding="utf-8").write(page(ep, hold=False))
        dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=15000",
                              "--dump-dom", url], capture_output=True, text=True, encoding="utf-8").stdout
        # Screenshots of the paused state. Headless Chrome renders a blank page if the
        # top-level page scrolls here, so the page sits in an iframe the harness scrolls.
        open(test_path, "w", encoding="utf-8").write(page(ep, hold=True))
        for theme in ("light", "dark"):
            for name, w, h in (("desktop", 1440, 900), ("mobile", 390, 844)):
                open(harness, "w", encoding="utf-8").write(HARNESS % dict(src=f"{ep}/_gate_test.html?theme={theme}", w=w, h=h))
                out = os.path.join(shots, f"after-{theme}-{name}-pause.png")
                subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                "--virtual-time-budget=9000", f"--window-size={max(w, 500)},{h}",
                                f"--screenshot={out}", "http://localhost:8000/_gate_shot.html"], capture_output=True)
                if w < 500:
                    from PIL import Image
                    Image.open(out).crop((0, 0, w, h)).save(out)
    finally:
        for f in (test_path, harness):
            if os.path.exists(f):
                os.remove(f)
    m = re.search(r'<pre id="test-out" hidden="">(.*?)</pre>', dom, re.S)
    result = (m.group(1).strip() if m else "")
    if "PASS finished" not in result:
        result += "\nFAIL test did not finish"
    print(result)
    sys.exit(1 if "FAIL" in result else 0)


if __name__ == "__main__":
    main()
