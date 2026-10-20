"use strict";
(() => {
  const key = "system-monitoring-theme";
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  let saved = null;
  try {
    saved = localStorage.getItem(key);
  } catch {
    // Theme preference is optional when storage is unavailable.
  }

  const current = () => saved || (media.matches ? "dark" : "light");
  const updateButtons = (theme) => {
    for (const button of document.querySelectorAll("[data-theme-toggle]")) {
      const next = theme === "dark" ? "light" : "dark";
      button.setAttribute("aria-label", `Use ${next} mode`);
      button.setAttribute("title", `Use ${next} mode`);
      button.setAttribute("aria-pressed", String(theme === "dark"));
      const label = button.querySelector("[data-theme-label]");
      if (label) label.textContent = `${next[0].toUpperCase()}${next.slice(1)} mode`;
      const icon = button.querySelector("[data-theme-icon]");
      if (icon) icon.textContent = theme === "dark" ? "☀" : "☾";
    }
  };
  const apply = (theme) => {
    document.documentElement.dataset.theme = theme;
    const color = theme === "dark" ? "#0d1714" : "#102c26";
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", color);
    updateButtons(theme);
  };

  apply(current());
  document.addEventListener("DOMContentLoaded", () => {
    apply(current());
    for (const button of document.querySelectorAll("[data-theme-toggle]")) {
      button.addEventListener("click", () => {
        saved = current() === "dark" ? "light" : "dark";
        try {
          localStorage.setItem(key, saved);
        } catch {
          // The active page still changes even if persistence is unavailable.
        }
        apply(saved);
      });
    }
  });
  media.addEventListener("change", () => {
    if (!saved) apply(current());
  });
})();
