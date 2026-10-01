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

});