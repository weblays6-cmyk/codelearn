(() => {
    const form = document.querySelector('#catalogSearchForm');
    if (!form) return;

    const desktop = window.matchMedia('(min-width: 769px)');
    const search = form.querySelector('input[name="search"]');
    const clearSearch = form.querySelector('.catalog-search-clear');
    const filterFields = form.querySelector('.course-filter-fields');
    const filterTrigger = form.querySelector('.mobile-filter-trigger');
    const filterBackdrop = form.querySelector('.course-filter-backdrop');
    const grid = document.querySelector('.courses-grid');
    let searchTimer;

    function submitFilters() {
        if (grid) {
            grid.classList.add('is-updating');
            grid.setAttribute('aria-busy', 'true');
        }
        const skeleton = document.querySelector('.catalog-skeleton-grid');
        if (skeleton) skeleton.hidden = false;
        if (form.requestSubmit) form.requestSubmit();
        else form.submit();
    }

    function closeFilterSheet(returnFocus = false) {
        if (!filterFields || !filterTrigger || !filterBackdrop) return;
        filterFields.classList.remove('is-open');
        filterFields.setAttribute('aria-hidden', 'true');
        filterFields.removeAttribute('aria-modal');
        filterFields.removeAttribute('role');
        filterTrigger.setAttribute('aria-expanded', 'false');
        filterBackdrop.hidden = true;
        document.body.classList.remove('catalog-filter-sheet-open');
        if (returnFocus) filterTrigger.focus();
    }

    function openFilterSheet() {
        if (!filterFields || !filterTrigger || !filterBackdrop) return;
        filterFields.classList.add('is-open');
        filterFields.setAttribute('aria-hidden', 'false');
        filterFields.setAttribute('aria-modal', 'true');
        filterFields.setAttribute('role', 'dialog');
        filterFields.setAttribute('aria-label', 'Course filters');
        filterTrigger.setAttribute('aria-expanded', 'true');
        filterBackdrop.hidden = false;
        document.body.classList.add('catalog-filter-sheet-open');
        filterFields.querySelector('select')?.focus();
    }

    filterTrigger?.addEventListener('click', openFilterSheet);
    filterBackdrop?.addEventListener('click', () => closeFilterSheet(true));

    function closeMenus(except) {
        fields.forEach(({ field, menu, trigger }) => {
            if (field === except) return;
            menu.setAttribute('aria-hidden', 'true');
            trigger.setAttribute('aria-expanded', 'false');
        });
    }

    const fields = [...form.querySelectorAll('.course-category-field select')].map((select) => {
        const field = select.closest('.course-category-field');
        const trigger = document.createElement('button');
        const menu = document.createElement('div');
        trigger.type = 'button';
        trigger.className = 'catalog-select-trigger';
        trigger.setAttribute('aria-haspopup', 'listbox');
        trigger.setAttribute('aria-expanded', 'false');
        trigger.setAttribute('aria-label', select.getAttribute('aria-label') || 'Choose a filter');
        menu.className = 'catalog-select-menu';
        menu.setAttribute('role', 'listbox');
        menu.setAttribute('aria-label', select.getAttribute('aria-label') || 'Course filters');
        menu.setAttribute('aria-hidden', 'true');
        select.after(trigger, menu);

        function syncOptions() {
            trigger.replaceChildren();
            const value = document.createElement('span');
            value.className = 'catalog-select-value';
            value.textContent = select.selectedOptions[0]?.textContent.trim() || '';
            const chevron = document.createElement('i');
            chevron.className = 'bi bi-chevron-down';
            chevron.setAttribute('aria-hidden', 'true');
            trigger.append(value, chevron);
            menu.replaceChildren();
            [...select.options].forEach((option, index) => {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'catalog-select-option';
                item.setAttribute('role', 'option');
                item.setAttribute('aria-selected', option.selected ? 'true' : 'false');
                item.tabIndex = option.selected ? 0 : -1;
                item.textContent = option.textContent.trim();
                item.addEventListener('click', () => {
                    select.selectedIndex = index;
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                    syncOptions();
                    closeMenus();
                    trigger.focus();
                });
                menu.append(item);
            });
        }

        function openMenu() {
            closeMenus(field);
            menu.setAttribute('aria-hidden', 'false');
            trigger.setAttribute('aria-expanded', 'true');
            menu.querySelector('[aria-selected="true"]')?.focus();
        }

        trigger.addEventListener('click', () => {
            if (trigger.getAttribute('aria-expanded') === 'true') {
                menu.setAttribute('aria-hidden', 'true');
                trigger.setAttribute('aria-expanded', 'false');
            } else {
                openMenu();
            }
        });
        trigger.addEventListener('keydown', (event) => {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                openMenu();
                if (event.key === 'ArrowUp') menu.querySelector('[role="option"]:last-child')?.focus();
            }
        });
        menu.addEventListener('keydown', (event) => {
            const options = [...menu.querySelectorAll('[role="option"]')];
            const current = options.indexOf(document.activeElement);
            let next = current;
            if (event.key === 'ArrowDown') next = Math.min(current + 1, options.length - 1);
            else if (event.key === 'ArrowUp') next = Math.max(current - 1, 0);
            else if (event.key === 'Home') next = 0;
            else if (event.key === 'End') next = options.length - 1;
            else if (event.key === 'Escape') {
                event.preventDefault();
                menu.setAttribute('aria-hidden', 'true');
                trigger.setAttribute('aria-expanded', 'false');
                trigger.focus();
                return;
            } else return;
            event.preventDefault();
            options[next]?.focus();
        });
        select.addEventListener('change', () => {
            syncOptions();
            submitFilters();
        });

        function setMode() {
            const customized = desktop.matches;
            field.classList.toggle('is-customized', customized);
            select.tabIndex = customized ? -1 : 0;
            if (!customized) {
                menu.setAttribute('aria-hidden', 'true');
                trigger.setAttribute('aria-expanded', 'false');
            }
        }

        syncOptions();
        setMode();
        return { field, trigger, menu, setMode };
    });

    document.addEventListener('click', (event) => {
        fields.forEach(({ field, menu, trigger }) => {
            if (!field.contains(event.target)) {
                menu.setAttribute('aria-hidden', 'true');
                trigger.setAttribute('aria-expanded', 'false');
            }
        });
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && filterFields?.classList.contains('is-open')) {
            closeFilterSheet(true);
        } else if (event.key === 'Escape') {
            closeMenus();
        }
        if (event.key === '/' && !event.altKey && !event.ctrlKey && !event.metaKey
            && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
            event.preventDefault();
            search?.focus();
        }
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
            event.preventDefault();
            document.querySelector('#globalSearchInput')?.focus();
        }
    });

    desktop.addEventListener('change', () => {
        fields.forEach(({ setMode }) => setMode());
        if (desktop.matches) closeFilterSheet();
    });

    function syncSearchClear() {
        if (clearSearch) clearSearch.hidden = !search?.value;
    }

    search?.addEventListener('input', () => {
        syncSearchClear();
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(submitFilters, 300);
    });

    clearSearch?.addEventListener('click', () => {
        if (!search) return;
        search.value = '';
        syncSearchClear();
        submitFilters();
        search.focus();
    });

    form.addEventListener('submit', () => {
        window.clearTimeout(searchTimer);
        closeMenus();
        if (grid) {
            grid.classList.add('is-updating');
            grid.setAttribute('aria-busy', 'true');
        }
        const skeleton = document.querySelector('.catalog-skeleton-grid');
        if (skeleton) skeleton.hidden = false;
    });
    syncSearchClear();

    const cards = [...document.querySelectorAll('.courses-grid .course-card')];
    const totalLessons = cards.reduce((total, card) => total + Number(card.dataset.lessonCount || 0), 0);
    const lessonCount = document.querySelector('[data-catalog-lesson-count]');
    if (lessonCount) lessonCount.textContent = String(totalLessons);

    const categorySelect = form.querySelector('select[name="category"]');
    document.querySelectorAll('.quick-category-pill[data-category-value]').forEach((pill) => {
        const category = pill.dataset.categoryValue || '';
        const countElement = pill.querySelector('[data-quick-count]');
        if (countElement) {
            const count = category
                ? cards.filter((card) => card.dataset.category === pill.querySelector('[data-quick-count]').dataset.quickCount).length
                : Number(countElement.textContent || cards.length);
            countElement.textContent = String(count);
            countElement.title = 'Courses on this page';
        }
        pill.addEventListener('click', (event) => {
            if (!categorySelect) return;
            event.preventDefault();
            const normalized = category.toLocaleLowerCase();
            const option = [...categorySelect.options].find((item) => item.value.toLocaleLowerCase() === normalized);
            if (!option && category) return;
            categorySelect.value = option?.value || '';
            categorySelect.dispatchEvent(new Event('change', { bubbles: true }));
        });
    });

    document.querySelectorAll('[data-scroll-target]').forEach((button) => {
        button.addEventListener('click', () => {
            const row = document.getElementById(button.dataset.scrollTarget);
            if (!row) return;
            row.scrollBy({
                left: Number(button.dataset.scrollDirection || 1) * row.clientWidth * .85,
                behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
            });
        });
    });

    const toolbar = document.querySelector('.catalog-toolbar');
    if (toolbar) {
        const updateStickyState = () => toolbar.classList.toggle('is-stuck', toolbar.getBoundingClientRect().top <= 64);
        window.addEventListener('scroll', updateStickyState, { passive: true });
        updateStickyState();
    }

    const globalSearchForm = document.querySelector('.workspace-search');
    if (globalSearchForm && !globalSearchForm.querySelector('.catalog-global-shortcut')) {
        const hint = document.createElement('kbd');
        hint.className = 'catalog-global-shortcut';
        hint.textContent = 'Ctrl K';
        hint.setAttribute('aria-hidden', 'true');
        globalSearchForm.append(hint);
    }
})();
