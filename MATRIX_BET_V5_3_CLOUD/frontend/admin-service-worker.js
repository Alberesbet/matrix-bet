const CACHE='matrix-bet-admin-v661';
self.addEventListener('install',e=>{self.skipWaiting()});
self.addEventListener('activate',e=>{e.waitUntil(
  caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('matrix-bet-admin-')&&k!==CACHE).map(k=>caches.delete(k))))
);self.clients.claim()});
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET') return;
  if(e.request.mode==='navigate' && new URL(e.request.url).pathname.startsWith('/painel-adm')){
    e.respondWith(fetch(e.request,{cache:'no-store'}).catch(()=>caches.match('/painel-adm')));
  }
});
