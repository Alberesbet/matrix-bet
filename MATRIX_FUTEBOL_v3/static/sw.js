const CACHE="matrix-futebol-v31";
self.addEventListener("install",e=>{self.skipWaiting()});
self.addEventListener("activate",e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith("matrix-futebol-")&&k!==CACHE).map(k=>caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch",e=>{
  if(e.request.method!=="GET")return;
  if(e.request.mode==="navigate"){
    e.respondWith(fetch(e.request,{cache:"no-store"}).catch(()=>caches.match("/")));
    return;
  }
  e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));
});