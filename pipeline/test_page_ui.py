#!/usr/bin/env python3
"""Browser test for the quiz and player controls (needs the preview server running).

    python pipeline/test_page_ui.py [episode-09]

Uses a fake media clock (headless Chrome won't play audio) and synthetic key presses.
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from test_quiz_gate import FAKE_MEDIA, CHROME  # noqa: E402

TEST = r"""<pre id="test-out" hidden></pre>
<script>
(() => {
  const out = [], pre = document.getElementById("test-out");
  const check = (name, ok, extra) => { out.push((ok ? "PASS " : "FAIL ") + name + (ok || extra === undefined ? "" : " (" + extra + ")")); pre.textContent = out.join("\n"); };
  const key = (el, k) => el.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
  setTimeout(() => {
    try {
      const $ = (id) => document.getElementById(id);
      const D = JSON.parse($("episode-data").textContent), a = $("audio");
      const opts = () => [...document.querySelectorAll("#opts .opt")];
      // --- quiz structure
      check("options are a radio group", $("opts").getAttribute("role") === "radiogroup" && opts().every((o) => o.getAttribute("role") === "radio"));
      check("options are lettered A-D in one column", opts().map((o) => o.querySelector(".opt-key").textContent).join("") === "ABCD");
      check("feedback region is aria-live", $("feedback").getAttribute("aria-live") === "polite");
      check("Next is hidden before answering", $("q-next").hidden && getComputedStyle($("q-next")).display === "none");
      // --- arrow keys move focus without answering
      opts()[0].focus(); key(opts()[0], "ArrowDown");
      check("ArrowDown moves focus to the next option", document.activeElement === opts()[1]);
      check("moving focus doesn't answer", opts().every((o) => o.getAttribute("aria-checked") === "false"));
      // --- number key answers
      key(opts()[1], "2");
      check("key 2 answers with option B", opts()[1].getAttribute("aria-checked") === "true");
      check("feedback appears below the options", /Correct|Not quite/.test($("feedback").textContent));
      check("no feedback text inside option cards", opts().every((o) => !/Correct|Not quite|answer/i.test(o.textContent.replace(o.querySelector(".opt-text").textContent, ""))));
      const q1 = D.quiz.questions[0];
      check("the correct option is marked", document.querySelector(`#opts .opt[data-id="${q1.correct}"]`).classList.contains("is-correct"));
      check("focus moves to Next after answering", document.activeElement === $("q-next"));
      check("Hear Marco explain this is offered", !!$("hear-explain"));
      // --- Enter continues
      key(opts()[0], "Enter");
      check("Enter goes to question 2", $("quiz-progress").textContent.startsWith("Question 2"));
      // --- letter key answers
      key(opts()[0], "c");
      check("key C answers with option C", opts()[2].getAttribute("aria-checked") === "true");
      // finish the round
      for (let i = 0; i < 6 && !$("qcard").hidden; i++) { $("q-next").click(); if (!$("qcard").hidden) key(opts()[0], "a"); }
      check("end screen shows a score", /scored \d of \d/.test($("quiz-end").textContent));
      const retry = $("retry-missed") || $("retry-all");
      check("end screen offers a retry and the next episode", !!retry && !!document.querySelector("#quiz-end a.btn"));
      if ($("retry-missed")) {
        const missed = document.querySelectorAll(".missed li").length;
        $("retry-missed").click();
        check("Retry the ones I missed restarts with only those", $("quiz-progress").textContent === `Question 1 of ${missed}`);
      }
      // --- player
      const t0 = a.currentTime; key(document.body, "ArrowRight");
      check("ArrowRight skips forward 15 s", Math.abs(a.currentTime - t0 - 15) < 0.5, a.currentTime - t0);
      key(document.body, "ArrowLeft");
      check("ArrowLeft goes back 15 s", Math.abs(a.currentTime - t0) < 0.5);
      key(document.body, " ");
      check("Space plays", !a.paused);
      key(document.body, " ");
      check("Space pauses", a.paused);
      const seen = []; for (let i = 0; i < 5; i++) { $("rate").click(); seen.push(a.playbackRate); }
      check("speed cycles through 0.75, 1, 1.25, 1.5, 2", [...seen].sort().join() === "0.75,1,1.25,1.5,2", seen.join());
      const marks = document.querySelectorAll(".pl-chapter");
      check("chapter markers on the scrubber", marks.length === D.chapters.length && marks.length >= 4, marks.length);
      marks[2].click();
      check("clicking a chapter jumps to it", Math.abs(a.currentTime - D.chapters[2].start) < 0.5);
      check("download link present", !!document.querySelector('.facts a[download]'));
      a.dispatchEvent(new Event("error"));
      check("audio error shows a message and disables play", !$("pl-error").hidden && $("play").disabled);
      check("finished", true);
    } catch (e) { check("threw: " + e.message, false); }
  }, 2500);
})();
</script>"""


def main():
    ep = sys.argv[1] if len(sys.argv) > 1 else "episode-09"
    html = open(os.path.join(ROOT, "site", ep, "index.html"), encoding="utf-8").read()
    html = re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]*>', "", html)
    html = html.replace("<head>", "<head>\n" + FAKE_MEDIA, 1).replace("</body>", TEST + "\n</body>", 1)
    path = os.path.join(ROOT, "site", ep, "_ui_test.html")
    open(path, "w", encoding="utf-8").write(html)
    try:
        dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=12000", "--dump-dom",
                              f"http://localhost:8000/{ep}/_ui_test.html"], capture_output=True, text=True, encoding="utf-8").stdout
    finally:
        os.remove(path)
    m = re.search(r'<pre id="test-out" hidden="">(.*?)</pre>', dom, re.S)
    result = (m.group(1).strip() if m else "") or "FAIL no output"
    print(result)
    sys.exit(1 if "FAIL" in result or "PASS finished" not in result else 0)


if __name__ == "__main__":
    main()
