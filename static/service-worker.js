// service-worker.js
// Responsável pelo cache offline e comportamento de app instalado

const CACHE_NAME = "retencaopro-v1";

// Arquivos que serão salvos no cache para funcionar offline
const ARQUIVOS_CACHE = [
  "/dashboard",
  "/login",
  "/static/manifest.json"
];

// Instalação: salva os arquivos no cache
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ARQUIVOS_CACHE).catch(() => {});
    })
  );
  self.skipWaiting();
});

// Ativação: remove caches antigos
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Fetch: tenta rede primeiro, fallback para cache
self.addEventListener("fetch", (event) => {
  // Ignora requisições que não sejam GET
  if (event.request.method !== "GET") return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Salva a resposta no cache se for válida
        if (response && response.status === 200) {
          const copia = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, copia);
          });
        }
        return response;
      })
      .catch(() => {
        // Se offline, retorna do cache
        return caches.match(event.request);
      })
  );
});
