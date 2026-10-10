import fs from 'fs';
// minimal SW environment
const listeners = {};
const store = new Map();          // cacheName -> Map(url -> {body})
const mkCache = name => ({
  async match(req){ const m=store.get(name); const k=typeof req==='string'?req:req.url; return m&&m.get(k) ? mkRes(m.get(k)) : undefined; },
  async put(req,res){ const k=typeof req==='string'?req:req.url; if(!store.has(name))store.set(name,new Map());
                      store.get(name).set(k,{size:res.__size}); },
  async keys(){ const m=store.get(name); return m?[...m.keys()].map(u=>({url:u})):[]; },
  async delete(k){ const m=store.get(name); return m?m.delete(typeof k==='string'?k:k.url):false; },
});
function mkRes({size}){ return { ok:true, status:200, type:'basic', __size:size,
  clone(){return mkRes({size})}, async arrayBuffer(){return new ArrayBuffer(size)} }; }

globalThis.self = {
  addEventListener:(t,f)=>{(listeners[t]=listeners[t]||[]).push(f)},
  location:{origin:'https://chargeandchew.com'}, skipWaiting(){}, clients:{claim(){}},
};
globalThis.caches = { open:async n=>mkCache(n), keys:async()=>[...store.keys()], delete:async n=>store.delete(n),
  async match(req){ const k=typeof req==='string'?req:req.url; for (const m of store.values()) if (m.get(k)) return mkRes(m.get(k)); return undefined; } };
let nextSize = 0;
globalThis.fetch = async () => mkRes({size:nextSize});
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
const TILE='https://a.basemaps.cartocdn.com/rastertiles/voyager/12/935/1686@2x.png';

nextSize = 126;                       // watermark / blocked tile
await tileReq(TILE);
const tilesCache = () => [...store.keys()].find(k=>k.endsWith('-tiles'));
const afterBad = (store.get(tilesCache())||new Map()).size;

nextSize = 87968;                     // healthy tile
await tileReq(TILE+'?x=2');
const afterGood = (store.get(tilesCache())||new Map()).size;

const probe = await tileReq(TILE+'?probe=1');

/* Every check counts toward the exit code. This file used to print "<-- BUG" and exit 0, so a
   service-worker regression would have sailed through CI with the word BUG in the log. */
let failed = 0;
const report = (label, ok, okText, badText) => {
  if (!ok) failed++;
  console.log('  ' + label.padEnd(31), ok ? okText : badText + '  <-- BUG');
};
report('watermark tile (126b) cached?', !(afterBad > 0), 'no   OK', 'YES');
report('healthy tile (88KB) cached?', afterGood > afterBad, 'yes  OK', 'NO');
report('probe request intercepted?', probe === undefined, 'no   OK (goes to network)', 'YES');

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

/* ---- an app update must not throw the dataset away ----
   The data cache used to carry the worker's VERSION, so every shell release (about twenty in
   a month) evicted the ~1 MB data.js although its content-hashed URL had not changed. */
const DATA_URL = 'https://chargeandchew.com/data.js?v=bbbbbbbbbb';
const dataName = [...store.keys()].find(k => k.endsWith('-data') || k === 'cc-data');
report('data cache unversioned?', dataName === 'cc-data', 'yes  OK', 'NO (' + dataName + ')');
store.delete('cc-data');
store.set('cc-v1-data', new Map([[DATA_URL, { size: 4_000_000 }]]));   // left by an older worker
store.set('cc-v1-shell', new Map([['https://chargeandchew.com/', { size: 1 }]]));
let act; for (const f of listeners['activate']) f({ waitUntil: p => { act = p; } });
await act;
report('update keeps cached dataset?', !!(store.get('cc-data') && store.get('cc-data').get(DATA_URL)),
       'yes  OK', 'NO (dataset re-downloaded after every update)');
report('old caches removed?', !store.has('cc-v1-data') && !store.has('cc-v1-shell'), 'yes  OK', 'NO');

/* ---- a slow network must not hold the page hostage ---- */
async function navReq(fetchImpl) {
  globalThis.fetch = fetchImpl;
  let out, waits = [];
  const ev = { request: { url: 'https://chargeandchew.com/', method: 'GET', mode: 'navigate', headers: { get: () => 'text/html' } },
               respondWith: p => { out = p; }, waitUntil: p => waits.push(p) };
  for (const f of listeners['fetch']) f(ev);
  const t0 = Date.now(); const res = await out; return { res, ms: Date.now() - t0 };
}
store.set('cc-v49-shell', new Map([['https://chargeandchew.com/', { size: 111 }]]));   // cached page
const slow = await navReq(() => new Promise(r => setTimeout(() => r(mkRes({ size: 222 })), 8000)));
report('slow network -> cached page?', slow.res && slow.res.__size === 111 && slow.ms < 5000,
       `yes  OK (${slow.ms} ms)`, `NO (${slow.ms} ms, size ${slow.res && slow.res.__size})`);
const fast = await navReq(async () => mkRes({ size: 333 }));
report('fast network -> fresh page?', fast.res && fast.res.__size === 333, 'yes  OK', 'NO');

console.log('  cache name in use:            ', [...store.keys()].join(',') || '(none)');
if (failed) { console.log(`\nservice worker: ${failed} check(s) FAILED`); process.exit(1); }
