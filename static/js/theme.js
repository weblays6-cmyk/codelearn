// =========================
// CODELEARN HUB THEME
// =========================

function applyTheme(theme) {

    const body = document.body;
    const icon = document.getElementById("themeIcon");

    if (theme === "light") {

        body.classList.add("light-theme");

        if (icon) {
            icon.className = "bi bi-sun-fill";
        }

    } else {

        body.classList.remove("light-theme");

        if (icon) {
            icon.className = "bi bi-moon-fill";
        }
    }

    localStorage.setItem("codelearn-theme", theme);
}


// =========================
// TOGGLE THEME
// =========================

function toggleTheme() {

    const isLight =
        document.body.classList.contains("light-theme");

    if (isLight) {
        applyTheme("dark");
    } else {
        applyTheme("light");
    }
}


// =========================
// LOAD SAVED THEME
// =========================

document.addEventListener("DOMContentLoaded", function () {

    const savedTheme =
        localStorage.getItem("codelearn-theme") || "light";

    applyTheme(savedTheme);

    const drawer = document.getElementById("sidebar");
    const menuToggle = document.getElementById("mobileMenuToggle");
    const drawerClose = document.getElementById("mobileDrawerClose");
    const drawerOverlay = document.getElementById("mobileDrawerOverlay");

    if (!drawer || !menuToggle || !drawerClose || !drawerOverlay) return;

    const mobileViewport = window.matchMedia("(max-width: 760px)");
    let previousOverflow = "";
    let touchStart = null;

    function closeDrawer(restoreFocus) {
        document.body.classList.remove("mobile-drawer-open");
        menuToggle.setAttribute("aria-expanded", "false");
        menuToggle.setAttribute("aria-label", "Open navigation menu");
        drawerOverlay.hidden = true;

        if (mobileViewport.matches) {
            drawer.setAttribute("aria-hidden", "true");
            drawer.setAttribute("inert", "");
            document.body.style.overflow = previousOverflow;
        } else {
            drawer.removeAttribute("aria-hidden");
            drawer.removeAttribute("inert");
        }

        if (restoreFocus) menuToggle.focus();
    }

    function openDrawer() {
        if (!mobileViewport.matches) return;

        previousOverflow = document.body.style.overflow;
        document.body.classList.add("mobile-drawer-open");
        document.body.style.overflow = "hidden";
        drawer.setAttribute("aria-hidden", "false");
        drawer.removeAttribute("inert");
        drawerOverlay.hidden = false;
        menuToggle.setAttribute("aria-expanded", "true");
        menuToggle.setAttribute("aria-label", "Close navigation menu");
        drawerClose.focus();
    }

    function syncDrawerForViewport() {
        if (mobileViewport.matches) {
            closeDrawer(false);
        } else {
            document.body.classList.remove("mobile-drawer-open");
            document.body.style.overflow = previousOverflow;
            drawer.removeAttribute("aria-hidden");
            drawer.removeAttribute("inert");
            drawerOverlay.hidden = true;
            menuToggle.setAttribute("aria-expanded", "false");
            menuToggle.setAttribute("aria-label", "Open navigation menu");
        }
    }

    menuToggle.addEventListener("click", function () {
        if (menuToggle.getAttribute("aria-expanded") === "true") {
            closeDrawer(true);
        } else {
            openDrawer();
        }
    });

    drawerClose.addEventListener("click", function () {
        closeDrawer(true);
    });

    drawerOverlay.addEventListener("click", function () {
        closeDrawer(true);
    });

    drawer.addEventListener("click", function (event) {
        if (event.target.closest("a, button[type='submit']")) {
            closeDrawer(false);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && menuToggle.getAttribute("aria-expanded") === "true") {
            closeDrawer(true);
        }
    });

    document.addEventListener("touchstart", function (event) {
        if (event.touches.length !== 1) {
            touchStart = null;
            return;
        }

        const target = event.target;
        if (target.closest(".danger-modal-backdrop:not([hidden])")) {
            touchStart = null;
            return;
        }

        if (target.closest("input, textarea, select, button, [contenteditable='true'], .monaco-editor, .CodeMirror")) {
            touchStart = null;
            return;
        }

        let ancestor = target;
        while (ancestor && ancestor !== document.body) {
            const style = window.getComputedStyle(ancestor);
            if ((style.overflowX === "auto" || style.overflowX === "scroll") &&
                ancestor.scrollWidth > ancestor.clientWidth + 1) {
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
        if (!touchStart || !event.changedTouches.length) return;

        const deltaX = event.changedTouches[0].clientX - touchStart.x;
        const deltaY = event.changedTouches[0].clientY - touchStart.y;
        const startX = touchStart.x;
        touchStart = null;

        if (Math.abs(deltaX) < 80 || Math.abs(deltaY) > 60) return;

        if (menuToggle.getAttribute("aria-expanded") === "true") {
            if (startX >= window.innerWidth - 28 && deltaX < 0) closeDrawer(true);
        } else if (startX <= 24 && deltaX > 0) {
            openDrawer();
        }
    }, { passive: true });

    mobileViewport.addEventListener("change", syncDrawerForViewport);
    syncDrawerForViewport();
});