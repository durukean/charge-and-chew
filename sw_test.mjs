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

console.log('  watermark tile (126b) cached? ', afterBad>0 ? 'YES  <-- BUG' : 'no   OK');
console.log('  healthy tile (88KB) cached?   ', afterGood>afterBad ? 'yes  OK' : 'NO   <-- BUG');
console.log('  probe request intercepted?    ', probe===undefined ? 'no   OK (goes to network)' : 'YES  <-- BUG');
console.log('  cache name in use:            ', [...store.keys()].join(',') || '(none)');
