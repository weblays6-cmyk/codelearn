document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy-code]");
    if (!button) return;
    const code = button.parentElement.querySelector("code");
    try {
        await navigator.clipboard.writeText(code.textContent);
        button.textContent = "Copied";
        window.setTimeout(() => {
            button.textContent = "Copy";
        }, 1500);
    } catch (error) {
        button.textContent = "Copy failed";
    }
});
