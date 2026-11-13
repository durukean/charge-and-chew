/* Charge & Chew service worker.
   Two jobs:
   1. Work offline — a road trip loses signal exactly where chargers matter most.
   2. Stop re-downloading the ~1 MB dataset. GitHub Pages sends cache-control: max-age=600,
      so without this a returning visitor refetches everything every 10 minutes.
   Cache names are versioned; bump VERSION to roll out a new shell.                       */
const VERSION = 'cc-v51';
const SHELL = `${VERSION}-shell`;   // app shell (html/css/js/icons)
/* NOT versioned. data.js is addressed by a hash of its content (?v=), so a new dataset is a new
   URL whatever this worker's version is. Versioning this cache threw the ~1 MB dataset away on
   every app update -- about twenty times in a month -- although the data had not changed. */
const DATA  = 'cc-data';
const NAV_TIMEOUT = 3500;           // ms before a slow page load falls back to the cached copy
const TILES = `${VERSION}-tiles`;   // map tiles for areas already viewed
const TILE_LIMIT = 400;

const SHELL_URLS = ['/', '/index.html', '/manifest.json', '/favicon.svg', '/icon-192.png',
                    '/vendor/leaflet.js', '/vendor/leaflet.css', '/assets/pages.css',
                    // self-hosted fonts (BUG-B03): offline, and a returning visit, paint in them
                    '/assets/fonts/inter-latin.woff2', '/assets/fonts/bricolage-grotesque-latin.woff2',
                    '/assets/fonts/jetbrains-mono-latin.woff2'];

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
    // Carry the dataset over from a versioned cache left by an older worker, once.
    const fresh = await caches.open(DATA);
    for (const k of keys.filter(k => k !== DATA && k.endsWith('-data'))) {
      const old = await caches.open(k);
      for (const req of await old.keys()) {
        if (!(await fresh.match(req))) { const r = await old.match(req); if (r) await fresh.put(req, r); }
      }
    }
    /* CARTO tiles are all "API KEY REQUIRED" watermarks now (BUG-B01) and an older worker cached
       them cache-first: drop every one, from whichever tile cache holds it. */
    for (const k of keys.filter(k => k.endsWith('-tiles'))) {
      const c = await caches.open(k);
      for (const req of await c.keys()) if (/(^|\.)cartocdn\.com$/.test(new URL(req.url).hostname)) await c.delete(req);
    }
    await Promise.all(keys.filter(k => !k.startsWith(VERSION) && k !== DATA).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', e => {
  if (e.data === 'skipWaiting') self.skipWaiting();
  // Which shell this is: a page that is already this version is not offered a reload into it.
  if (e.data === 'version' && e.ports && e.ports[0]) e.ports[0].postMessage(VERSION);
  // Switching map style must drop cached tiles from the old provider — and is the escape
  // hatch if a watermark tile ever got cached by an older build of this worker.
  if (e.data === 'clearTiles') e.waitUntil(caches.delete(TILES));
});

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
  // Esri only. A CARTO tile (an old page still asking for one) is never intercepted, so never
  // cached: it goes to the network like any other cross-origin request (BUG-B01).
  if (url.hostname === 'server.arcgisonline.com') {
    event.respondWith((async () => {
      const c = await caches.open(TILES);
      const hit = await c.match(request);
      if (hit) return hit;
      try {
        const res = await fetch(request);
        // NEVER cache a throttle/watermark tile. CARTO answers a referrer block with an
        // "API key required" image as a valid 200 PNG; caching it cache-first pinned that
        // message on the map permanently, surviving deploys and CARTO itself recovering.
        // Real tiles are tens of KB, watermarks and blanks are under 2 KB.
        // Opaque (a tile requested without CORS) has no readable size: never cached. The page
        // asks with crossOrigin, so a normal tile is a readable 'cors' response.
        if (res && res.ok && res.type !== 'opaque') {
          const buf = await res.clone().arrayBuffer();
          if (buf.byteLength > 2000) { c.put(request, res.clone()); trimCache(TILES, TILE_LIMIT); }
        }
        return res;
      } catch { return hit || Response.error(); }
    })());
    return;
  }

  if (!sameOrigin) return;   // Nominatim / OSRM / analytics: always live, never cached

  // ---- the datasets: cache-first (URL carries a content hash, so a new build is a new entry).
  // data.js always; level2.js once someone has switched the Level 2 layer on.
  if (url.pathname.endsWith('/data.js') || url.pathname.endsWith('/level2.js')) {
    event.respondWith((async () => {
      const c = await caches.open(DATA);
      const hit = await c.match(request);
      if (hit) return hit;
      const res = await fetch(request);
      if (res && res.ok) {
        // keep only the current version of THIS file -- dropping every other URL would make
        // caching level2.js evict data.js
        for (const k of await c.keys()) {
          if (k.url !== request.url && new URL(k.url).pathname === url.pathname) c.delete(k);
        }
        c.put(request, res.clone());
      }
      return res;
    })());
    return;
  }

  // ---- pages: network-first so updates land, cache as offline fallback
  /* With no timeout, opening the app on one bar of signal waited for the network to give up
     entirely before the cached copy was used. After NAV_TIMEOUT the cached page is served and
     the network answer still refreshes the cache for next time. */
  /* One cached copy per PAGE, not per address. Keyed on the full URL, every shared link
     (/?q=starbucks, /?from=LA&to=Vegas, /?stop=123...) stored its own ~420 KB copy of the same
     index.html, without limit, and a link never opened before missed the cache and waited for
     the network on one bar of signal (BUG-20). The query never changes what the server sends. */
  if (request.mode === 'navigate' || (request.headers.get('accept') || '').includes('text/html')) {
    const page = url.origin + url.pathname;
    const net = fetch(request).then(async res => {
      if (res && res.ok) await (await caches.open(SHELL)).put(page, res.clone());
      return res;
    });
    if (event.waitUntil) event.waitUntil(net.catch(() => {}));
    event.respondWith((async () => {
      try {
        const first = await Promise.race([net, new Promise(r => setTimeout(r, NAV_TIMEOUT, 'slow'))]);
        if (first !== 'slow') return first;
        const hit = await caches.match(page);
        return hit || await net;
      } catch {
        return (await caches.match(page)) || (await caches.match('/index.html')) ||
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
