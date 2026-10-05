/* Applies a saved Light/Dark choice before first paint (kept external for the CSP). */
try { var t = localStorage.getItem("dd-theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; } catch (e) {}
