/* "Next episode" countdown. The release time is 07:30 Europe/Rome on the episode's date;
   it is converted to the viewer's local time here, in the browser. Without JavaScript the
   box still opens and shows the date as plain text. */
(() => {
  "use strict";

  // Offset of a time zone from UTC at a given instant, in minutes (handles summer time).
  function tzOffset(instant, timeZone) {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }).formatToParts(instant).reduce((o, p) => ((o[p.type] = p.value), o), {});
    const asUtc = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour, +parts.minute, +parts.second);
    return (asUtc - instant.getTime()) / 60000;
  }

  // The UTC instant of a wall-clock time in a time zone.
  function zonedInstant(dateStr, timeStr, timeZone) {
    const [y, m, d] = dateStr.split("-").map(Number);
    const [hh, mm] = timeStr.split(":").map(Number);
    const guess = Date.UTC(y, m - 1, d, hh, mm);
    let t = guess - tzOffset(new Date(guess), timeZone) * 60000;
    t = guess - tzOffset(new Date(t), timeZone) * 60000;  // second pass for days when clocks change
    return new Date(t);
  }

  const pad = (n) => String(n).padStart(2, "0");
  function span(ms) {
    const s = Math.floor(ms / 1000), d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60), sec = s % 60;
    return (d ? `${d} d ` : "") + `${h} h ${pad(m)} min ${pad(sec)} s`;
  }

  document.querySelectorAll(".next-ep[data-date]").forEach((box) => {
    const release = zonedInstant(box.dataset.date, box.dataset.time, box.dataset.tz);
    const when = box.querySelector(".next-when"), count = box.querySelector(".next-count");
    const local = release.toLocaleString(undefined, {
      weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZoneName: "short",
    });
    when.textContent = `Releases ${local}, your time.`;
    count.hidden = false;

    let timer = null;
    function tick() {
      const left = release.getTime() - Date.now();
      if (left > 0) count.textContent = `In ${span(left)}`;
      else if (left > -3 * 3600 * 1000) count.textContent = "Publishing now, refresh in a few minutes.";
      else count.textContent = "Running late today.";
    }
    tick();
    box.addEventListener("toggle", () => {
      clearInterval(timer);
      if (box.open) { tick(); timer = setInterval(tick, 1000); }
    });
  });
})();
