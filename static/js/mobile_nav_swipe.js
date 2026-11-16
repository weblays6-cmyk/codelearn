document.addEventListener("DOMContentLoaded", function () {
    const mobileNav = document.querySelector(".mobile-nav");
    const mobileViewport = window.matchMedia("(max-width: 600px)");

    if (!mobileNav) {
        return;
    }

    let touchStart = null;

    document.addEventListener("touchstart", function (event) {
        if (!mobileViewport.matches || event.touches.length !== 1) {
            touchStart = null;
            return;
        }

        const target = event.target;
        if (
            target.closest(
                "input, textarea, select, button, a, [contenteditable='true'], " +
                "[role='dialog'], .mobile-drawer-overlay:not([hidden]), " +
                ".sidebar, .monaco-editor, .CodeMirror"
            )
        ) {
            touchStart = null;
            return;
        }

        let ancestor = target;
        while (ancestor && ancestor !== document.body) {
            const style = window.getComputedStyle(ancestor);
            if (
                (style.overflowX === "auto" || style.overflowX === "scroll") &&
                ancestor.scrollWidth > ancestor.clientWidth + 1
            ) {
                touchStart = null;
                return;
            }
            ancestor = ancestor.parentElement;
        }

        touchStart = {
            x: event.touches[0].clientX,
            y: event.touches[0].clientY
        };
    }, { passive: true });

    document.addEventListener("touchend", function (event) {
        if (!touchStart || !event.changedTouches.length || !mobileViewport.matches) {
            touchStart = null;
            return;
        }

        const deltaX = event.changedTouches[0].clientX - touchStart.x;
        const deltaY = event.changedTouches[0].clientY - touchStart.y;
        touchStart = null;

        if (Math.abs(deltaX) < 70 || Math.abs(deltaY) > 80) {
            return;
        }

        const links = Array.from(
            mobileNav.querySelectorAll(".mobile-nav-link")
        );
        const activeIndex = links.findIndex(function (link) {
            return link.classList.contains("active");
        });
        if (activeIndex === -1) {
            return;
        }

        const nextIndex = activeIndex + (deltaX < 0 ? 1 : -1);
        if (nextIndex >= 0 && nextIndex < links.length) {
            window.location.assign(links[nextIndex].href);
        }
    }, { passive: true });

    mobileViewport.addEventListener("change", function () {
        touchStart = null;
    });
});
