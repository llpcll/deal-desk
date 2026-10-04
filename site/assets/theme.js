/* Appearance switch: Auto follows the system setting; Light and Dark override it. */
(() => {
  const root = document.documentElement;
  const buttons = document.querySelectorAll("[data-set-theme]");
  function apply(t) {
    if (t === "light" || t === "dark") root.dataset.theme = t; else delete root.dataset.theme;
    try { t === "light" || t === "dark" ? localStorage.setItem("dd-theme", t) : localStorage.removeItem("dd-theme"); } catch { /* storage unavailable */ }
    buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.setTheme === t)));
  }
  buttons.forEach((b) => b.addEventListener("click", () => apply(b.dataset.setTheme)));
  apply(root.dataset.theme || "system");
})();
