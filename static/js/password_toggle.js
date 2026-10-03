document.querySelectorAll(".password-toggle[data-target]").forEach(function (button) {
    const input = document.getElementById(button.dataset.target);
    const icon = button.querySelector("i");

    if (!input || !icon) return;

    let savedSelection = null;

    button.setAttribute("aria-controls", input.id);
    button.setAttribute("aria-pressed", "false");

    function captureSelection(restoreFocus) {
        savedSelection = {
            start: input.selectionStart,
            end: input.selectionEnd,
            restoreFocus: restoreFocus
        };
    }

    button.addEventListener("pointerdown", function () {
        if (document.activeElement === input) {
            captureSelection(true);
        }
    });

    button.addEventListener("mousedown", function (event) {
        if (document.activeElement === input) {
            captureSelection(true);
            event.preventDefault();
        }
    });

    input.addEventListener("blur", function () {
        if (document.activeElement === button) {
            captureSelection(false);
        } else {
            savedSelection = null;
        }
    });

    button.addEventListener("click", function () {
        const isVisible = input.type === "password";
        const selection = savedSelection || {
            start: input.selectionStart,
            end: input.selectionEnd,
            restoreFocus: document.activeElement === input
        };
        savedSelection = null;

        input.type = isVisible ? "text" : "password";
        icon.className = isVisible ? "bi bi-eye" : "bi bi-eye-slash";
        button.setAttribute("aria-label", isVisible ? "Hide password" : "Show password");
        button.setAttribute("title", isVisible ? "Hide password" : "Show password");
        button.setAttribute("aria-pressed", String(isVisible));

        if (selection.start !== null && selection.end !== null) {
            window.requestAnimationFrame(function () {
                if (selection.restoreFocus) input.focus({ preventScroll: true });
                input.setSelectionRange(selection.start, selection.end);
            });
        }
    });
});
