(() => {
    function showToast(message) {
        let toast = document.querySelector('.wishlist-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.className = 'wishlist-toast';
            toast.setAttribute('role', 'status');
            toast.setAttribute('aria-live', 'polite');
            document.body.append(toast);
        }
        toast.textContent = message;
        toast.classList.add('is-visible');
        window.clearTimeout(toast.hideTimer);
        toast.hideTimer = window.setTimeout(() => toast.classList.remove('is-visible'), 2400);
    }

    document.querySelectorAll('[data-share-course]').forEach((button) => {
        button.addEventListener('click', async () => {
            const url = button.dataset.shareUrl || window.location.href;
            try {
                if (navigator.clipboard?.writeText) {
                    await navigator.clipboard.writeText(url);
                } else {
                    const fallback = document.createElement('textarea');
                    fallback.value = url;
                    fallback.setAttribute('readonly', '');
                    fallback.style.position = 'fixed';
                    fallback.style.opacity = '0';
                    document.body.append(fallback);
                    fallback.select();
                    const copied = document.execCommand('copy');
                    fallback.remove();
                    if (!copied) throw new Error('Could not copy this course link.');
                }
                showToast('Course link copied.');
            } catch (error) {
                showToast(error.message || 'Could not copy this course link.');
            }
        });
    });
})();