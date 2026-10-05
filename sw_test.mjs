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
globalThis.caches = { open:async n=>mkCache(n), keys:async()=>[...store.keys()], delete:async n=>store.delete(n) };
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

console.log('  cache name in use:            ', [...store.keys()].join(',') || '(none)');
if (failed) { console.log(`\nservice worker: ${failed} check(s) FAILED`); process.exit(1); }
