(() => {
    const launch = document.getElementById('aiFeatureLaunch');
    const panel = document.getElementById('aiFeaturePanel');
    if (!launch || !panel) return;

    const close = document.getElementById('aiFeatureClose');
    const select = document.getElementById('aiFeatureSelect');
    const prompt = document.getElementById('aiFeaturePrompt');
    const submit = document.getElementById('aiFeatureSubmit');
    const status = document.getElementById('aiFeatureStatus');
    const result = document.getElementById('aiFeatureResult');
    const csrf = panel.querySelector('#aiFeatureCsrf input[name="csrfmiddlewaretoken"]')?.value
        || document.cookie.split('; ').find(item => item.startsWith('csrftoken='))?.split('=').slice(1).join('=')
        || '';

    launch.addEventListener('click', () => {
        panel.hidden = false;
        launch.setAttribute('aria-expanded', 'true');
        prompt.focus();
    });
    close.addEventListener('click', () => {
        panel.hidden = true;
        launch.setAttribute('aria-expanded', 'false');
        launch.focus();
    });
    panel.addEventListener('keydown', event => {
        if (event.key === 'Escape') close.click();
    });

    submit.addEventListener('click', async () => {
        submit.disabled = true;
        status.textContent = 'Preparing your suggestion…';
        result.textContent = '';
        try {
            const feature = select.value;
            const endpoint = panel.dataset.endpoint.replace(/assistant\/$/, `${encodeURIComponent(feature)}/`);
            const body = new URLSearchParams({
                prompt: prompt.value,
                object_type: panel.dataset.contextType || '',
                object_id: panel.dataset.contextId || ''
            });
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest'},
                body
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || 'The suggestion could not be generated.');
            const value = payload.result;
            result.textContent = Object.values(value).map(item => typeof item === 'string' ? item : JSON.stringify(item, null, 2)).join('\n\n');
            if (['lesson_quiz', 'interview_report'].includes(feature)) {
                const keep = document.createElement('button');
                keep.type = 'button';
                keep.textContent = 'Save to my learning';
                keep.addEventListener('click', async () => {
                    keep.disabled = true;
                    const saved = await fetch('/ai/features/keep/', {
                        method: 'POST',
                        headers: {'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest'},
                        body: new URLSearchParams({feature, content: JSON.stringify(value)})
                    });
                    const data = await saved.json();
                    status.textContent = saved.ok ? 'Saved to your learning.' : (data.error || 'Could not save this suggestion.');
                    keep.disabled = false;
                });
                result.append(document.createElement('br'), keep);
            }
            status.textContent = payload.cached ? 'Suggestion ready (cached).' : 'Suggestion ready.';
        } catch (error) {
            status.textContent = error instanceof Error ? error.message : 'The suggestion could not be generated. Please retry.';
        } finally {
            submit.disabled = false;
        }
    });
})();
