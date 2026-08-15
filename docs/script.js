const copyButton = document.querySelector("[data-copy]");

if (copyButton) {
  copyButton.addEventListener("click", async () => {
    const address = copyButton.dataset.copy;

    try {
      await navigator.clipboard.writeText(address);
      copyButton.textContent = "Copied";
      window.setTimeout(() => {
        copyButton.textContent = "Copy address";
      }, 1800);
    } catch {
      const addressElement = document.querySelector("#lightning-address");
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(addressElement);
      selection.removeAllRanges();
      selection.addRange(range);
    }
  });
}
