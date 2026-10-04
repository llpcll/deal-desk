/* The Deal Desk episode page: audio player, synced transcript, timed visuals, quiz. */
(() => {
  "use strict";
  const D = JSON.parse(document.getElementById("episode-data").textContent);
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const narrow = matchMedia("(max-width: 960px)");
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
  };

  const audio = $("audio");
  audio.src = D.audio;
  const lines = D.lines;
  const V = D.visuals || [];
  const duration = () => (isFinite(audio.duration) && audio.duration) || D.duration;
  const fmtTime = (s) => { s = Math.max(0, Math.floor(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };

  /* ---- Transcript ------------------------------------------------------- */
  const figsByLine = {};
  V.forEach((v, k) => (figsByLine[v.line] = figsByLine[v.line] || []).push(k));

  // Quiz answers stay blurred until the listener asks for them (or the audio reaches them).
  const Qz = D.quiz || {};
  const answerLines = new Set();
  if (Qz.answersLine != null) for (let i = Qz.answersLine; i < Qz.answersLine + (Qz.answersCount || 1); i++) answerLines.add(i);
  let revealed = answerLines.size === 0;
  const lineLis = [];

  const lineEls = lines.map((l, i) => {
    const li = document.createElement("li");
    const who = l.speaker === "MARCO" ? "Marco" : "Sofia";
    const refs = (figsByLine[i] || []).map((k) => `<span class="ref">Fig. ${k + 1}</span>`).join("");
    li.innerHTML = `<button type="button" class="line ${who.toLowerCase()}"><span class="gut"><span class="who">${who}</span><span class="when">${fmtTime(l.start)}</span></span><span class="txt">${esc(l.text)}${refs}</span></button>`;
    const btn = li.firstChild;
    btn.addEventListener("click", () => {
      if (answerLines.has(i) && !revealed) return;
      following = true; $("follow").hidden = true; seek(l.start); audio.play();
    });
    $("lines").appendChild(li);
    lineLis.push(li);
    return btn;
  });

  answerLines.forEach((i) => {
    const li = lineLis[i];
    li.classList.add("held");
    lineEls[i].setAttribute("tabindex", "-1");
    lineEls[i].querySelector(".txt").setAttribute("aria-hidden", "true");
    const b = document.createElement("button");
    b.type = "button"; b.className = "reveal"; b.textContent = "Reveal Marco's answers";
    b.addEventListener("click", () => revealAnswers());
    li.appendChild(b);
  });

  function revealAnswers() {
    if (revealed) return;
    revealed = true;
    answerLines.forEach((i) => {
      lineLis[i].classList.remove("held");
      lineEls[i].removeAttribute("tabindex");
      lineEls[i].querySelector(".txt").removeAttribute("aria-hidden");
      lineLis[i].querySelector(".reveal")?.remove();
    });
    $("gate")?.remove();
  }

  // When Marco says "pause here", stop the audio and wait for Continue.
  const pauseAt = Qz.pauseLine != null && !revealed ? lines[Qz.pauseLine].end : null;
  function openGate() {
    if ($("gate")) return;
    const g = document.createElement("li");
    g.id = "gate"; g.className = "gate";
    g.innerHTML = `<p>Paused so you can answer the quiz. Continue to hear Marco's answers.</p><button type="button" class="btn" id="gate-go">Continue</button>`;
    lineLis[Qz.pauseLine].after(g);
    $("gate-go").addEventListener("click", () => { revealAnswers(); audio.play(); });
    $("gate-go").focus({ preventScroll: true });
  }

  // Last index whose start <= t (small lead so highlights don't lag the voice).
  function lastStartBefore(starts, t) {
    let lo = 0, hi = starts.length - 1, ans = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (starts[mid] <= t + 0.05) { ans = mid; lo = mid + 1; } else hi = mid - 1; }
    return ans;
  }
  const lineStarts = lines.map((l) => l.start);
  const figStarts = V.map((v) => lines[v.line].start);

  let curLine = -1;
  let following = true;

  function scrollToLine(i) {
    const el = lineEls[i];
    if (!el) return;
    const stage = $("stage");
    const top = narrow.matches ? stage.getBoundingClientRect().bottom : 0;
    const bottom = innerHeight - $("player").offsetHeight;
    const target = top + (bottom - top) * 0.28;
    window.scrollTo({ top: scrollY + el.getBoundingClientRect().top - target, behavior: reduceMotion ? "auto" : "smooth" });
  }

  function setLine(i) {
    if (i === curLine) return;
    if (curLine >= 0) lineEls[curLine].classList.remove("current");
    curLine = i;
    if (i >= 0) {
      lineEls[i].classList.add("current");
      if (following && !audio.paused) scrollToLine(i);
    }
  }

  const userScrolled = () => { if (!audio.paused && following) { following = false; $("follow").hidden = false; } };
  addEventListener("wheel", userScrolled, { passive: true });
  addEventListener("touchmove", userScrolled, { passive: true });
  addEventListener("keydown", (e) => { if (["PageUp", "PageDown", "Home", "End"].includes(e.key)) userScrolled(); });
  $("follow").addEventListener("click", () => { following = true; $("follow").hidden = true; scrollToLine(curLine); });

  /* ---- Visuals ----------------------------------------------------------- */
  const unitFmt = (v, unit, d, approx) => {
    const n = d != null ? Number(v).toFixed(d) : String(v);
    const s = unit === "%" ? `${n}%` : unit === "x" ? `${n}x` : unit === "£bn" ? `£${n}bn` : unit ? `${n} ${unit}` : n;
    return (approx ? "c. " : "") + s;
  };
  const tipAttr = (title, body) => `tabindex="0" data-tip="${esc(`<b>${esc(title)}</b>${esc(body || "")}`)}"`;
  const note = (v) => (v.note ? `<p class="note">${esc(v.note)}</p>` : "");

  const R = {
    tombstone: (v) => `
      <div class="tomb">
        ${v.kicker ? `<p class="t-kicker">${esc(v.kicker)}</p>` : ""}
        <p class="t-name">${esc(v.name)}</p>
        <hr class="t-rule">
        ${v.sub ? `<p class="t-sub">${esc(v.sub)}</p>` : ""}
        ${(v.lines || []).map((l) => `<p class="t-line">${esc(l)}</p>`).join("")}
        ${v.date ? `<p class="t-date">${esc(v.date)}</p>` : ""}
      </div>${note(v)}`,

    keynumbers: (v) => {
      const val = (it) => `${it.approx ? '<span class="approx">c.</span>' : ""}${esc(it.value)}`;
      if (v.items.length === 1) {
        const it = v.items[0];
        return `<div class="pull"><span class="p-val">${val(it)}</span><span class="p-lab">${esc(it.label)}</span></div>${note(v)}`;
      }
      return `<dl class="terms">${v.items.map((it) => `<div><dt>${esc(it.label)}</dt><dd>${val(it)}</dd></div>`).join("")}</dl>${note(v)}`;
    },

    bars: (v) => {
      const max = Math.max(...v.items.map((i) => i.value), v.band ? v.band.to : 0) * 1.08;
      const pct = (x) => (x / max) * 100;
      const band = v.band ? `<div class="band" style="left:${pct(v.band.from)}%;width:${pct(v.band.to - v.band.from)}%"></div>` : "";
      return `
      <div class="bars" role="list">
        ${v.items.map((it) => {
          const val = unitFmt(it.value, v.unit, v.decimals, it.approx);
          return `<div class="bar-row" role="listitem">
            <div class="bar-lab"><span>${esc(it.label)}</span><b>${esc(val)}</b></div>
            <div class="bar-track">${band}<div class="bar" style="width:${pct(it.value)}%" ${tipAttr(it.label, val)} aria-label="${esc(it.label)}: ${esc(val)}"></div></div>
          </div>`; }).join("")}
      </div>
      ${v.band ? `<p class="band-key"><i aria-hidden="true"></i>${esc(v.band.label)}</p>` : ""}${note(v)}`;
    },

    waterfall: (v) => {
      let run = 0;
      const segs = v.steps.map((s) => {
        let from, to;
        if (s.kind === "total") { from = 0; to = s.value; run = s.value; }
        else if (s.kind === "add") { from = run; to = run + s.value; run = to; }
        else { from = run - s.value; to = run; run = from; }
        return { ...s, from, to, level: run };
      });
      const max = Math.max(...segs.map((s) => s.to)) * 1.06;
      const pct = (x) => (x / max) * 100;
      return `
      <div class="wf">
        ${segs.map((s, i) => {
          const val = (s.kind === "add" ? "+" : s.kind === "sub" ? "−" : "") + unitFmt(s.value, v.unit, v.decimals);
          const link = i < segs.length - 1 ? `<div class="wf-link" style="bottom:${pct(s.level)}%"></div>` : "";
          return `<div class="wf-col">
            <div class="wf-val">${esc(val)}</div>
            <div class="wf-plot">
              <div class="wf-bar ${s.kind}" style="bottom:${pct(s.from)}%;height:${pct(s.to - s.from)}%" ${tipAttr(s.label, " " + val)} aria-label="${esc(s.label)}: ${esc(val)}"></div>${link}
            </div>
            <div class="wf-lab">${esc(s.label)}</div>
          </div>`; }).join("")}
      </div>${note(v)}`;
    },

    table: (v) => {
      const al = (j) => ((v.align || [])[j] === "right" ? ' class="r"' : "");
      return `
      <div class="tbl-wrap"><table class="tbl">
        <thead><tr>${v.columns.map((c, j) => `<th${al(j)} scope="col">${esc(c)}</th>`).join("")}</tr></thead>
        <tbody>${v.rows.map((r, i) => `<tr${i === v.highlight ? ' class="hl"' : ""}>${r.map((c, j) =>
          `<td${al(j)}>${c === "" ? "–" : esc(c)}${i === v.highlight && j === 0 && v.highlightLabel ? `<span class="hl-note">${esc(v.highlightLabel)}</span>` : ""}</td>`).join("")}</tr>`).join("")}</tbody>
      </table></div>${note(v)}`;
    },

    steps: (v) => {
      const n = v.items.length;
      return `<ol class="funnel">${v.items.map((it, i) => {
        const label = typeof it === "string" ? it : it.label, detail = typeof it === "string" ? "" : it.detail;
        return `<li><span class="f-band" aria-hidden="true"><i style="width:${100 - (i * 70) / Math.max(1, n - 1)}%"></i></span><span class="f-text"><b>${esc(label)}</b>${detail ? `<span>${esc(detail)}</span>` : ""}</span></li>`;
      }).join("")}</ol>${note(v)}`;
    },

    formula: (v) => `<p class="formula">${esc(v.formula)}</p>${note(v)}`,

    football: (v) => {
      const lo = Math.min(...v.bars.map((b) => b.from)), hi = Math.max(...v.bars.map((b) => b.to));
      const pad = (hi - lo) * 0.08, a = lo - pad, b = hi + pad;
      const pct = (x) => ((x - a) / (b - a)) * 100;
      return `
      <div class="ff">
        ${v.marker ? `<div class="ff-marker" style="left:${pct(v.marker.value)}%"><span>${esc(v.marker.label)}</span></div>` : ""}
        ${v.bars.map((r) => `<div class="ff-row"><span class="ff-lab">${esc(r.label)}</span>
          <div class="ff-track"><div class="ff-bar" style="left:${pct(r.from)}%;width:${pct(r.to) - pct(r.from)}%" ${tipAttr(r.label, v.illustrative ? " Illustrative range" : "")} aria-label="${esc(r.label)}"></div></div></div>`).join("")}
      </div>
      <div class="ff-axis" aria-hidden="true"><span>Lower value</span><span>Higher value</span></div>${note(v)}`;
    },

    quizcall: (v) => `<div class="qcall"><p>${esc(v.text)}</p><a class="btn" href="#quiz">Go to the quiz</a></div>`,
  };

  const cover = () => `
    <div class="fig"><div class="tomb cover">
      <p class="t-kicker">The Deal Desk, episode ${esc(D.number)}</p>
      <p class="t-name">${esc(D.title)}</p>
      <hr class="t-rule">
      <p class="t-sub">${V.length ? "Press play. Visuals appear here as Marco reaches them." : "Press play to listen."}</p>
    </div></div>`;

  let fig = null, autoFig = null, pinned = false;

  function showFig(k, animate) {
    if (k === fig) return;
    fig = k;
    const body = $("stage-body");
    if (k < 0) body.innerHTML = cover();
    else {
      const v = V[k];
      const render = R[v.type];
      body.innerHTML = `<figure class="fig">
        ${v.title ? `<h3>${esc(v.title)}</h3>` : ""}
        ${render ? render(v) : `<p class="note">Unknown visual type: ${esc(v.type)}</p>`}
      </figure>`;
    }
    $("fig-count").innerHTML = k < 0
      ? `${V.length} visuals in this episode`
      : `<b>Fig. ${k + 1}</b> of ${V.length}`;
    $("fig-prev").disabled = k < 0;
    $("fig-next").disabled = k >= V.length - 1;
  }

  $("fig-prev").addEventListener("click", () => { pinned = true; showFig(Math.max(-1, fig - 1), true); });
  $("fig-next").addEventListener("click", () => { pinned = true; showFig(Math.min(V.length - 1, fig + 1), true); });
  $("stage-toggle").addEventListener("click", (e) => {
    const collapsed = $("stage").classList.toggle("collapsed");
    e.currentTarget.textContent = collapsed ? "Show" : "Hide";
    e.currentTarget.setAttribute("aria-expanded", String(!collapsed));
  });

  function updateFig(t) {
    const a = lastStartBefore(figStarts, t);
    if (a !== autoFig) { const first = autoFig === null; autoFig = a; pinned = false; showFig(a, !first); }
    else if (!pinned && fig !== a) showFig(a, false);
  }

  /* ---- Tooltip ----------------------------------------------------------- */
  const tip = $("tip");
  const placeTip = (x, y) => {
    const r = tip.getBoundingClientRect();
    tip.style.left = `${Math.min(innerWidth - r.width - 8, Math.max(8, x + 12))}px`;
    tip.style.top = `${Math.max(8, y - r.height - 12)}px`;
  };
  document.addEventListener("pointerover", (e) => {
    const t = e.target.closest("[data-tip]");
    if (!t) return;
    tip.innerHTML = t.dataset.tip; tip.hidden = false; placeTip(e.clientX, e.clientY);
  });
  document.addEventListener("pointermove", (e) => { if (!tip.hidden && e.target.closest("[data-tip]")) placeTip(e.clientX, e.clientY); });
  document.addEventListener("pointerout", (e) => { if (e.target.closest("[data-tip]")) tip.hidden = true; });
  document.addEventListener("focusin", (e) => {
    const t = e.target.closest?.("[data-tip]");
    if (!t) return;
    const r = t.getBoundingClientRect();
    tip.innerHTML = t.dataset.tip; tip.hidden = false; placeTip(r.left + r.width / 2, r.top);
  });
  document.addEventListener("focusout", () => { tip.hidden = true; });
  addEventListener("scroll", () => { tip.hidden = true; }, { passive: true });

  /* ---- Player ------------------------------------------------------------- */
  const seekEl = $("seek");
  let dragging = false, lastSave = 0;

  function seek(t) { audio.currentTime = Math.max(0, Math.min(duration() - 0.1, t)); update(); }

  function drawTicks() {
    $("ticks").innerHTML = figStarts.map((s) => `<i style="left:${(s / duration()) * 100}%"></i>`).join("");
  }

  let lastT = 0;
  function update() {
    const t = audio.currentTime, d = duration();
    if (!revealed && !audio.paused) {
      // Only when playback runs across the pause line, not when the listener seeks past it.
      if (pauseAt != null && lastT < pauseAt && t >= pauseAt && t - lastT < 1.5) {
        audio.pause(); audio.currentTime = pauseAt; openGate();
      } else if (t >= lines[Qz.answersLine].start - 0.05 && lastT < lines[Qz.answersLine].start) {
        revealAnswers();
      }
    }
    lastT = audio.currentTime;
    setLine(lastStartBefore(lineStarts, t));
    updateFig(t);
    $("cur").textContent = fmtTime(t);
    const p = d ? t / d : 0;
    $("fill").style.width = `${p * 100}%`;
    if (!dragging) seekEl.value = Math.round(p * 1000);
    seekEl.setAttribute("aria-valuetext", `${fmtTime(t)} of ${fmtTime(d)}`);
    if (Math.abs(t - lastSave) > 5) { lastSave = t; store.set(`dd-pos-${D.id}`, t.toFixed(1)); }
  }

  function loop() { update(); if (!audio.paused) requestAnimationFrame(loop); }

  $("play").addEventListener("click", () => (audio.paused ? audio.play() : audio.pause()));
  $("back").addEventListener("click", () => seek(audio.currentTime - 15));
  $("fwd").addEventListener("click", () => seek(audio.currentTime + 15));
  audio.addEventListener("play", () => {
    document.body.classList.add("playing"); $("play").setAttribute("aria-label", "Pause");
    if (following && curLine >= 0) scrollToLine(curLine);
    requestAnimationFrame(loop);
  });
  audio.addEventListener("pause", () => {
    document.body.classList.remove("playing"); $("play").setAttribute("aria-label", "Play");
    store.set(`dd-pos-${D.id}`, audio.currentTime.toFixed(1));
  });
  audio.addEventListener("seeked", update);
  // timeupdate keeps firing in background tabs and with the screen off, where
  // requestAnimationFrame stops; the quiz gate depends on it.
  audio.addEventListener("timeupdate", update);
  audio.addEventListener("loadedmetadata", () => {
    $("dur").textContent = fmtTime(duration());
    drawTicks();
    // A #t=SECONDS link wins over the remembered position.
    const linked = parseFloat((location.hash.match(/^#t=([\d.]+)$/) || [])[1]);
    const saved = parseFloat(store.get(`dd-pos-${D.id}`));
    if (linked >= 0) audio.currentTime = Math.min(linked, duration() - 0.1);
    else if (saved > 5 && saved < duration() - 10 && audio.currentTime < 1) audio.currentTime = saved;
    update();
  });

  seekEl.addEventListener("input", () => { dragging = true; seek((seekEl.value / 1000) * duration()); });
  seekEl.addEventListener("change", () => { dragging = false; });

  const rates = [1, 1.25, 1.5, 2, 0.75];
  const setRate = (r) => { audio.playbackRate = r; $("rate").textContent = `${r}×`; store.set("dd-rate", r); };
  $("rate").addEventListener("click", () => setRate(rates[(rates.indexOf(audio.playbackRate) + 1) % rates.length] || 1));
  const savedRate = parseFloat(store.get("dd-rate"));
  if (rates.includes(savedRate)) setRate(savedRate);

  document.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const tag = e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA") return;
    if (e.key === " " && tag !== "BUTTON" && tag !== "A") { e.preventDefault(); audio.paused ? audio.play() : audio.pause(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); seek(audio.currentTime - 5); }
    else if (e.key === "ArrowRight") { e.preventDefault(); seek(audio.currentTime + 5); }
  });

  if ("mediaSession" in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({ title: D.title, artist: "The Deal Desk", album: `Episode ${D.number}` });
    const ms = navigator.mediaSession;
    ms.setActionHandler("play", () => audio.play());
    ms.setActionHandler("pause", () => audio.pause());
    ms.setActionHandler("seekbackward", () => seek(audio.currentTime - 15));
    ms.setActionHandler("seekforward", () => seek(audio.currentTime + 15));
  }

  /* ---- Quiz ----------------------------------------------------------------- */
  function buildQuiz() {
    const Q = D.quiz && D.quiz.questions;
    const sec = $("quiz");
    if (!Q || !Q.length) { sec.remove(); return; }
    const answers = new Array(Q.length).fill(null);
    sec.innerHTML = `
      <div class="quiz-head"><h2 id="quiz-h">Quiz</h2><p class="score" id="score" aria-live="polite"></p></div>
      <ol class="qcards">${Q.map((q, i) => `
        <li class="qcard" data-q="${i}">
          <p class="q-n">Question ${i + 1} of ${Q.length}</p>
          <p class="q">${esc(q.q)}</p>
          <div class="opts" role="group" aria-label="Answers to question ${i + 1}">
            ${q.options.map((o, j) => `<button type="button" class="opt" data-o="${j}"><span>${esc(o)}</span><span class="tag"></span></button>`).join("")}
          </div>
          <p class="verdict" hidden></p>
        </li>`).join("")}
      </ol>
      <div class="quiz-actions">
        ${D.quiz.answersLine != null ? '<button type="button" class="btn" id="hear">Hear Marco\'s answers</button>' : ""}
        <button type="button" class="btn ghost" id="retry" hidden>Start the quiz again</button>
      </div>`;

    const score = () => {
      const done = answers.filter((a) => a !== null).length;
      const right = answers.filter((a, i) => a === Q[i].correct).length;
      $("score").innerHTML = done === Q.length
        ? `You scored <b>${right} of ${Q.length}</b>`
        : done ? `${right} of ${done} answered correctly` : `${Q.length} questions`;
      $("retry").hidden = done === 0;
    };

    sec.addEventListener("click", (e) => {
      const opt = e.target.closest(".opt");
      if (!opt || opt.disabled) return;
      const card = opt.closest(".qcard"), i = +card.dataset.q, j = +opt.dataset.o, q = Q[i];
      answers[i] = j;
      card.querySelectorAll(".opt").forEach((b) => {
        const o = +b.dataset.o;
        b.disabled = true;
        if (o === q.correct) { b.classList.add("right"); b.querySelector(".tag").textContent = o === j ? "Your answer, correct" : "Correct answer"; }
        else if (o === j) { b.classList.add("wrong"); b.querySelector(".tag").textContent = "Your answer"; }
        else b.classList.add("dim");
      });
      const v = card.querySelector(".verdict");
      v.innerHTML = j === q.correct
        ? `<b>Correct.</b> ${esc(q.explain)}`
        : `<b>Not quite.</b> The answer is ${esc(q.options[q.correct])}. ${esc(q.explain)}`;
      v.hidden = false;
      score();
    });
    $("retry").addEventListener("click", () => {
      answers.fill(null);
      sec.querySelectorAll(".opt").forEach((b) => { b.disabled = false; b.className = "opt"; b.querySelector(".tag").textContent = ""; });
      sec.querySelectorAll(".verdict").forEach((v) => { v.hidden = true; });
      score();
      sec.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" });
    });
    const hear = $("hear");
    if (hear) hear.addEventListener("click", () => {
      revealAnswers(); following = true; $("follow").hidden = true;
      seek(lines[D.quiz.answersLine].start); audio.play();
    });
    score();
  }

  /* ---- Sources ------------------------------------------------------------- */
  if (D.sources && D.sources.length) {
    $("source-list").innerHTML = D.sources.map((src) => `<li><a href="${esc(src.url)}" rel="noopener" target="_blank">${esc(src.label)}</a></li>`).join("");
    $("sources").hidden = false;
  }

  /* ---- Init ------------------------------------------------------------------ */
  $("dur").textContent = fmtTime(D.duration);
  drawTicks();
  buildQuiz();
  update();
})();
