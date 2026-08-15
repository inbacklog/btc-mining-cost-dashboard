const copyButton = document.querySelector("[data-copy]");

function copyWithFallback(text) {
  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.opacity = "0";
  document.body.appendChild(textArea);
  textArea.select();

  const copied = document.execCommand("copy");
  textArea.remove();

  if (!copied) {
    throw new Error("Clipboard copy was unavailable");
  }
}

if (copyButton) {
  copyButton.addEventListener("click", async () => {
    const address = copyButton.dataset.copy;

    try {
      if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(address);
        } catch {
          copyWithFallback(address);
        }
      } else {
        copyWithFallback(address);
      }

      copyButton.textContent = "Copied";
    } catch {
      const addressElement = document.querySelector("#lightning-address");
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(addressElement);
      selection.removeAllRanges();
      selection.addRange(range);
      copyButton.textContent = "Address selected";
    }
  });
}
