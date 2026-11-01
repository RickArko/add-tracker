// Keeps the app's own files available offline. API responses are never cached here, so health
// data doesn't end up in this cache.
const CACHE = "tally-shell-v1";

self.addEventListener("install", (event) => {
  // The first visit loads files before this worker runs, so collect them from the page itself.
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE);
      await cache.add("/");
      const html = await (await cache.match("/")).text();
      const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1]);
      await cache.addAll(assets);
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname === "/healthz") return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Every route serves the same page, so one cached copy covers them all.
          if (response.ok) caches.open(CACHE).then((cache) => cache.put("/", response.clone()));
          return response.clone();
        })
        .catch(() => caches.match("/")),
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ||
        fetch(request).then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        }),
    ),
  );
});
