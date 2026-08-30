// Cache the shell, network-first for the API.
const SHELL = 'meridian-shell-v2';
self.addEventListener('install', e => { self.skipWaiting(); e.waitUntil(caches.open(SHELL).then(c => c.addAll(['/', '/manifest.json', '/icon.svg']))); });
self.addEventListener('activate', e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (u.pathname.startsWith('/api/') || e.request.method !== 'GET') return; // network only
  const hashed = u.pathname.startsWith('/assets/');   // content-hashed: cache first. Everything else: network first, cache as fallback.
  e.respondWith(caches.match(e.request).then(hit => {
    const net = fetch(e.request).then(r => { if (r.ok && u.origin === location.origin) caches.open(SHELL).then(c => c.put(e.request, r.clone())); return r; }).catch(() => hit);
    return hashed && hit ? hit : net;
  }));
});
