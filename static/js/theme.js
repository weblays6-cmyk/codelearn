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


document.addEventListener("DOMContentLoaded", function () {
    const searchShell = document.querySelector(".workspace-search-shell");
    const searchForm = document.querySelector(".workspace-search");
    const searchInput = document.getElementById("globalSearchInput");
    const clearButton = document.getElementById("workspaceSearchClear");
    const searchResults = document.getElementById("globalSearchResults");
    const userMenuToggle = document.getElementById("userMenuToggle");
    const userDropdown = document.getElementById("userDropdown");

    const GLOBAL_SEARCH_URL = '/global-search/';

    if (searchShell && searchForm && searchInput && searchResults) {
        let debounceTimer = null;
        let selectedIndex = -1;

        function setSearchResultsVisible(visible) {
            if (!searchResults) return;
            searchResults.hidden = !visible;
            if (visible) {
                searchResults.setAttribute("aria-expanded", "true");
            } else {
                searchResults.setAttribute("aria-expanded", "false");
            }
        }

        function escapeHtml(value) {
            return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
        }

        function renderSearchResults(payload) {
            const navigationResults = Array.isArray(payload.navigation) ? payload.navigation : [];
            const contentResults = Array.isArray(payload.content) ? payload.content : [];
            const allResults = [...navigationResults, ...contentResults];

            if (!allResults.length) {
                searchResults.innerHTML = '<div class="global-search-empty">No results found</div>';
                selectedIndex = -1;
                setSearchResultsVisible(true);
                return;
            }

            const markup = [];
            if (navigationResults.length) {
                markup.push('<div class="global-search-group"><div class="global-search-group-title">Navigation</div>');
                navigationResults.forEach((item, index) => {
                    const safeUrl = escapeHtml(item.url || '#');
                    const safeLabel = escapeHtml(item.label || '');
                    const safeDescription = escapeHtml(item.description || 'Open result');
                    const safeIcon = escapeHtml(item.icon || 'app');
                    markup.push(`
                        <button type="button" class="global-search-item${index === 0 ? ' is-active' : ''}" data-url="${safeUrl}" data-group="navigation" data-index="${index}" aria-label="Open ${safeLabel}">
                            <span class="global-search-item-icon"><i class="bi bi-${safeIcon}" aria-hidden="true"></i></span>
                            <span class="global-search-item-copy">
                                <span class="global-search-item-title">${safeLabel}</span>
                                <span class="global-search-item-description">${safeDescription}</span>
                            </span>
                        </button>
                    `);
                });
                markup.push('</div>');
            }

            if (contentResults.length) {
                markup.push('<div class="global-search-group"><div class="global-search-group-title">Content</div>');
                contentResults.forEach((item, index) => {
                    const resultIndex = navigationResults.length + index;
                    const safeUrl = escapeHtml(item.url || '#');
                    const safeLabel = escapeHtml(item.label || '');
                    const safeCategory = escapeHtml(item.category || 'Content');
                    const safeDescription = escapeHtml(item.description || '');
                    const safeIcon = escapeHtml(item.icon || 'book');
                    markup.push(`
                        <button type="button" class="global-search-item${resultIndex === 0 ? ' is-active' : ''}" data-url="${safeUrl}" data-group="content" data-index="${resultIndex}" aria-label="Open ${safeLabel}">
                            <span class="global-search-item-icon"><i class="bi bi-${safeIcon}" aria-hidden="true"></i></span>
                            <span class="global-search-item-copy">
                                <span class="global-search-item-title">${safeLabel}</span>
                                <span class="global-search-item-description">${safeCategory}: ${safeDescription}</span>
                            </span>
                        </button>
                    `);
                });
                markup.push('</div>');
            }

            searchResults.innerHTML = markup.join('');
            selectedIndex = 0;
            setSearchResultsVisible(true);

            const items = searchResults.querySelectorAll('.global-search-item');
            items.forEach((item) => {
                item.addEventListener('click', () => {
                    if (item.dataset.url) {
                        window.location.href = item.dataset.url;
                    }
                });
            });
        }

        function clearSearchState() {
            selectedIndex = -1;
            if (searchResults) {
                searchResults.innerHTML = '';
                setSearchResultsVisible(false);
            }
        }

        function navigateSelectedResult() {
            const activeItem = searchResults.querySelector('.global-search-item.is-active');
            if (activeItem && activeItem.dataset.url) {
                window.location.href = activeItem.dataset.url;
                return true;
            }
            return false;
        }

        function moveSelection(direction) {
            const allItems = Array.from(searchResults.querySelectorAll('.global-search-item'));
            if (!allItems.length) return;

            const nextIndex = selectedIndex + direction;
            const boundedIndex = Math.max(0, Math.min(nextIndex, allItems.length - 1));
            selectedIndex = boundedIndex;

            allItems.forEach((item, index) => {
                item.classList.toggle('is-active', index === boundedIndex);
            });
        }

        function fetchSearchResults() {
            const query = searchInput.value.trim();
            if (!query) {
                clearSearchState();
                return;
            }

            searchResults.innerHTML = '<div class="global-search-empty">Loading…</div>';
            setSearchResultsVisible(true);
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                fetch(`${GLOBAL_SEARCH_URL}?q=${encodeURIComponent(query)}`, {
                    method: 'GET',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                })
                    .then((response) => response.ok ? response.json() : Promise.reject(new Error('Search failed')))
                    .then((payload) => renderSearchResults(payload))
                    .catch(() => {
                        searchResults.innerHTML = '<div class="global-search-empty">No results found</div>';
                        selectedIndex = -1;
                        setSearchResultsVisible(true);
                    });
            }, 180);
        }

        searchInput.addEventListener('input', fetchSearchResults);

        if (clearButton) {
            clearButton.addEventListener('click', () => {
                searchInput.value = '';
                clearSearchState();
                searchInput.focus();
            });
        }

        searchInput.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                clearSearchState();
                searchInput.blur();
                return;
            }

            if (event.key === 'ArrowDown' && !searchResults.hidden) {
                event.preventDefault();
                moveSelection(1);
                return;
            }

            if (event.key === 'ArrowUp' && !searchResults.hidden) {
                event.preventDefault();
                moveSelection(-1);
                return;
            }

            if (event.key === 'Enter') {
                if (!searchResults.hidden) {
                    const didNavigate = navigateSelectedResult();
                    if (didNavigate) {
                        event.preventDefault();
                    }
                }
            }
        });

        searchForm.addEventListener('submit', function (event) {
            event.preventDefault();
            const query = searchInput.value.trim();
            if (!query) {
                clearSearchState();
                return;
            }

            const activeItem = searchResults.querySelector('.global-search-item.is-active');
            if (activeItem && activeItem.dataset.url) {
                window.location.href = activeItem.dataset.url;
                return;
            }

            window.location.href = `/courses/?search=${encodeURIComponent(query)}`;
        });

        document.addEventListener('click', function (event) {
            if (!searchShell.contains(event.target)) {
                clearSearchState();
            }
        });

        if (clearButton) {
            const updateClearButton = () => {
                clearButton.hidden = searchInput.value.trim().length === 0;
            };
            searchInput.addEventListener('input', updateClearButton);
            updateClearButton();
        }
    }

    if (userMenuToggle && userDropdown) {
        const closeUserMenu = () => {
            userMenuToggle.setAttribute('aria-expanded', 'false');
            userDropdown.hidden = true;
        };

        const openUserMenu = () => {
            userMenuToggle.setAttribute('aria-expanded', 'true');
            userDropdown.hidden = false;
        };

        userMenuToggle.addEventListener('click', function () {
            const isOpen = userMenuToggle.getAttribute('aria-expanded') === 'true';
            if (isOpen) {
                closeUserMenu();
            } else {
                openUserMenu();
            }
        });

        document.addEventListener('click', function (event) {
            const trigger = event.target.closest('#userMenuToggle');
            const dropdown = event.target.closest('#userDropdown');
            if (!trigger && !dropdown) {
                closeUserMenu();
            }
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                closeUserMenu();
            }
        });
    }

    document.addEventListener('keydown', function (event) {
        const isMeta = event.ctrlKey || event.metaKey;
        if (isMeta && event.key.toLowerCase() === 'k') {
            if (searchInput) {
                event.preventDefault();
                searchInput.focus();
                searchInput.select();
            }
        }
    });
});