const CACHE_NAME = "voltacliente-v2";
const ARQUIVOS_CACHE = ["/login", "/static/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ARQUIVOS_CACHE).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response && response.status === 200) {
          const copia = response.clone();
          caches.open(CACHE_NAME).then((cache) => { cache.put(event.request, copia); });
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
