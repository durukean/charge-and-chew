import fs from 'fs';
// minimal SW environment
const listeners = {};
const store = new Map();          // cacheName -> Map(url -> {body})
const mkCache = name => ({
  async match(req){ const m=store.get(name); const k=typeof req==='string'?req:req.url; return m&&m.get(k) ? mkRes(m.get(k)) : undefined; },
  async put(req,res){ const k=typeof req==='string'?req:req.url; if(!store.has(name))store.set(name,new Map());
                      store.get(name).set(k,{size:res.__size, ct:res.__ct, etag:res.__etag}); },
  async keys(){ const m=store.get(name); return m?[...m.keys()].map(u=>({url:u})):[]; },
  async delete(k){ const m=store.get(name); return m?m.delete(typeof k==='string'?k:k.url):false; },
});
/* type: 'basic' same-origin, 'cors' a cross-origin answer the page asked for with CORS (the
   map tiles, since crossOrigin is set), 'opaque' one asked for without -- its body is unreadable
   to the worker, which therefore must never cache it. */
function mkRes({size, type='basic', status=200, ct='image/png', etag}){ return { ok:status>=200&&status<300, status, type, __size:size, __ct:ct, __etag:etag,
  headers:{ get:h => h === 'content-type' ? ct : h === 'etag' ? (etag || null) : null },
  clone(){return mkRes({size, type, status, ct, etag})}, async arrayBuffer(){return new ArrayBuffer(type === 'opaque' ? 0 : size)},
  async text(){ return 'x'.repeat(size) } }; }

globalThis.self = {
  addEventListener:(t,f)=>{(listeners[t]=listeners[t]||[]).push(f)},
  location:{origin:'https://chargeandchew.com'}, skipWaiting(){},
  clients:{claim(){}, async get(id){ return id ? { postMessage: m => told_page.push([id, m]) } : undefined; }},
};
globalThis.caches = { open:async n=>mkCache(n), keys:async()=>[...store.keys()], delete:async n=>store.delete(n),
  async match(req){ let k=typeof req==='string'?req:req.url; if (k.startsWith('/')) k='https://chargeandchew.com'+k; for (const m of store.values()) if (m.get(k)) return mkRes(m.get(k)); return undefined; } };
const told_page = [];
let nextSize = 0, nextType = 'cors', nextStatus = 200, nextCt = 'image/png';
globalThis.fetch = async req => /basemaps|arcgisonline/.test(req && req.url || req)
  ? mkRes({size:nextSize, type:nextType, status:nextStatus, ct:nextCt}) : mkRes({size:nextSize, ct:'text/html'});
globalThis.Response = class { static error(){return{error:true}} };
globalThis.Request = class { constructor(u,o){this.url=u;Object.assign(this,o)} };

eval(fs.readFileSync('sw.js','utf8'));

async function tileReq(url){
  let out;
  const ev = { request:{ url, method:'GET', mode:'no-cors', headers:{get:()=>''} },
               respondWith:p=>{out=p}, waitUntil:()=>{} };
  for (const f of listeners['fetch']) f(ev);
  if (out) await out;
  return out;
}
const TILE='https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/12/1686/935';
const CARTO='https://a.basemaps.cartocdn.com/rastertiles/voyager/12/935/1686@2x.png';

const tilesCache = () => [...store.keys()].find(k=>k.endsWith('-tiles'));
const nTiles = () => (store.get(tilesCache())||new Map()).size;
/* Errors are never cached: a JSON error answered as 200 ("Map data not yet available"), a 404,
   an empty body. */
nextSize = 120; nextCt = 'application/json';
await tileReq(TILE+'?err=json');
nextCt = 'image/png'; nextStatus = 404;
await tileReq(TILE+'?err=404');
nextStatus = 200; nextSize = 0;
await tileReq(TILE+'?err=empty');
const afterBad = nTiles();
/* A small, mostly transparent Esri label tile IS a real tile (BUG-B08: 22 of 24 were dropped
   by a 2,000-byte rule, so offline maps had no place names). */
nextSize = 126;
await tileReq(TILE);
const afterLabel = nTiles();

nextSize = 87968;                     // healthy tile
await tileReq(TILE+'?x=2');
const afterGood = (store.get(tilesCache())||new Map()).size;

/* CARTO answers every tile with an "API KEY REQUIRED" watermark (BUG-B01): the worker must not
   even intercept one, so it can never be cached. */
nextSize = 87968;
const cartoOut = await tileReq(CARTO);
const afterCarto = (store.get(tilesCache())||new Map()).size;

/* An opaque tile (requested without crossOrigin) must still reach the map, but never the cache:
   its size reads as 0, so the watermark check cannot vouch for it. */
nextSize = 87968; nextType = 'opaque';
const opaqueOut = await tileReq(TILE+'?x=3');
const opaqueRes = opaqueOut && await opaqueOut;
const afterOpaque = (store.get(tilesCache())||new Map()).size;
nextType = 'cors';

/* Every check counts toward the exit code. This file used to print "<-- BUG" and exit 0, so a
   service-worker regression would have sailed through CI with the word BUG in the log. */
let failed = 0;
const report = (label, ok, okText, badText) => {
  if (!ok) failed++;
  console.log('  ' + label.padEnd(31), ok ? okText : badText + '  <-- BUG');
};
report('error tile (json/404/empty) cached?', afterBad === 0, 'no   OK', 'YES (' + afterBad + ')');
report('small label tile (126b) cached?', afterLabel === 1, 'yes  OK', 'NO (offline map loses its labels)');
report('healthy tile (88KB) cached?', afterGood === 2, 'yes  OK', 'NO');
report('tile cache unversioned?', tilesCache() === 'cc-tiles', 'yes  OK', 'NO (' + tilesCache() + ')');
report('CARTO tile intercepted?', cartoOut === undefined && afterCarto === afterGood, 'no   OK (goes to network)', 'YES (watermark can be cached)');
report('opaque tile returned?', !!(opaqueRes && opaqueRes.type === 'opaque'), 'yes  OK', 'NO (map loses the tile)');
report('opaque tile cached?', afterOpaque === afterGood, 'no   OK', 'YES (unvetted tile cached)');

/* ---- data.js: a returning visitor must get NEW data when it is published ----
   The worker serves data.js cache-first by URL. For months the URL was a hand-edited "?v=9"
   that the monthly refresh never changed, so returning visitors kept their first cached copy.
   build.py now puts a hash of the content in ?v=, and this proves the worker then does the
   right thing on both sides: same URL -> no network; new URL -> fetch, and the old copy goes. */
let fetches = 0;
const realFetch = globalThis.fetch;
globalThis.fetch = async (...a) => { fetches++; return realFetch(...a); };
async function dataReq(v) {
  let out;
  const ev = { request: { url: 'https://chargeandchew.com/data.js?v=' + v, method: 'GET', mode: 'no-cors',
                          headers: { get: () => '' } }, respondWith: p => { out = p }, waitUntil: () => {} };
  for (const f of listeners['fetch']) f(ev);
  if (out) await out;
  return out;
}
const dataCache = () => store.get([...store.keys()].find(k => k.endsWith('-data'))) || new Map();
nextSize = 4_000_000;
fetches = 0; await dataReq('aaaaaaaaaa');                 // first visit
const firstFetch = fetches;
fetches = 0; await dataReq('aaaaaaaaaa');                 // revisit, data unchanged
const revisitFetch = fetches;
fetches = 0; await dataReq('bbbbbbbbbb');                 // monthly refresh published new data
const newDataFetch = fetches;
const kept = [...dataCache().keys()];
report('data: first visit downloads?', firstFetch === 1, 'yes  OK', 'NO');
report('data: unchanged -> re-download?', revisitFetch === 0, 'no   OK (served from cache)', 'YES (wasted ~1 MB)');
report('data: new ?v= -> fetches new?', newDataFetch === 1, 'yes  OK', 'NO (stale data served)');
report('data: old copy dropped?', kept.length === 1 && kept[0].endsWith('v=bbbbbbbbbb'), 'yes  OK',
       'NO (' + kept.length + ' copies)');

/* ---- level2.js is cached alongside data.js, never instead of it ---- */
{
  let out;
  const ev = { request: { url: 'https://chargeandchew.com/level2.js?v=cccccccccc', method: 'GET', mode: 'no-cors',
                          headers: { get: () => '' } }, respondWith: p => { out = p }, waitUntil: () => {} };
  for (const f of listeners['fetch']) f(ev);
  await out;
  const keys = [...dataCache().keys()];
  report('level2 cached beside data?', keys.some(k => k.includes('/level2.js')) && keys.some(k => k.includes('/data.js')),
         'yes  OK', 'NO (' + keys.join(',') + ')');
}

/* ---- an app update must not throw the dataset away ----
   The data cache used to carry the worker's VERSION, so every shell release (about twenty in
   a month) evicted the ~1 MB data.js although its content-hashed URL had not changed. */
const DATA_URL = 'https://chargeandchew.com/data.js?v=bbbbbbbbbb';
const dataName = [...store.keys()].find(k => k.endsWith('-data') || k === 'cc-data');
report('data cache unversioned?', dataName === 'cc-data', 'yes  OK', 'NO (' + dataName + ')');
store.delete('cc-data');
store.set('cc-v1-data', new Map([[DATA_URL, { size: 4_000_000 }]]));   // left by an older worker
store.set('cc-v1-shell', new Map([['https://chargeandchew.com/', { size: 1 }]]));
// a watermark an older worker cached cache-first, next to a good Esri tile
store.get('cc-tiles').set(CARTO, { size: 2049 });
// an older worker's VERSIONED tile cache: its Esri tiles must move over, its CARTO ones not (B09)
const OLD_TILE = TILE + '?old=1';
store.set('cc-v51-tiles', new Map([[OLD_TILE, { size: 5000, ct: 'image/png' }], [CARTO + '?old=1', { size: 2049 }]]));
let act; for (const f of listeners['activate']) f({ waitUntil: p => { act = p; } });
await act;
const tileKeys = [...(store.get('cc-tiles') || new Map()).keys()];
report('activate purges CARTO tiles?', !tileKeys.some(u => u.includes('cartocdn')) && tileKeys.length > 0,
       'yes  OK', 'NO (watermarks stay on the offline map)');
report('update keeps the offline map?', tileKeys.includes(TILE) && tileKeys.includes(OLD_TILE) && !store.has('cc-v51-tiles'),
       'yes  OK', 'NO (' + tileKeys.length + ' tiles; a shell release wiped the offline map)');
report('update keeps cached dataset?', !!(store.get('cc-data') && store.get('cc-data').get(DATA_URL)),
       'yes  OK', 'NO (dataset re-downloaded after every update)');
report('old caches removed?', !store.has('cc-v1-data') && !store.has('cc-v1-shell'), 'yes  OK', 'NO');

/* ---- pages: the cached copy at once, refreshed behind it (PERF-B2) ---- */
async function navReq(fetchImpl, path = '/', clientId = 'c1') {
  globalThis.fetch = fetchImpl;
  let out, waits = [];
  const ev = { request: { url: 'https://chargeandchew.com' + path, method: 'GET', mode: 'navigate', headers: { get: () => 'text/html' } },
               resultingClientId: clientId, respondWith: p => { out = p; }, waitUntil: p => waits.push(p) };
  for (const f of listeners['fetch']) f(ev);
  const t0 = Date.now(); const res = await out; const ms = Date.now() - t0;
  await Promise.all(waits.map(w => w.catch(() => {})));   // let the background refresh land
  return { res, ms };
}
const shellName = () => [...store.keys()].find(k => k.startsWith('cc-v') && k.endsWith('-shell'));
const page = (etag, size) => mkRes({ size, ct: 'text/html', etag });
store.set('cc-v52-shell', new Map([['https://chargeandchew.com/', { size: 111, ct: 'text/html', etag: 'A' }]]));   // cached page
// the network 3 s away: the cached page is served at once, the new one lands in the cache
told_page.length = 0;
const slow = await navReq(() => new Promise(r => setTimeout(() => r(page('B', 222)), 3000)), '/', 'c-slow');
report('cached page served at once?', slow.res && slow.res.__size === 111 && slow.ms < 200,
       `yes  OK (${slow.ms} ms)`, `NO (${slow.ms} ms, size ${slow.res && slow.res.__size})`);
report('background refresh cached?', store.get(shellName()).get('https://chargeandchew.com/').size === 222, 'yes  OK', 'NO');
report('changed page -> page told?', told_page.length === 1 && told_page[0][0] === 'c-slow' && told_page[0][1].type === 'page-updated',
       'yes  OK', 'NO (' + JSON.stringify(told_page) + ')');
told_page.length = 0;
const same = await navReq(async () => page('B', 222), '/', 'c-same');
report('same page -> no reload offered?', same.res.__size === 222 && told_page.length === 0, 'yes  OK', 'NO (' + JSON.stringify(told_page) + ')');

/* ---- one cached page per path, whatever the query (BUG-20) ----
   Every shared link (?q=, ?from=&to=, ?stop=) used to store its own ~420 KB copy of index.html,
   without limit, and a link never opened before missed the cache on a slow network. */
for (const q of ['/?q=starbucks', '/?from=LA&to=Vegas', '/?stop=123', '/?chain=IHOP']) await navReq(async () => page('C', 444), q);
const shellKeys = [...(store.get(shellName()) || new Map()).keys()];
report('one shell copy for all links?', shellKeys.length === 1 && shellKeys[0] === 'https://chargeandchew.com/',
       'yes  OK', 'NO (' + shellKeys.join(' ') + ')');
const unseen = await navReq(() => new Promise(r => setTimeout(() => r(page('D', 555)), 8000)), '/?from=Never&to=Seen');
report('slow, never-seen link -> cache?', unseen.res && unseen.res.__size === 444 && unseen.ms < 200,
       `yes  OK (${unseen.ms} ms)`, `NO (${unseen.ms} ms, size ${unseen.res && unseen.res.__size})`);
const offlineNav = await navReq(async () => { throw new TypeError('offline'); }, '/?q=never+seen');
// 555: the slow load above still refreshed the ONE shared copy in the background
report('offline, never-seen link -> page?', offlineNav.res && offlineNav.res.__size === 555, 'yes  OK',
       'NO (' + (offlineNav.res && (offlineNav.res.__size || 'fallback page')) + ')');
// a page with no cached copy waits for the network, up to NAV_TIMEOUT, then whatever is cached
const fresh = await navReq(async () => page('E', 666), '/trip/somewhere/');
report('uncached page -> network?', fresh.res && fresh.res.__size === 666, 'yes  OK', 'NO');
// nothing cached at all: offline, the app's own page stands in rather than an error
store.get(shellName()).set('https://chargeandchew.com/index.html', { size: 888, ct: 'text/html' });   // precached at install
const offNew = await navReq(async () => { throw new TypeError('offline'); }, '/trip/elsewhere/');
report('uncached + offline -> app page?', offNew.res && offNew.res.__size === 888, 'yes  OK', 'NO');

/* "New version — tap to reload" only for a page older than the worker: the page asks the
   installing worker its version over a MessageChannel, and must get this file's VERSION. */
let told = null;
for (const f of listeners['message'] || []) f({ data: 'version', ports: [{ postMessage: v => { told = v; } }], waitUntil: () => {} });
const swVer = (fs.readFileSync('sw.js', 'utf8').match(/const VERSION = '([^']+)'/) || [])[1];
report('tells the page its version?', told && told === swVer, `yes  OK (${told})`, `NO (${told})`);

console.log('  cache name in use:            ', [...store.keys()].join(',') || '(none)');
if (failed) { console.log(`\nservice worker: ${failed} check(s) FAILED`); process.exit(1); }
