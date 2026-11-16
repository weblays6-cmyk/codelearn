(() => {
    function csrfToken() {
        return document.cookie.split('; ').find((value) => value.startsWith('csrftoken='))?.split('=').slice(1).join('=')
            || document.querySelector('[name="csrfmiddlewaretoken"]')?.value
            || '';
    }

    function toast(message) {
        let item = document.querySelector('.wishlist-toast');
        if (!item) {
            item = document.createElement('div');
            item.className = 'wishlist-toast';
            item.setAttribute('role', 'status');
            item.setAttribute('aria-live', 'polite');
            document.body.appendChild(item);
        }
        item.textContent = message;
        item.classList.add('is-visible');
        window.clearTimeout(item.hideTimer);
        item.hideTimer = window.setTimeout(() => item.classList.remove('is-visible'), 2600);
    }

    function animateMark(button) {
        const target = document.querySelector('.courses-wishlist-button');
        if (!target || window.matchMedia('(prefers-reduced-motion: reduce)').matches || !button.animate) return false;
        const from = button.getBoundingClientRect();
        const to = target.querySelector('.wishlist-mark')?.getBoundingClientRect() || target.getBoundingClientRect();
        const mark = document.createElement('span');
        mark.className = 'wishlist-flight';
        mark.textContent = 'v';
        mark.style.left = `${from.left + from.width / 2 - 13}px`;
        mark.style.top = `${from.top + from.height / 2 - 13}px`;
        document.body.appendChild(mark);
        const x = to.left + to.width / 2 - from.left - from.width / 2;
        const y = to.top + to.height / 2 - from.top - from.height / 2;
        const animation = mark.animate([
            { transform: 'translate(0, 0) scale(1)', opacity: 1 },
            { transform: `translate(${x * .48}px, ${y * .48 - 64}px) scale(.8)`, opacity: 1, offset: .58 },
            { transform: `translate(${x}px, ${y}px) scale(.5)`, opacity: .2 },
        ], { duration: 600, easing: 'cubic-bezier(.2,.8,.2,1)' });
        animation.onfinish = () => {
            mark.remove();
            target.classList.remove('is-bouncing');
            void target.offsetWidth;
            target.classList.add('is-bouncing');
        };
        return true;
    }

    function updateSaved(button, saved) {
        button.dataset.saved = saved ? 'true' : 'false';
        button.setAttribute('aria-pressed', saved ? 'true' : 'false');
        button.setAttribute('aria-label', saved ? 'Remove saved course' : 'Save course');
        const icon = button.querySelector('i');
        if (icon) icon.className = `bi ${saved ? 'bi-heart-fill' : 'bi-heart'}`;
    }

    document.querySelectorAll('.wishlist-toggle[data-url]').forEach((button) => {
        button.addEventListener('click', async () => {
            const previous = button.dataset.saved === 'true';
            const optimistic = !previous;
            updateSaved(button, optimistic);
            if (optimistic) animateMark(button);
            button.disabled = true;
            try {
                const response = await fetch(button.dataset.url, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
                    body: new URLSearchParams({ action: 'toggle' }),
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || 'Wishlist update failed.');
                updateSaved(button, result.saved);
                document.querySelectorAll('.wishlist-count').forEach((count) => {
                    count.textContent = result.count;
                    count.hidden = result.count < 1;
                });
                document.querySelectorAll('.courses-wishlist-button').forEach((target) => {
                    target.setAttribute('aria-label', `Open wishlist, ${result.count} saved courses`);
                });
                toast(result.saved ? 'Added to your wishlist.' : 'Removed from your wishlist.');
                if (!result.saved && document.querySelector('.wishlist-page')) {
                    button.closest('.course-card')?.remove();
                    if (!document.querySelector('.wishlist-page .course-card')) window.location.reload();
                }
            } catch (error) {
                updateSaved(button, previous);
                toast(error.message || 'Could not update your wishlist.');
            } finally {
                button.disabled = false;
            }
        });
    });
})();