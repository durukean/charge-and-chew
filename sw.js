/* Charge & Chew service worker.
   Two jobs:
   1. Work offline — a road trip loses signal exactly where chargers matter most.
   2. Stop re-downloading the ~1 MB dataset. GitHub Pages sends cache-control: max-age=600,
      so without this a returning visitor refetches everything every 10 minutes.
   Cache names are versioned; bump VERSION to roll out a new shell.                       */
const VERSION = 'cc-v2';
const SHELL = `${VERSION}-shell`;   // app shell (html/css/js/icons)
const DATA  = `${VERSION}-data`;    // data.js — big, versioned by ?v= in the URL
const TILES = `${VERSION}-tiles`;   // map tiles for areas already viewed
const TILE_LIMIT = 400;

const SHELL_URLS = ['/', '/index.html', '/manifest.json', '/favicon.svg', '/icon-192.png',
                    '/vendor/leaflet.js', '/vendor/leaflet.css', '/assets/pages.css'];

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const c = await caches.open(SHELL);
    // don't let one 404 abort the whole install
    await Promise.allSettled(SHELL_URLS.map(u => c.add(new Request(u, { cache: 'reload' }))));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => !k.startsWith(VERSION)).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', e => { if (e.data === 'skipWaiting') self.skipWaiting(); });

async function trimCache(name, max) {
  const c = await caches.open(name);
  const keys = await c.keys();
  if (keys.length > max) await Promise.all(keys.slice(0, keys.length - max).map(k => c.delete(k)));
}

self.addEventListener('fetch', event => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  const sameOrigin = url.origin === self.location.origin;

  // ---- map tiles (cross-origin): cache-first, capped — gives an offline map of where you've been
  if (/basemaps\.cartocdn\.com/.test(url.hostname)) {
    event.respondWith((async () => {
      const c = await caches.open(TILES);
      const hit = await c.match(request);
      if (hit) return hit;
      try {
        const res = await fetch(request);
        if (res && (res.ok || res.type === 'opaque')) { c.put(request, res.clone()); trimCache(TILES, TILE_LIMIT); }
        return res;
      } catch { return hit || Response.error(); }
    })());
    return;
  }

  if (!sameOrigin) return;   // Nominatim / OSRM / analytics: always live, never cached

  // ---- the dataset: cache-first (URL carries ?v=N, so a new build is a new entry)
  if (url.pathname.endsWith('/data.js')) {
    event.respondWith((async () => {
      const c = await caches.open(DATA);
      const hit = await c.match(request);
      if (hit) return hit;
      const res = await fetch(request);
      if (res && res.ok) {
        // keep only the current version of the data
        for (const k of await c.keys()) if (k.url !== request.url) c.delete(k);
        c.put(request, res.clone());
      }
      return res;
    })());
    return;
  }

  // ---- pages: network-first so updates land, cache as offline fallback
  if (request.mode === 'navigate' || (request.headers.get('accept') || '').includes('text/html')) {
    event.respondWith((async () => {
      try {
        const res = await fetch(request);
        if (res && res.ok) (await caches.open(SHELL)).put(request, res.clone());
        return res;
      } catch {
        return (await caches.match(request)) || (await caches.match('/index.html')) ||
               new Response('<h1>Offline</h1><p>Open the app once while online to use it offline.</p>',
                            { headers: { 'Content-Type': 'text/html' } });
      }
    })());
    return;
  }

  // ---- everything else same-origin: stale-while-revalidate
  event.respondWith((async () => {
    const c = await caches.open(SHELL);
    const hit = await c.match(request);
    const net = fetch(request).then(res => { if (res && res.ok) c.put(request, res.clone()); return res; })
                              .catch(() => null);
    return hit || (await net) || Response.error();
  })());
});
