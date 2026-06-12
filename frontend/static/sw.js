// Minimal offline-friendly service worker for GameDrop.
// App shell: cache-first for static assets, network-first for navigations.
// API responses are never cached (always live price data).
const CACHE = 'gamedrop-v1';
const SHELL = ['/', '/favicon.svg', '/manifest.webmanifest'];

self.addEventListener('install', (e) => {
	e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
	e.waitUntil(
		caches
			.keys()
			.then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
			.then(() => self.clients.claim())
	);
});

self.addEventListener('fetch', (e) => {
	const { request } = e;
	if (request.method !== 'GET') return;
	const url = new URL(request.url);
	if (url.origin !== self.location.origin) return;
	if (url.pathname.startsWith('/api/')) return; // always live

	if (request.mode === 'navigate') {
		e.respondWith(
			fetch(request)
				.then((res) => {
					caches.open(CACHE).then((c) => c.put('/', res.clone()));
					return res;
				})
				.catch(() => caches.match('/').then((r) => r ?? caches.match(request)))
		);
		return;
	}

	e.respondWith(
		caches.match(request).then(
			(cached) =>
				cached ??
				fetch(request).then((res) => {
					if (res.ok && res.type === 'basic') {
						const copy = res.clone();
						caches.open(CACHE).then((c) => c.put(request, copy));
					}
					return res;
				})
		)
	);
});
