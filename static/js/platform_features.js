window.vgrowhubFormatBadgeCount = function (value) {
    const count = Math.max(0, Number(value) || 0);
    return count > 9 ? '9+' : String(count);
};

document.addEventListener('DOMContentLoaded', function () {
    const LIVE_COUNTS_URL = '/api/live-counts/';
    const NOTIFICATIONS_URL = '/notifications/';
    const MESSAGES_URL = '/messages/';
    const countNames = [
        'notifications_unread',
        'messages_unread',
        'follow_requests_pending',
    ];
    const countLabels = {
        notifications_unread: 'New notification',
        messages_unread: 'New message',
        follow_requests_pending: 'New follow request',
    };
    const previousCounts = {};
    let pollTimer = null;
    let backoff = 0;
    let stopped = false;
    let polling = false;
    let refreshWhenCurrentPollCompletes = false;
    let latestMessageSender = '';
    let audioContext = null;
    let deferredInstallPrompt = null;
    try {
        localStorage.setItem('vgrowhub-notification-sound', document.documentElement.dataset.notificationSound === 'true' ? 'true' : 'false');
        localStorage.setItem('vgrowhub-message-sound', document.documentElement.dataset.messageSound === 'true' ? 'true' : 'false');
    } catch (error) {
        window.console.warn('Sound preferences could not be synchronized.', error);
    }

    function getAudioContext() {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return null;
        if (!audioContext) audioContext = new AudioContextClass();
        return audioContext;
    }

    function unlockAudio() {
        const context = getAudioContext();
        if (!context || context.state === 'running') return;
        context.resume().catch((error) => {
            window.console.warn('Audio could not be enabled.', error);
        });
    }

    ['click', 'keydown', 'touchstart'].forEach((eventName) => {
        document.addEventListener(eventName, unlockAudio, { passive: true, once: true });
    });

    function playChime(force) {
        const context = getAudioContext();
        if (!context) return;
        if (!force) {
            try {
                if (localStorage.getItem('vgrowhub-notification-sound') !== 'true'
                    && localStorage.getItem('vgrowhub-message-sound') !== 'true') return;
            } catch (error) {
                window.console.warn('Sound preferences could not be read.', error);
                return;
            }
        }
        if (context.state !== 'running') {
            unlockAudio();
            return;
        }
        const startAt = context.currentTime;
        [659.25, 880].forEach((frequency, index) => {
            const oscillator = context.createOscillator();
            const gain = context.createGain();
            const noteStart = startAt + index * 0.14;
            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(frequency, noteStart);
            gain.gain.setValueAtTime(0.0001, noteStart);
            gain.gain.exponentialRampToValueAtTime(0.045, noteStart + 0.025);
            gain.gain.exponentialRampToValueAtTime(0.0001, noteStart + 0.16);
            oscillator.connect(gain);
            gain.connect(context.destination);
            oscillator.start(noteStart);
            oscillator.stop(noteStart + 0.17);
        });
    }

    function playCategorySound(name) {
        const key = name === 'messages_unread'
            ? 'vgrowhub-message-sound'
            : 'vgrowhub-notification-sound';
        try {
            if (localStorage.getItem(key) === 'true') playChime(false);
        } catch (error) {
            window.console.warn('Sound preferences could not be read.', error);
        }
        if (navigator.vibrate) navigator.vibrate([35, 45, 35]);
        if (document.visibilityState === 'hidden' && 'Notification' in window
            && Notification.permission === 'granted') {
            new Notification(name === 'messages_unread' ? 'New message' : 'New notification', {
                body: 'You have new activity on vGrowHub.',
                icon: '/static/images/vgrowhub-icon-192.png',
            });
        }
    }

    function readCookie(name) {
        const entry = document.cookie.split(';').map((value) => value.trim())
            .find((value) => value.startsWith(`${name}=`));
        return entry ? decodeURIComponent(entry.slice(name.length + 1)) : '';
    }

    function updateBadges(counts) {
        countNames.forEach((name) => {
            const count = Math.max(0, Number(counts[name]) || 0);
            if (previousCounts[name] !== undefined && count > previousCounts[name]) {
                const label = name === 'messages_unread' && latestMessageSender
                    ? `New message from @${latestMessageSender}`
                    : countLabels[name];
                showToast(label);
                playCategorySound(name);
            }
            previousCounts[name] = count;
            document.querySelectorAll(`[data-live-count="${name}"]`).forEach((badge) => {
                badge.textContent = window.vgrowhubFormatBadgeCount(count);
                badge.hidden = count === 0;
                badge.setAttribute('aria-label', `${count} ${name.replace(/_/g, ' ')}`);
                if (count > 0) {
                    badge.classList.remove('badge-pulse');
                    void badge.offsetWidth;
                    badge.classList.add('badge-pulse');
                    window.setTimeout(() => badge.classList.remove('badge-pulse'), 650);
                }
            });
        });
        const total = countNames.reduce((sum, name) => sum + (Number(counts[name]) || 0), 0);
        const baseTitle = document.title.replace(/^\(\d+\)\s*/, '');
        document.title = total ? `(${total}) ${baseTitle}` : baseTitle;
    }

    function showToast(message) {
        let toast = document.getElementById('platformLiveToast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'platformLiveToast';
            toast.className = 'platform-live-toast';
            toast.setAttribute('role', 'status');
            toast.setAttribute('aria-live', 'polite');
            document.body.appendChild(toast);
        }
        toast.textContent = message;
        toast.classList.add('is-visible');
        window.clearTimeout(toast.hideTimer);
        toast.hideTimer = window.setTimeout(() => toast.classList.remove('is-visible'), 2800);
    }

    function updateNotificationList(items) {
        const list = document.querySelector('.notification-shell');
        if (!list || !items.length) return;
        const existingIds = new Set(
            Array.from(list.querySelectorAll('[data-notification-id]'))
                .map((item) => Number(item.dataset.notificationId))
        );
        const emptyState = list.querySelector('.empty-state');
        if (emptyState) emptyState.remove();
        items.forEach((item) => {
            if (existingIds.has(Number(item.id))) return;
            const article = document.createElement('article');
            article.className = item.is_read ? 'notification' : 'notification unread';
            article.dataset.notificationId = item.id;
            const content = document.createElement('div');
            content.className = 'notification-content';
            const title = document.createElement('h3');
            const link = document.createElement('a');
            link.href = item.url;
            link.textContent = item.sender_name;
            title.appendChild(link);
            const message = document.createElement('p');
            message.textContent = item.message;
            const time = document.createElement('div');
            time.className = 'notification-time';
            time.textContent = item.created_at;
            content.append(title, message, time);
            article.append(content);
            if (!item.is_read) {
                const dot = document.createElement('span');
                dot.className = 'unread-dot';
                dot.setAttribute('aria-label', 'Unread notification');
                article.append(dot);
            }
            const firstNotification = list.querySelector('[data-notification-id]');
            if (firstNotification) firstNotification.before(article);
            else list.appendChild(article);
        });
    }

    async function refreshNotifications() {
        if (!window.location.pathname.startsWith(NOTIFICATIONS_URL)) return;
        const ids = Array.from(document.querySelectorAll('[data-notification-id]'))
            .map((item) => Number(item.dataset.notificationId) || 0);
        const after = Math.max(0, ...ids);
        const filter = new URLSearchParams(window.location.search).get('filter');
        const filterParameter = filter ? `&filter=${encodeURIComponent(filter)}` : '';
        const response = await fetch(`${NOTIFICATIONS_URL}?format=json&after=${after}${filterParameter}`, {
            credentials: 'same-origin',
            cache: 'no-store',
        });
        if (response.status === 401) {
            stopped = true;
            return;
        }
        if (!response.ok) throw new Error('Could not refresh notifications.');
        const data = await response.json();
        updateNotificationList(data.items || []);
    }

    function buildConversationItem(item) {
        const link = document.createElement('a');
        link.className = 'conversation-item';
        link.href = item.url;
        link.dataset.conversationId = item.id;
        link.dataset.conversationSearch = `${item.name} @${item.username} ${item.project} ${item.preview}`;
        const avatar = document.createElement('div');
        avatar.className = 'conversation-avatar';
        avatar.textContent = (item.name || item.username || '?').slice(0, 1).toUpperCase();
        const info = document.createElement('div');
        info.className = 'conversation-info';
        const top = document.createElement('div');
        top.className = 'conversation-top';
        const name = document.createElement('strong');
        name.textContent = item.name;
        const username = document.createElement('small');
        username.textContent = `@${item.username}`;
        top.append(name, username);
        if (item.unread_count) {
            const unread = document.createElement('span');
            unread.className = 'unread-badge';
            unread.textContent = window.vgrowhubFormatBadgeCount(item.unread_count);
            top.appendChild(unread);
        }
        if (item.last_message_time) {
            const time = document.createElement('span');
            time.className = 'conversation-time';
            time.textContent = item.last_message_time;
            top.appendChild(time);
        }
        const project = document.createElement('div');
        project.className = 'conversation-project';
        project.textContent = item.project || 'Personal conversation';
        const preview = document.createElement('p');
        preview.className = 'conversation-preview';
        preview.textContent = item.preview;
        info.append(top, project, preview);
        const arrow = document.createElement('i');
        arrow.className = 'bi bi-chevron-right conversation-arrow';
        link.append(avatar, info, arrow);
        return link;
    }

    async function refreshConversations() {
        if (window.location.pathname !== MESSAGES_URL) return;
        const response = await fetch(`${MESSAGES_URL}?format=json`, {
            credentials: 'same-origin',
            cache: 'no-store',
        });
        if (response.status === 401) {
            stopped = true;
            return;
        }
        if (!response.ok) throw new Error('Could not refresh conversations.');
        const data = await response.json();
        const newestUnread = (data.items || []).find((item) => item.unread_count > 0);
        latestMessageSender = newestUnread ? newestUnread.last_message_sender_username : '';
        let list = document.getElementById('conversationList');
        if (!list && data.items && data.items.length) {
            const card = document.querySelector('.messages-card');
            list = document.createElement('div');
            list.className = 'conversation-list';
            list.id = 'conversationList';
            card.appendChild(list);
            const empty = card.querySelector('.messages-empty');
            if (empty) empty.remove();
        }
        if (!list) return;
        (data.items || []).forEach((item) => {
            let existing = list.querySelector(`[data-conversation-id="${item.id}"]`);
            const replacement = buildConversationItem(item);
            if (existing) existing.replaceWith(replacement);
            else list.append(replacement);
        });
        (data.items || []).forEach((item) => {
            const conversation = list.querySelector(`[data-conversation-id="${item.id}"]`);
            if (conversation) list.appendChild(conversation);
        });
    }

    async function poll() {
        if (stopped || document.visibilityState !== 'visible' || polling) return;
        polling = true;
        try {
            const response = await fetch(LIVE_COUNTS_URL, {
                credentials: 'same-origin',
                cache: 'no-store',
            });
            if (response.status === 401 || response.redirected && response.url.includes('/login/')) {
                stopped = true;
                handleRevokedSession();
                return;
            }
            if (!response.ok) throw new Error('Could not refresh live counts.');
            const counts = await response.json();
            await Promise.all([refreshNotifications(), refreshConversations()]);
            updateBadges(counts);
            backoff = 0;
        } catch (error) {
            backoff = Math.min(backoff + 1, 5);
            window.console.warn('Live updates could not be refreshed; retrying with backoff.', error);
        } finally {
            polling = false;
        }
        if (!stopped && document.visibilityState === 'visible') {
            if (refreshWhenCurrentPollCompletes) {
                refreshWhenCurrentPollCompletes = false;
                poll();
                return;
            }
            pollTimer = window.setTimeout(poll, backoff ? Math.min(5000 * (2 ** backoff), 60000) : 5000);
        }
    }

    function startPolling() {
        window.clearTimeout(pollTimer);
        if (document.visibilityState !== 'visible' || stopped) return;
        if (polling) {
            refreshWhenCurrentPollCompletes = true;
            return;
        }
        poll();
    }

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') window.clearTimeout(pollTimer);
        else {
            backoff = 0;
            startPolling();
        }
    });
    document.addEventListener('vgrowhub:refresh-counts', startPolling);
    startPolling();

    document.addEventListener('click', async function (event) {
        const article = event.target.closest('[data-notification-id]');
        const link = event.target.closest('a[href]');
        if (!article || !link || !article.classList.contains('unread')) return;
        event.preventDefault();
        const formData = new URLSearchParams({ notification_id: article.dataset.notificationId });
        try {
            const response = await fetch(`${NOTIFICATIONS_URL}?format=json`, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': readCookie('csrftoken'),
                },
                body: formData,
                keepalive: true,
            });
            if (!response.ok) throw new Error('Could not mark the notification as read.');
            article.classList.remove('unread');
            article.querySelector('.unread-dot')?.remove();
            const countsResponse = await fetch(LIVE_COUNTS_URL, {
                credentials: 'same-origin',
                cache: 'no-store',
            });
            if (countsResponse.status === 401) {
                handleRevokedSession();
                return;
            }
            if (!countsResponse.ok) throw new Error('Could not refresh live counts.');
            updateBadges(await countsResponse.json());
        } catch (error) {
            showToast('Could not mark the notification as read.');
            window.console.error('Notification read status could not be updated.', error);
            return;
        }
        window.location.href = link.href;
    });

    document.querySelectorAll('.setting-feature-toggle').forEach((input) => {
        const key = input.dataset.featureToggle;
        const defaultValue = key === 'swipe-navigation';
        try {
            input.checked = localStorage.getItem(`vgrowhub-${key}`) === null
                ? defaultValue
                : localStorage.getItem(`vgrowhub-${key}`) === 'true';
        } catch (error) {
            input.checked = defaultValue;
        }
        input.addEventListener('change', function () {
            try {
                localStorage.setItem(`vgrowhub-${key}`, String(input.checked));
            } catch (error) {
                window.console.error('Could not save this preference.', error);
            }
        });
    });

    document.querySelectorAll('.setting-sound-toggle').forEach((input) => {
        const fieldName = input.dataset.soundToggle;
        const storageKey = `vgrowhub-${fieldName.replace('_', '-')}`;
        try {
            localStorage.setItem(storageKey, String(input.checked));
        } catch (error) {
            window.console.warn('Sound preference could not be stored locally.', error);
        }
        input.addEventListener('change', async function () {
            const requestedValue = input.checked;
            const values = {
                notification_sound: document.querySelector('[data-sound-toggle="notification_sound"]')?.checked,
                message_sound: document.querySelector('[data-sound-toggle="message_sound"]')?.checked,
            };
            try {
                const response = await fetch('/settings/', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': readCookie('csrftoken'),
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    body: new URLSearchParams({
                        notification_sound: String(Boolean(values.notification_sound)),
                        message_sound: String(Boolean(values.message_sound)),
                    }),
                });
                if (response.status === 401) {
                    handleRevokedSession();
                    return;
                }
                if (!response.ok) throw new Error('Could not save sound preferences.');
                const saved = await response.json();
                try {
                    localStorage.setItem('vgrowhub-notification-sound', String(saved.notification_sound));
                    localStorage.setItem('vgrowhub-message-sound', String(saved.message_sound));
                } catch (error) {
                    window.console.warn('Sound preference could not be stored locally.', error);
                }
                if (requestedValue) unlockAudio();
            } catch (error) {
                input.checked = !requestedValue;
                showToast('Sound preference could not be saved.');
                window.console.error(error);
            }
        });
    });

    const testSoundButton = document.getElementById('testNotificationSound');
    if (testSoundButton) {
        testSoundButton.addEventListener('click', function () {
            const context = getAudioContext();
            if (!context) {
                showToast('Audio is not supported by this browser.');
                return;
            }
            context.resume().then(() => playChime(true)).catch((error) => {
                window.console.error('Test sound could not be played.', error);
                showToast('Test sound could not be played.');
            });
        });
    }

    const desktopNotificationsButton = document.getElementById('enableDesktopNotifications');
    if (desktopNotificationsButton) {
        desktopNotificationsButton.addEventListener('click', async function () {
            if (!('Notification' in window)) {
                showToast('Desktop notifications are not supported by this browser.');
                return;
            }
            const permission = await Notification.requestPermission();
            showToast(permission === 'granted'
                ? 'Desktop notifications enabled.'
                : 'Desktop notifications were not enabled.');
        });
    }

    const installButton = document.getElementById('installAppButton');
    const installCard = document.getElementById('settings-app');
    const installStates = installCard ? installCard.querySelectorAll('[data-install-state]') : [];
    const setInstallState = function (state) {
        installStates.forEach(function (item) {
            item.hidden = item.dataset.installState !== state;
        });
    };
    const isInstalledApp = window.matchMedia('(display-mode: standalone)').matches
        || navigator.standalone === true;
    let installedFlag = false;
    try {
        installedFlag = localStorage.getItem('vgrowhub-installed') === 'true';
    } catch (error) {
        window.console.warn('The installed app state could not be read.', error);
    }
    if (installCard) {
        setInstallState(isInstalledApp || installedFlag ? 'installed' : 'unsupported');
        const instructions = installCard.querySelector('.install-instructions');
        if (instructions && /iPad|iPhone|iPod/.test(navigator.userAgent)) {
            instructions.textContent = 'Tap Share, then Add to Home Screen.';
        }
    }
    window.addEventListener('beforeinstallprompt', function (event) {
        event.preventDefault();
        deferredInstallPrompt = event;
        if (installButton) {
            installButton.disabled = false;
            setInstallState('ready');
        }
    });
    if (installButton) {
        installButton.addEventListener('click', async function () {
            if (!deferredInstallPrompt) {
                showToast('Use your browser menu to install vGrowHub.');
                return;
            }
            deferredInstallPrompt.prompt();
            const choice = await deferredInstallPrompt.userChoice;
            deferredInstallPrompt = null;
            if (choice.outcome === 'accepted') {
                try {
                    localStorage.setItem('vgrowhub-installed', 'true');
                } catch (error) {
                    window.console.warn('The installed app state could not be saved.', error);
                }
                setInstallState('installed');
            } else {
                setInstallState('ready');
            }
        });
    }
    window.addEventListener('appinstalled', function () {
        if (!installCard) return;
        try {
            localStorage.setItem('vgrowhub-installed', 'true');
        } catch (error) {
            window.console.warn('The installed app state could not be saved.', error);
        }
        setInstallState('installed');
    });

    if ('serviceWorker' in navigator) {
        if (document.documentElement.dataset.debug === 'true') {
            navigator.serviceWorker.getRegistrations()
                .then((registrations) => Promise.all(registrations.map((registration) => registration.unregister())));
        } else {
            navigator.serviceWorker.register('/service-worker.js', { scope: '/' })
                .catch((error) => window.console.error('The offline app shell could not be registered.', error));
        }
    }

    function setupMobileFilterSheet(elements, title, buttonLabel) {
        const controls = elements.filter(Boolean);
        if (!controls.length || controls.some((element) => element.parentElement !== controls[0].parentElement)) return;

        const parent = controls[0].parentElement;
        const trigger = document.createElement('button');
        trigger.className = 'mobile-filter-trigger';
        trigger.type = 'button';
        trigger.innerHTML = '<i class="bi bi-sliders" aria-hidden="true"></i>';
        trigger.append(document.createTextNode(` ${buttonLabel}`));

        const dialog = document.createElement('dialog');
        dialog.className = 'mobile-filter-dialog';
        dialog.setAttribute('aria-label', title);

        const header = document.createElement('div');
        header.className = 'mobile-filter-sheet-header';
        const heading = document.createElement('h2');
        heading.className = 'mobile-filter-sheet-title';
        heading.textContent = title;
        const closeButton = document.createElement('button');
        closeButton.className = 'mobile-filter-sheet-close';
        closeButton.type = 'button';
        closeButton.setAttribute('aria-label', 'Close filters');
        closeButton.innerHTML = '<i class="bi bi-x-lg" aria-hidden="true"></i>';
        header.append(heading, closeButton);

        const content = document.createElement('div');
        content.className = 'mobile-filter-sheet-content';
        const footer = document.createElement('div');
        footer.className = 'mobile-filter-sheet-footer';
        const doneButton = document.createElement('button');
        doneButton.className = 'mobile-filter-sheet-done';
        doneButton.type = 'button';
        doneButton.textContent = 'Done';
        footer.appendChild(doneButton);
        dialog.append(header, content, footer);

        const placeholders = [];
        let controlsInSheet = false;

        function closeSheet() {
            if (dialog.open) dialog.close();
            else dialog.removeAttribute('open');
        }

        function syncForViewport(isMobile) {
            if (isMobile && !controlsInSheet) {
                controls.forEach((element) => {
                    const placeholder = document.createComment('mobile-filter-control');
                    element.before(placeholder);
                    placeholders.push(placeholder);
                    content.appendChild(element);
                });
                controlsInSheet = true;
            } else if (!isMobile && controlsInSheet) {
                closeSheet();
                controls.forEach((element, index) => {
                    placeholders[index].before(element);
                    placeholders[index].remove();
                });
                placeholders.length = 0;
                controlsInSheet = false;
            }
            trigger.hidden = !isMobile;
        }

        trigger.hidden = true;
        controls[0].before(trigger);
        parent.appendChild(dialog);
        trigger.addEventListener('click', function () {
            if (typeof dialog.showModal === 'function') dialog.showModal();
            else dialog.setAttribute('open', '');
        });
        closeButton.addEventListener('click', closeSheet);
        doneButton.addEventListener('click', closeSheet);
        dialog.addEventListener('click', function (event) {
            if (event.target === dialog) closeSheet();
        });

        const mobileFilterViewport = window.matchMedia('(max-width: 767px)');
        mobileFilterViewport.addEventListener('change', (event) => syncForViewport(event.matches));
        syncForViewport(mobileFilterViewport.matches);
    }

    setupMobileFilterSheet(
        [
            document.querySelector('.practice-page .panel .filters'),
            document.querySelector('.practice-page .panel .filters-row2'),
        ],
        'Practice filters',
        'Filters',
    );
    setupMobileFilterSheet(
        [document.querySelector('.courses-toolbar .course-search-form')],
        'Search courses',
        'Search and filters',
    );
    setupMobileFilterSheet(
        [document.querySelector('.project-toolbar')],
        'Search projects',
        'Search and filters',
    );

    const swipePaths = [
        '/dashboard/', '/courses/', '/my-learning/', '/practice/', '/assignments/',
        '/ai-tutor/', '/projects/', '/community/', '/messages/', '/profile/',
    ];
    let touchStart = null;
    function swipeEnabled() {
        try {
            return localStorage.getItem('vgrowhub-swipe-navigation') !== 'false';
        } catch (error) {
            return true;
        }
    }
    function swipeBlocked(target) {
        if (Boolean(target.closest(
            'input, textarea, select, button, [contenteditable="true"], .monaco-editor, .CodeMirror, pre, code, table, ' +
            '.carousel, [data-carousel], .modal, dialog[open], [role="dialog"], .message-modal-overlay, .danger-modal-backdrop, ' +
            '.sidebar, .mobile-drawer-overlay, .mobile-nav, #chatMessages, .chat-messages, .table-responsive, ' +
            '[data-horizontal-scroll], .bottom-sheet, [data-bottom-sheet]'
        )) || Boolean(window.getSelection()?.toString())) return true;

        let ancestor = target;
        while (ancestor && ancestor !== document.body) {
            const style = window.getComputedStyle(ancestor);
            if (
                (style.overflowX === 'auto' || style.overflowX === 'scroll')
                && ancestor.scrollWidth > ancestor.clientWidth + 1
            ) return true;
            ancestor = ancestor.parentElement;
        }
        return false;
    }
    function currentSwipeIndex() {
        const path = window.location.pathname;
        if (path.startsWith('/dashboard/')) return 0;
        if (path.startsWith('/course/') || path.startsWith('/courses/')) return 1;
        if (path.startsWith('/lesson/') || path.startsWith('/my-learning/')) return 2;
        if (path.startsWith('/practice/')) return 3;
        if (path.startsWith('/assignments/')) return 4;
        if (path.startsWith('/ai-tutor/')) return 5;
        if (path.startsWith('/projects/')) return 6;
        if (path.startsWith('/community/')) return 7;
        if (path.startsWith('/messages/')) return 8;
        if (path.startsWith('/profile/')) return 9;
        return -1;
    }
    document.addEventListener('touchstart', function (event) {
        if (window.innerWidth >= 768 || !swipeEnabled() || !event.touches.length || swipeBlocked(event.target)) {
            touchStart = null;
            return;
        }
        touchStart = {
            x: event.touches[0].clientX,
            y: event.touches[0].clientY,
            target: event.target,
        };
    }, { passive: true });
    document.addEventListener('touchmove', function (event) {
        if (touchStart && window.innerWidth < 768 && swipeEnabled() && event.touches.length) {
            touchStart.dx = event.touches[0].clientX - touchStart.x;
            touchStart.dy = event.touches[0].clientY - touchStart.y;
        }
    }, { passive: true });
    document.addEventListener('touchend', function () {
        if (!touchStart || window.innerWidth >= 768 || !swipeEnabled()) {
            touchStart = null;
            return;
        }
        const { dx = 0, dy = 0, target } = touchStart;
        touchStart = null;
        if (swipeBlocked(target) || Boolean(window.getSelection()?.toString())) return;
        if (Math.abs(dx) < 80 || Math.abs(dx) / Math.max(Math.abs(dy), 1) <= 1.5) return;
        const index = currentSwipeIndex();
        if (index < 0) return;
        const next = dx < 0 ? index + 1 : index - 1;
        if (next >= 0 && next < swipePaths.length) {
            try {
                sessionStorage.setItem('vgrowhub-swipe-transition', '1');
            } catch (error) {
                window.console.warn('Swipe transition could not be initialized.', error);
            }
            window.location.href = swipePaths[next];
        }
    }, { passive: true });

    try {
        if (sessionStorage.getItem('vgrowhub-swipe-transition') === '1') {
            sessionStorage.removeItem('vgrowhub-swipe-transition');
            document.body.classList.add('swipe-page-enter');
        }
    } catch (error) {
        window.console.warn('Swipe transition preference could not be read.', error);
    }

    window.addEventListener('pageshow', function () {
        if (window.location.pathname === '/settings/') return;
        try {
            sessionStorage.removeItem('vgrowhub-swipe-transition');
        } catch (error) {
            window.console.warn('Swipe transition state could not be cleared.', error);
        }
    }, { once: true });
});

function handleRevokedSession() {
    const message = 'You were signed out because your account was used on another device.';
    let toast = document.getElementById('platformLiveToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'platformLiveToast';
        toast.className = 'platform-live-toast';
        toast.setAttribute('role', 'alert');
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('is-visible');
    window.setTimeout(() => {
        window.location.assign('/login/?device_signed_out=1');
    }, 900);
}
