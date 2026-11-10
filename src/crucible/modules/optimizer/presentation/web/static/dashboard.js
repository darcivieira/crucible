"use strict";

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy-target]");
  if (!button) return;
  const source = document.getElementById(button.dataset.copyTarget);
  const label = button.querySelector("[data-copy-label]");
  const status = document.getElementById("copy-status");
  if (!source || !label) return;
  try {
    await navigator.clipboard.writeText(source.textContent);
    label.textContent = "Copied";
    status.textContent = "Prompt copied to clipboard.";
  } catch {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(source);
    selection.removeAllRanges();
    selection.addRange(range);
    label.textContent = "Text selected";
    status.textContent = "Clipboard unavailable. The prompt is selected; use your copy shortcut.";
  }
  window.setTimeout(() => { label.textContent = "Copy prompt"; }, 2500);
});
