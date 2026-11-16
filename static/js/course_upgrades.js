(() => {
    const dialog = document.getElementById('courseUpgradeDialog');
    if (!dialog) return;

    const freeOption = dialog.querySelector('[data-free-option]');
    const enrollForm = dialog.querySelector('[data-course-enroll-form]');
    const courseName = dialog.querySelector('[data-upgrade-course-name]');
    const paymentStatus = dialog.querySelector('[data-payment-status]');
    let currentCourse = '';

    function csrfToken() {
        return document.querySelector('#courseUpgradeCsrf [name="csrfmiddlewaretoken"]')?.value
            || document.cookie.split('; ').find((value) => value.startsWith('csrftoken='))?.split('=').slice(1).join('=')
            || '';
    }

    function openUpgrade(trigger) {
        currentCourse = trigger.dataset.courseSlug || '';
        if (enrollForm) {
            enrollForm.action = trigger.dataset.courseUrl || (currentCourse ? `/courses/${encodeURIComponent(currentCourse)}/` : '');
        }
        if (freeOption) freeOption.hidden = false;
        if (courseName) courseName.textContent = trigger.dataset.courseTitle || '';
        if (paymentStatus) paymentStatus.textContent = dialog.dataset.paymentsAvailable === 'true' ? '' : 'Payments coming soon.';
        dialog.querySelectorAll('[data-upgrade-lesson-list]').forEach((list) => {
            list.hidden = trigger.dataset.paid !== 'true' && Number(trigger.dataset.advancedCount || 0) === 0;
        });
        if (!dialog.open) dialog.showModal();
    }

    document.querySelectorAll('.course-enroll-trigger, [data-open-upgrade]').forEach((trigger) => {
        trigger.addEventListener('click', () => openUpgrade(trigger));
    });
    dialog.querySelectorAll('[data-close-upgrade]').forEach((button) => {
        button.addEventListener('click', () => dialog.close());
    });
    dialog.addEventListener('click', (event) => {
        if (event.target === dialog) dialog.close();
    });

    let checkoutScript;
    function loadCheckout() {
        if (window.Razorpay) return Promise.resolve();
        if (checkoutScript) return checkoutScript;
        checkoutScript = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://checkout.razorpay.com/v1/checkout.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
        return checkoutScript;
    }

    function idempotencyKey() {
        if (window.crypto?.randomUUID) return window.crypto.randomUUID();
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
            const value = Math.floor(Math.random() * 16);
            return (character === 'x' ? value : (value & 3) | 8).toString(16);
        });
    }

    dialog.querySelectorAll('.course-premium-plan').forEach((button) => {
        button.addEventListener('click', async () => {
            if (dialog.dataset.paymentsAvailable !== 'true') {
                if (paymentStatus) paymentStatus.textContent = 'Payments coming soon.';
                return;
            }
            const originalText = button.textContent;
            button.disabled = true;
            if (paymentStatus) paymentStatus.textContent = 'Preparing secure checkout…';
            try {
                const body = new URLSearchParams({
                    idempotency_key: idempotencyKey(),
                    course: currentCourse,
                });
                const response = await fetch(`/payments/create-order/${encodeURIComponent(button.dataset.planSlug)}/`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
                    body,
                });
                const order = await response.json();
                if (!response.ok || !order.available || order.already_unlocked || order.already_paid) {
                    if (paymentStatus) paymentStatus.textContent = order.message || order.error || (order.already_unlocked || order.already_paid ? 'Your premium access is active.' : 'Payments are temporarily unavailable.');
                    if (order.already_unlocked || order.already_paid) window.location.reload();
                    return;
                }
                await loadCheckout();
                const checkout = new window.Razorpay({
                    key: order.key,
                    amount: order.amount,
                    currency: order.currency,
                    name: 'vGrowHub',
                    description: `${order.plan_name} · ${courseName?.textContent || 'Premium learning'}`,
                    order_id: order.order_id,
                    handler: async (result) => {
                        if (paymentStatus) paymentStatus.textContent = 'Verifying payment…';
                        const confirmation = await fetch('/payments/confirm/', {
                            method: 'POST',
                            headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
                            body: new URLSearchParams({
                                payment_id: order.payment_id,
                                razorpay_order_id: result.razorpay_order_id,
                                razorpay_payment_id: result.razorpay_payment_id,
                                razorpay_signature: result.razorpay_signature,
                            }),
                        });
                        const verified = await confirmation.json();
                        if (verified.success) window.location.reload();
                        else if (paymentStatus) paymentStatus.textContent = verified.error || 'Payment verification failed. Contact support if you were charged.';
                    },
                    modal: { ondismiss: () => { if (paymentStatus) paymentStatus.textContent = 'Checkout closed. Your payment was not completed.'; } },
                    prefill: {},
                    theme: { color: '#2F5BEA' },
                });
                checkout.open();
            } catch (error) {
                if (paymentStatus) paymentStatus.textContent = 'Payments are temporarily unavailable.';
            } finally {
                button.disabled = false;
                button.textContent = originalText;
            }
        });
    });
})();