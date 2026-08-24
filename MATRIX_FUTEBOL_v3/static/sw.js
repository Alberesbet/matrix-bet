const CACHE="matrix-futebol-v328-betfair-login";
const STATIC=["/static/manifest.webmanifest","/static/icon-192.png","/static/icon-512.png"];
self.addEventListener("install",e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(STATIC)).catch(()=>{}));
  self.skipWaiting();
});
self.addEventListener("activate",e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(
    keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))
  )).then(()=>self.clients.claim()));
});
self.addEventListener("fetch",e=>{
  const req=e.request,url=new URL(req.url);
  if(req.mode==="navigate" || url.pathname==="/" || url.pathname.startsWith("/api/")){
    e.respondWith(fetch(req,{cache:"no-store"}).catch(()=>caches.match(req)));
    return;
  }
  if(url.pathname.startsWith("/static/")){
    e.respondWith(fetch(req,{cache:"no-store"}).then(resp=>{
      const copy=resp.clone();
      caches.open(CACHE).then(c=>c.put(req,copy)).catch(()=>{});
      return resp;
    }).catch(()=>caches.match(req)));
  }
});
