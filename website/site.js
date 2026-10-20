"use strict";
for (const button of document.querySelectorAll("[data-copy]")) {
  button.addEventListener("click", async () => {
    const code = document.getElementById(button.dataset.copy);
    const status = button.closest(".code-card").querySelector("[role=status]");
    try {
      await navigator.clipboard.writeText(code.textContent);
      status.textContent = "Commands copied. Edit .env before starting the stack.";
    } catch {
      status.textContent = "Select the commands above and copy them manually.";
    }
  });
}
