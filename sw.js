/* Charge & Chew service worker.
   Two jobs:
   1. Work offline — a road trip loses signal exactly where chargers matter most.
   2. Stop re-downloading the ~1 MB dataset. GitHub Pages sends cache-control: max-age=600,
      so without this a returning visitor refetches everything every 10 minutes.
   The shell cache is versioned; bump VERSION (and index.html's SW_VER) to roll out a new shell.
   The dataset and the map tiles are not: an app update must not throw either away.        */
const VERSION = 'cc-v54';
const SHELL = `${VERSION}-shell`;   // app shell (html/css/js/icons)
/* NOT versioned. data.js is addressed by a hash of its content (?v=), so a new dataset is a new
   URL whatever this worker's version is. Versioning this cache threw the ~1 MB dataset away on
   every app update -- about twenty times in a month -- although the data had not changed. */
const DATA  = 'cc-data';
const NAV_TIMEOUT = 3500;           // ms a page never opened before waits before a cached copy is used
/* NOT versioned either (BUG-B09): a versioned tile cache wiped the offline map of everywhere
   you had been on every shell release. 'clearTiles' still empties it on demand. */
const TILES = 'cc-tiles';
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
       them cache-first: drop every one, from whichever tile cache holds it. Tiles in a versioned
       cache an older worker left (cc-v51-tiles) move into the stable one, once. */
    const tiles = await caches.open(TILES);
    for (const k of keys.filter(k => k.endsWith('-tiles'))) {
      const c = await caches.open(k);
      for (const req of await c.keys()) {
        if (/(^|\.)cartocdn\.com$/.test(new URL(req.url).hostname)) { await c.delete(req); continue; }
        if (k !== TILES && !(await tiles.match(req))) { const r = await c.match(req); if (r) await tiles.put(req, r); }
      }
    }
    await Promise.all(keys.filter(k => !k.startsWith(VERSION) && k !== DATA && k !== TILES).map(k => caches.delete(k)));
    trimCache(TILES, TILE_LIMIT);
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

/* Did the page change since the copy this visit was served? ETag or Last-Modified when both
   copies carry one (GitHub Pages sends both), else the bytes. */
async function pageChanged(a, b) {
  for (const h of ['etag', 'last-modified']) {
    const x = a.headers.get(h), y = b.headers.get(h);
    if (x && y) return x !== y;
  }
  return (await a.text()) !== (await b.text());
}
/* The page that was just served the cached copy: tell it a newer one is ready. It may still be
   loading, so look for it for a few seconds (its messages queue until its listener is up). */
async function tellPage(id) {
  for (let i = 0; id && i < 20; i++) {
    const c = await self.clients.get(id);
    if (c) { c.postMessage({ type: 'page-updated', version: VERSION }); return; }
    await new Promise(r => setTimeout(r, 500));
  }
}

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
        /* Only a real tile: HTTP 200, an image, with a body. An error comes back as a non-200 or
           as JSON/HTML ("Map data not yet available" is a 200 JSON error), never cached. The old
           rule (skip anything under 2,000 bytes) was for CARTO's watermarks and dropped 22 of 24
           Esri label tiles, which are mostly transparent and small, so offline maps had no
           place names (BUG-B08). CARTO itself is never intercepted (above).
           Opaque (a tile requested without CORS) is unreadable: never cached. The page asks with
           crossOrigin, so a normal tile is a readable 'cors' response. */
        if (res && res.status === 200 && res.type !== 'opaque' && /^image\/(png|jpe?g|webp)\b/i.test(res.headers.get('content-type') || '')) {
          const buf = await res.clone().arrayBuffer();
          if (buf.byteLength > 0) { c.put(request, res.clone()); trimCache(TILES, TILE_LIMIT); }
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

  // ---- pages: the cached copy at once, refreshed in the background (stale-while-revalidate)
  /* Network-first meant every visit more than ten minutes after the last (GitHub Pages sends
     max-age=600) waited for the HTML before the cached shell was used: 2.0 s with the page
     1.1 s away, 3.9 s with it 3 s away (PERF-B2). Now a page this worker has is served at once
     and the network copy replaces it for next time; if it changed, the page is told and offers
     "New version — tap to reload". A page never cached waits for the network as before, up
     to NAV_TIMEOUT, then any cached copy. */
  /* One cached copy per PAGE, not per address. Keyed on the full URL, every shared link
     (/?q=starbucks, /?from=LA&to=Vegas, /?stop=123...) stored its own ~420 KB copy of the same
     index.html, without limit, and a link never opened before missed the cache and waited for
     the network on one bar of signal (BUG-20). The query never changes what the server sends. */
  if (request.mode === 'navigate' || (request.headers.get('accept') || '').includes('text/html')) {
    const page = url.origin + url.pathname;
    const hitP = caches.match(page);
    /* Behind a cached copy, revalidate past the HTTP cache (max-age=600 would hand back the same
       old page for ten minutes): a conditional request, a 304 when nothing changed. A redirected
       answer is never stored: served to a later navigation it would be a network error. */
    const net = hitP.then(hit => hit ? fetch(url.href, { cache: 'no-cache', credentials: 'same-origin' }) : fetch(request)).then(async res => {
      if (res && res.ok && !res.redirected) {
        const prev = await caches.match(page);
        await (await caches.open(SHELL)).put(page, res.clone());
        if (prev && await pageChanged(prev, res.clone())) tellPage(event.resultingClientId || event.clientId);
      }
      return res;
    });
    if (event.waitUntil) event.waitUntil(net.catch(() => {}));
    event.respondWith((async () => {
      const hit = await hitP;
      if (hit) return hit;
      try {
        const first = await Promise.race([net, new Promise(r => setTimeout(r, NAV_TIMEOUT, 'slow'))]);
        if (first !== 'slow') return first;
        return (await caches.match(page)) || await net;
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
