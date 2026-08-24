const CACHE="matrix-futebol-v322-fresh";
const STATIC=[
  "/static/manifest.webmanifest",
  "/static/icon-192.png",
  "/static/icon-512.png"
];

self.addEventListener("install",event=>{
  event.waitUntil(caches.open(CACHE).then(c=>c.addAll(STATIC)).catch(()=>{}));
  self.skipWaiting();
});

self.addEventListener("activate",event=>{
  event.waitUntil(
    caches.keys().then(keys=>Promise.all(
      keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))
    )).then(()=>self.clients.claim())
  );
});

self.addEventListener("fetch",event=>{
  const req=event.request;
  const url=new URL(req.url);

  if(
    req.mode==="navigate" ||
    url.pathname==="/" ||
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/bfbot/")
  ){
    event.respondWith(fetch(req,{cache:"no-store"}).catch(()=>caches.match(req)));
    return;
  }

  if(url.pathname.startsWith("/static/")){
    event.respondWith(
      fetch(req,{cache:"no-store"}).then(resp=>{
        const copy=resp.clone();
        caches.open(CACHE).then(c=>c.put(req,copy)).catch(()=>{});
        return resp;
      }).catch(()=>caches.match(req))
    );
  }
});
