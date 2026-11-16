const CACHE_VERSION = 'v2';
const CACHE_NAME = `vgrowhub-static-${CACHE_VERSION}`;
const PRECACHE_URLS = [
    '/static/images/vgrowhub-logo.svg',
    '/static/images/vgrowhub-icon.svg',
    '/static/images/vgrowhub-icon-192.png',
    '/static/images/vgrowhub-icon-512.png',
    '/static/manifest.webmanifest',
];
const STATIC_ASSET_PATTERN = /\.(?:css|js|svg|png|webmanifest|woff2?|ttf|ico)$/i;

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(PRECACHE_URLS))
            .then(() => self.skipWaiting()),
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((key) => key.startsWith('vgrowhub-static-') && key !== CACHE_NAME)
                    .map((key) => caches.delete(key)),
            ))
            .then(() => self.clients.claim()),
    );
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    const url = new URL(request.url);
    if (url.origin !== self.location.origin || request.method !== 'GET') return;

    if (url.pathname.startsWith('/static/') && STATIC_ASSET_PATTERN.test(url.pathname)) {
        if (/\.(?:css|js)$/i.test(url.pathname)) {
            event.respondWith(
                fetch(request).then((response) => {
                    if (response.ok && response.type === 'basic') {
                        const copy = response.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
                    }
                    return response;
                }).catch(() => caches.match(request)),
            );
            return;
        }
        event.respondWith(
            caches.match(request).then((cached) => cached || fetch(request).then((response) => {
                if (response.ok && response.type === 'basic') {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
                }
                return response;
            })),
        );
        return;
    }

    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request).catch(() => new Response(
                '<!doctype html><html lang="en"><meta charset="utf-8"><title>Offline</title><p>You are offline. Reconnect and try again.</p></html>',
                { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } },
            )),
        );
    }
});
