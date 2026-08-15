const CACHE = 'matrix-bet-v62-shell';
const SHELL = ['/', '/static/manifest.webmanifest', '/static/icon-192.png', '/static/icon-512.png'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).catch(()=>{}));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // Never intercept API/auth or administrator pages.
  if (
    url.pathname.startsWith('/api/') ||
    url.pathname === '/admin' ||
    url.pathname === '/admin/' ||
    url.pathname === '/painel-adm' ||
    url.pathname === '/painel-adm/' ||
    url.pathname === '/admin-login'
  ) return;

  event.respondWith(
    fetch(req).then(resp => {
      const copy = resp.clone();
      caches.open(CACHE).then(cache => cache.put(req, copy)).catch(()=>{});
      return resp;
    }).catch(() => caches.match(req).then(r => r || caches.match('/')))
  );
});
