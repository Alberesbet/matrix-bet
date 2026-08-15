const ADMIN_CACHE='matrix-bet-admin-v596-shell';
const ADMIN_SHELL=[
  '/',
  '/static/admin.html',
  '/static/admin-manifest.webmanifest',
  '/static/icon-192.png',
  '/static/icon-512.png'
];

self.addEventListener('install',event=>{
  event.waitUntil(
    caches.open(ADMIN_CACHE).then(cache=>cache.addAll(ADMIN_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener('activate',event=>{
  event.waitUntil(
    caches.keys().then(keys=>Promise.all(
      keys.filter(k=>k.startsWith('matrix-bet-admin-') && k!==ADMIN_CACHE).map(k=>caches.delete(k))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch',event=>{
  const req=event.request;
  const url=new URL(req.url);
  if(req.method!=='GET') return;
  if(url.pathname.startsWith('/api/')) return;

  if(ADMIN_SHELL.includes(url.pathname)){
    event.respondWith(
      fetch(req).then(resp=>{
        const clone=resp.clone();
        caches.open(ADMIN_CACHE).then(cache=>cache.put(req,clone));
        return resp;
      }).catch(()=>caches.match(req))
    );
  }
});
