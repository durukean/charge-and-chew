#!/usr/bin/env node
/* End-to-end search audit: types real queries into the real app in headless Chrome, with a
   faked phone location and a prepared starting state, and checks WHERE the app ends up.

   The parser suite (verify_search.py) checks what a query means. This checks what the app
   then does with it -- which is where "I searched X and it went to another state" lives:
   a remembered area, an area picked earlier, a refused location, a route on screen.

       node tools/search_audit.mjs                # every case
       node tools/search_audit.mjs "in n out"     # only cases whose query contains this

   Uses the network for place lookups (Nominatim) exactly like the app, one at a time, and
   keeps one browser profile so each place is looked up once. Not part of check.sh.
*/
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CHROME = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium']
  .find(p => existsSync(p));
/* --quick: a handful of cases that need nothing from the network (outside services are
   blocked), for check.sh. The full run needs the internet and ~20 minutes. */
const QUICK = process.argv.includes('--quick');
const ONLY = process.argv.slice(2).find(a => !a.startsWith('--')) || '';
const sleep = ms => new Promise(r => setTimeout(r, ms));

/* ── where people are ── */
const LOC = {
  LA: [34.0983, -118.3267], DAL: [32.7767, -96.797], NYC: [40.7505, -73.9934],
  CHI: [41.8781, -87.6298], SEA: [47.6062, -122.3321], MIA: [25.7617, -80.1918],
};
const TZ = { LA: 'America/Los_Angeles', DAL: 'America/Chicago', NYC: 'America/New_York',
             CHI: 'America/Chicago', SEA: 'America/Los_Angeles', MIA: 'America/New_York' };

/* ── expectations ──
   near: [placeKey or [lat,lon], miles]  the area searched (or, with no area, the first
                                         result) is within that distance
   st:   'TX'                            the area searched is in that state (by its label),
                                         or else most of the first five results are
   chain / cat / route / hwy / empty     what the search should have set
   clear: true                           then tap the search box's x: the rest is judged after
   toast: 'text'                         the message shown contains this */
function C(who, prior, q, expect, note) { return { who, prior, q, expect, note }; }
const CASES = [
  // ── a chain, no place: means near me ──
  ...['in n out', 'In-N-Out', 'in n out burger', 'in & out', 'starbucks', 'ihop', 'chick fil a',
      'mcdonalds', 'costco', 'target', 'ihops', 'walmat', 'costo', 'taco bells'].map(q =>
    C('LA', 'fresh', q, { near: ['LA', 40] })),
  // none in California: the nearest ones (Arizona), not an empty Los Angeles
  C('LA', 'fresh', 'whataburger', { near: ['LA', 450] }),
  C('LA', 'fresh', 'waffle house', { near: ['LA', 450] }),
  C('DAL', 'fresh', 'buc-ees', { near: ['DAL', 60] }),
  C('DAL', 'fresh', 'whataburger', { near: ['DAL', 30] }),
  C('NYC', 'fresh', 'dunkin', { near: ['NYC', 30] }),
  C('NYC', 'fresh', 'in n out', { near: ['NYC', 2500] }, 'no In-N-Out near NYC: nearest ones, not an empty map'),
  C('CHI', 'fresh', 'portillos', { near: ['CHI', 2500] }, 'not a tracked chain'),
  C('SEA', 'fresh', 'starbucks near me', { near: ['SEA', 30] }),
  C('MIA', 'fresh', 'publix', { near: ['MIA', 30] }),

  // ── same, but a remembered area from a previous visit (New York) ──
  C('LA', 'restoredNY', 'in n out', { near: ['LA', 40] }),
  C('LA', 'restoredNY', 'starbucks', { near: ['LA', 40] }),
  C('LA', 'restoredNY', 'ice cream', { near: ['LA', 40] }),
  C('LA', 'restoredNY', 'tacos', { near: ['LA', 40] }),
  C('denied', 'restoredNY', 'starbucks', { near: ['NYC', 40] }, 'no location: the remembered area, said so'),
  C('denied', 'restoredNY', 'in n out', { near: ['NYC', 2500] }, 'no location + none there: nearest'),

  // ── remembered area, location only available by the time they search (a slow phone) ──
  C('LA-late', 'restoredNY', 'in n out', { near: ['LA', 40] }, '@late'),
  C('LA-late', 'restoredNY', 'starbucks', { near: ['LA', 40] }, '@late'),
  C('LA-late', 'restoredNY', 'tacos', { near: ['LA', 40] }, '@late'),
  C('LA-late', 'fresh', 'ihop', { near: ['LA', 40] }, '@late'),

  // ── an area picked in this visit (New York), then a chain ──
  C('LA', 'chosenNY', 'starbucks', { near: ['NYC', 40] }, 'refining the area on screen'),
  C('LA', 'chosenNY', 'in n out', { near: ['LA', 40] }, 'none in NY: look near me'),
  C('denied', 'chosenNY', 'in n out', { near: ['NYC', 2500] }),
  C('LA', 'chosenNY', 'starbucks near me', { near: ['LA', 40] }),

  // ── a route on screen, then a chain ──
  C('LA', 'route', 'starbucks', { route: true, chain: 'Starbucks' }),
  C('LA', 'route', 'in n out', { route: true, chain: 'In-N-Out' }),
  C('LA', 'route', 'ice cream', { route: true }),

  // ── no location at all ──
  C('denied', 'fresh', 'starbucks', { near: ['LA', 400] }, 'time-zone guess: California'),
  C('denied', 'fresh', 'ice cream', { near: ['LA', 400] }),

  // ── places ──
  ...[
    ['chargers in austin', 'TX'], ['ihop in dallas', 'TX'], ['starbucks in denver', 'CO'],
    ['in n out in fresno', 'CA'], ['in n out burger in fresno', 'CA'], ['tacos in phoenix', 'AZ'],
    ['ice cream in portland', 'OR'], ['chargers in portland maine', 'ME'], ['portland, me', 'ME'],
    ['springfield il', 'IL'], ['springfield missouri', 'MO'], ['kansas city', 'MO'],
    ['columbus ohio', 'OH'], ['columbus', 'OH'], ['san jose', 'CA'], ['sf', 'CA'],
    ['nyc', 'NY'], ['vegas', 'NV'], ['philly', 'PA'], ['nola', 'LA'], ['dc', 'DC'],
    ['90210', 'CA'], ['10001', 'NY'], ['75201', 'TX'], ['chargers in 30303', 'GA'],
    ['buc-ees in texas', 'TX'], ['waffle house in georgia', 'GA'], ['texas', 'TX'],
    ['santa monica', 'CA'], ['palm springs', 'CA'], ['lake tahoe', 'CA'], ['moab', 'UT'],
    ['flagstaff', 'AZ'], ['bakersfield', 'CA'], ['barstow', 'CA'], ['baker ca', 'CA'],
    ['kettleman city', 'CA'], ['tejon ranch', 'CA'], ['harris ranch', 'CA'],
    ['starbucks near seattle', 'WA'], ['chargers near boston', 'MA'], ['costco in san diego', 'CA'],
    ['target in miami', 'FL'], ['ihop near orlando', 'FL'], ['mcdonalds in chicago', 'IL'],
    ['wendys in wendover', 'NV'], ['denny\'s in dennis ma', 'MA'], ['taco bell in el paso', 'TX'],
    ['supercharger in st louis', 'MO'], ['fort worth', 'TX'], ['st. petersburg fl', 'FL'],
    ['washington', 'DC'], ['georgia', 'GA'], ['new york', 'NY'], ['charlotte', 'NC'],
    ['wilmington nc', 'NC'], ['jackson ms', 'MS'], ['jackson hole', 'WY'], ['the woodlands', 'TX'],
    ['jackson, ms', 'MS'], ['columbus ga', 'GA'], ['charleston wv', 'WV'], ['salem or', 'OR'],
    ['portland or', 'OR'], ['springfield mo', 'MO'], ['paris tx', 'TX'], ['wawas in philly', 'PA'],
  ].map(([q, st]) => C('LA', 'fresh', q, { st })),

  // ── one-word towns that exist in several states: the nearby one ──
  C('LA', 'fresh', 'pasadena', { st: 'CA' }, '@amb'),
  C('LA', 'fresh', 'glendale', { st: 'CA' }, '@amb'),
  C('LA', 'fresh', 'burbank', { st: 'CA' }, '@amb'),
  C('LA', 'fresh', 'ontario', { st: 'CA' }, '@amb'),
  C('LA', 'fresh', 'hollywood', { st: 'CA' }, '@amb'),
  C('DAL', 'fresh', 'arlington', { st: 'TX' }, '@amb'),
  C('DAL', 'fresh', 'irving', { st: 'TX' }, '@amb'),
  C('DAL', 'fresh', 'paris', { st: 'TX' }, '@amb'),
  C('DAL', 'fresh', 'pasadena', { st: 'TX' }, '@amb'),
  C('CHI', 'fresh', 'aurora', { st: 'IL' }, '@amb'),
  C('CHI', 'fresh', 'naperville', { st: 'IL' }, '@amb'),
  C('CHI', 'fresh', 'springfield', { st: 'IL' }, '@amb'),
  C('CHI', 'fresh', 'columbus', { st: 'OH' }, '@amb'),
  C('SEA', 'fresh', 'vancouver', { st: 'WA' }, '@amb'),
  C('SEA', 'fresh', 'portland', { st: 'OR' }, '@amb'),
  C('SEA', 'fresh', 'bellevue', { st: 'WA' }, '@amb'),
  C('NYC', 'fresh', 'portland', { st: 'ME' }, '@amb'),
  C('NYC', 'fresh', 'princeton', { st: 'NJ' }, '@amb'),
  C('NYC', 'fresh', 'greenwich', { st: 'CT' }, '@amb'),
  C('NYC', 'fresh', 'arlington', { st: 'VA' }, '@amb'),
  C('MIA', 'fresh', 'naples', { st: 'FL' }, '@amb'),
  C('MIA', 'fresh', 'jacksonville', { st: 'FL' }, '@amb'),
  C('MIA', 'fresh', 'aventura', { st: 'FL' }, '@amb'),
  // ── landmarks people steer by ──
  C('LA', 'fresh', 'disneyland', { st: 'CA' }, '@amb'),
  C('LA', 'fresh', 'lax', { st: 'CA' }, '@amb'),
  C('LA', 'fresh', 'chargers near lax', { st: 'CA' }, '@amb'),
  C('LA', 'fresh', 'santa monica pier', { st: 'CA' }, '@amb'),
  C('NYC', 'fresh', 'times square', { st: 'NY' }, '@amb'),
  C('NYC', 'fresh', 'jfk', { st: 'NY' }, '@amb'),
  C('SEA', 'fresh', 'sea-tac', { st: 'WA' }, '@amb'),
  C('LA', 'fresh', 'yosemite', { st: 'CA' }, '@amb'),
  C('LA', 'fresh', 'grand canyon', { st: 'AZ' }, '@amb'),
  C('LA', 'fresh', 'zion national park', { st: 'UT' }, '@amb'),
  // ── a route with tricky ends ──
  C('LA', 'fresh', 'jackson ms to new orleans', { route: true }, '@amb'),
  C('LA', 'fresh', 'portland me to boston', { route: true }, '@amb'),
  C('LA', 'fresh', 'from here to san diego', { route: true }, '@amb'),
  C('LA', 'fresh', 'disneyland to vegas', { route: true }, '@amb'),

  // ── a kind of place (looked up live) plus a town: the town, not where you are ──
  C('LA', 'fresh', 'pharmacy in denver', { st: 'CO' }, '@poi'),
  C('LA', 'fresh', 'coffee in austin', { st: 'TX' }, '@poi'),
  C('LA', 'fresh', 'gas station in reno', { st: 'NV' }, '@poi'),
  C('LA', 'fresh', 'tire shop in phoenix', { st: 'AZ' }, '@poi'),
  C('LA', 'fresh', 'grocery store in boise', { st: 'ID' }, '@poi'),
  C('LA', 'fresh', 'bank near seattle', { st: 'WA' }, '@poi'),
  C('LA', 'fresh', 'gym in miami', { st: 'FL' }, '@poi'),
  C('LA', 'fresh', 'bakery in portland', { st: 'OR' }, '@poi'),
  C('LA', 'fresh', 'pharmacy', { near: ['LA', 40] }, '@poi'),
  C('LA', 'fresh', 'bank near me', { near: ['LA', 40] }, '@poi'),
  C('LA', 'chosenNY', 'pharmacy', { near: ['NYC', 40] }, '@poi'),

  // ── what the previous search set must not leak into the next ──
  C('LA', 'poiDenver', 'lax', { st: 'CA', nochain: true }, '@leak'),
  C('LA', 'poiDenver', 'chargers in austin', { st: 'TX', nochain: true }, '@leak'),
  C('LA', 'starbucks', 'chargers in dallas', { st: 'TX', nochain: true }, '@leak'),
  C('LA', 'starbucks', 'ihop in dallas', { st: 'TX', chain: 'IHOP' }, '@leak'),

  // ── trips and roads ──
  C('LA', 'fresh', 'la to vegas', { route: true }),
  C('LA', 'fresh', 'sf to la with in n out', { route: true, chain: 'In-N-Out' }),
  C('LA', 'fresh', 'dallas to houston', { route: true }),
  C('LA', 'fresh', 'on my way to vegas', { route: true }),
  C('LA', 'fresh', 'i-5', { hwy: 'I-5' }),
  C('LA', 'fresh', 'i 95 starbucks', { hwy: 'I-95' }),

  // ── odd but real things people type ──
  C('LA', 'fresh', 'food', { near: ['LA', 40] }),
  C('LA', 'fresh', 'coffee', { near: ['LA', 40] }),
  C('LA', 'fresh', 'charger', { near: ['LA', 40] }),
  C('LA', 'fresh', 'supercharger', { near: ['LA', 40] }),
  C('LA', 'fresh', 'tesla', { near: ['LA', 40] }),
  C('LA', 'fresh', 'chargers near me', { near: ['LA', 40] }),
  C('LA', 'fresh', 'where can i eat while charging', { near: ['LA', 40] }),
  C('LA', 'fresh', 'fast charger with bathroom', { near: ['LA', 40] }),
  C('LA', 'fresh', 'burgers', { near: ['LA', 40] }),
  C('LA', 'fresh', 'pizza', { near: ['LA', 40] }),
  C('LA', 'fresh', 'starbuck', { near: ['LA', 40] }),
  C('LA', 'fresh', 'chik fil a', { near: ['LA', 40] }),
  C('LA', 'fresh', 'mcdonald', { near: ['LA', 40] }),
  C('LA', 'fresh', 'ihop near the airport', { near: ['LA', 40] }),
  C('LA', 'fresh', 'grocery store', { near: ['LA', 40] }),
  C('LA', 'fresh', 'walmart supercenter', { near: ['LA', 40] }),
  C('LA', 'fresh', 'electrify america', { near: ['LA', 40] }),
  C('LA', 'fresh', 'evgo near me', { near: ['LA', 40] }),
  C('LA', 'fresh', '350 kw', { near: ['LA', 40] }),
  C('LA', 'fresh', 'ccs', { near: ['LA', 40] }),
  // towns with the place lookup down (--quick blocks it): found from the chargers' own towns
  C('LA', 'fresh', 'ihop in austin', { st: 'TX', chain: 'IHOP' }, '@offline'),
  // a junk hit is not a place: "n out" was a hiking path in Colorado
  C('LA', 'fresh', 'n out', { near: ['LA', 30] }, '@junk'),
  // Probe 2026-10-28: a destination in other words, regions, "downtown", a cuisine in a town
  C('LA', 'fresh', 'directions to san diego', { route: true }, '@probe'),
  C('LA', 'fresh', 'take me to vegas', { route: true }, '@probe'),
  C('LA', 'fresh', 'route to vegas', { route: true }, '@probe'),
  C('LA', 'fresh', 'downtown la', { near: ['LA', 15], st: 'CA' }, '@probe'),
  C('NYC', 'fresh', 'bay area', { near: [[37.7749, -122.4194], 20] }, '@probe'),
  C('LA', 'fresh', 'socal', { near: ['LA', 20] }, '@probe'),
  C('LA', 'fresh', 'bbq in austin', { st: 'TX' }, '@probe'),
  C('LA', 'fresh', 'steakhouse in dallas', { st: 'TX' }, '@probe'),
  C('NYC', 'fresh', 'chargers in ca', { st: 'CA' }, '@probe'),
  C('LA', 'fresh', 'buc-ees in tx', { st: 'TX', chain: "Buc-ee's" }, '@probe'),
  C('LA', 'fresh', 'starbucks in wa', { st: 'WA', chain: 'Starbucks' }, '@probe'),
  C('LA', 'fresh', 'in n out in az', { st: 'AZ', chain: 'In-N-Out' }, '@probe'),
  C('LA', 'fresh', 'us 101', { toast: "can't follow US-101" }, '@probe'),
  C('LA', 'fresh', 'pch', { toast: "can't follow the Pacific Coast Highway" }, '@probe'),
  C('LA', 'fresh', '123 main st boise', { st: 'ID' }, '@probe'),
  C('LA', 'fresh', '500 broadway nashville', { st: 'TN' }, '@probe'),
  // the search box's x undoes the search: back where you were, the chain it set gone
  C('LA', 'fresh', 'in n out', { clear: true, near: ['LA', 30], nochain: true }, '@clear'),
  C('LA', 'fresh', 'buc-ees', { clear: true, near: ['LA', 30], nochain: true }, '@clear'),
  C('LA', 'fresh', 'starbucks in austin', { clear: true, near: ['LA', 30], nochain: true }, '@clear'),
  C('LA', 'fresh', 'buc-ees in texas', { clear: true, near: ['LA', 30], nochain: true }, '@clear'),
  C('LA', 'fresh', 'pharmacy in denver', { clear: true, near: ['LA', 30], nochain: true }, '@clear'),
  C('denied', 'fresh', 'starbucks', { clear: true, nochain: true }, '@clear'),
];

const QUICK_SET = new Set([
  'LA|fresh|in n out', 'LA|fresh|ihops', 'LA|fresh|walmat', 'LA|fresh|tacos',
  'NYC|fresh|in n out', 'NYC|fresh|dunkin', 'LA|restoredNY|starbucks', 'LA|restoredNY|in n out',
  'denied|restoredNY|in n out', 'denied|fresh|starbucks', 'LA|fresh|chargers near me',
  'LA-late|restoredNY|in n out', 'LA-late|restoredNY|starbucks',
  'LA|fresh|ihop in austin', 'DAL|fresh|pasadena', 'LA|fresh|pasadena', 'NYC|fresh|portland', 'SEA|fresh|portland',
  'LA|fresh|springfield il', 'LA|fresh|us 101', 'LA|fresh|pch', 'NYC|fresh|bay area', 'LA|fresh|downtown la', 'LA|fresh|buc-ees', 'LA|fresh|starbucks in austin', 'LA|fresh|springfield missouri', 'LA|fresh|columbus ohio', 'LA|fresh|chargers in austin',
]);
const BLOCK = ['*nominatim.openstreetmap.org*', '*overpass*', '*router.project-osrm.org*', '*arcgisonline.com*',
  '*basemaps.cartocdn.com*', '*goatcounter*', '*gc.zgo.at*', '*fonts.g*'];

/* ── tiny CDP client ── */
async function cdpConnect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0; const pending = new Map();
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
  };
  const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
    const i = ++id; pending.set(i, { res, rej });
    ws.send(JSON.stringify({ id: i, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  return { send, close: () => ws.close() };
}

function startServer() {
  return new Promise((res, rej) => {
    const p = spawn('python3', ['-u', '-m', 'http.server', '0', '--bind', '127.0.0.1'], { cwd: ROOT });
    p.stdout.on('data', d => { const m = String(d).match(/port (\d+)/); if (m) res({ p, port: +m[1] }); });
    p.stderr.on('data', d => { const m = String(d).match(/port (\d+)/); if (m) res({ p, port: +m[1] }); });
    setTimeout(() => rej(new Error('server did not start')), 8000);
  });
}

async function startChrome(profile) {
  const p = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check', '--window-size=420,900', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  const ws = await new Promise((res, rej) => {
    p.stderr.on('data', d => { const m = String(d).match(/DevTools listening on (ws:\/\/\S+)/); if (m) res(m[1]); });
    setTimeout(() => rej(new Error('chrome did not start')), 15000);
  });
  return { p, ws };
}

const miles = (a, b) => {
  const R = 3958.8, t = Math.PI / 180;
  const x = Math.sin((b[0] - a[0]) * t / 2) ** 2 + Math.cos(a[0] * t) * Math.cos(b[0] * t) * Math.sin((b[1] - a[1]) * t / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
};

async function main() {
  if (!CHROME) { console.log('SKIP: Chrome not found'); return; }
  const { p: srv, port } = await startServer();
  const profile = mkdtempSync(join(tmpdir(), 'cc-audit-'));
  const { p: chrome, ws } = await startChrome(profile);
  const B = await cdpConnect(ws);
  const ORIGIN = `http://127.0.0.1:${port}`;
  // "@tag" selects by note, anything else by query text
  const cases = CASES.filter(c => QUICK ? QUICK_SET.has(`${c.who}|${c.prior}|${c.q}`)
    : !ONLY || (ONLY.startsWith('@') ? (c.note || '').includes(ONLY) : c.q.includes(ONLY)));
  let pass = 0; const fails = [];

  for (const c of cases) {
    const { targetId } = await B.send('Target.createTarget', { url: 'about:blank' });
    const { sessionId: S } = await B.send('Target.attachToTarget', { targetId, flatten: true });
    const send = (m, p) => B.send(m, p, S);
    const ev = async expr => {
      const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    };
    let res, err = null;
    try {
      await send('Page.enable'); await send('Runtime.enable');
      if (QUICK) { await send('Network.enable'); await send('Network.setBlockedURLs', { urls: BLOCK }); }
      const late = c.who.endsWith('-late');          // location refused at start-up, given before the search
      const who = late ? c.who.slice(0, -5) : c.who;
      if (c.who === 'denied' || late) {
        await B.send('Browser.setPermission', { origin: ORIGIN, permission: { name: 'geolocation' }, setting: 'denied' });
        await send('Emulation.setTimezoneOverride', { timezoneId: 'America/Los_Angeles' });
      } else {
        await B.send('Browser.setPermission', { origin: ORIGIN, permission: { name: 'geolocation' }, setting: 'granted' });
        const [la, lo] = LOC[who];
        await send('Emulation.setGeolocationOverride', { latitude: la, longitude: lo, accuracy: 30 });
        await send('Emulation.setTimezoneOverride', { timezoneId: TZ[who] });
      }
      await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
      // A clean slate for this origin, except the place-lookup cache (be kind to Nominatim).
      await send('Page.navigate', { url: ORIGIN + '/favicon.svg' }); await sleep(300);
      await ev(`Object.keys(localStorage).filter(k => !k.startsWith('cc_geo')).forEach(k => localStorage.removeItem(k));
                localStorage.setItem('cc_hero', '0'); true`);
      if (c.prior === 'restoredNY')
        await ev(`localStorage.setItem('cc_area', JSON.stringify({ lat: 40.7128, lon: -74.006, label: 'New York, NY', kind: 'place', r: 25, t: Date.now() })); true`);
      await send('Page.navigate', { url: ORIGIN + '/?nosw=1' });
      // ready when the data is in and the boot-time location attempt has settled
      for (let i = 0; i < 80; i++) { await sleep(250); if (await ev(`typeof window.__ccState === 'function' && window.__ccState().ready`).catch(() => false)) break; }
      await sleep(2500);
      const search = async q => {
        await ev(`(() => { const i = document.getElementById('placeIn'); i.value = ${JSON.stringify(q)};
          i.dispatchEvent(new Event('input', { bubbles: true }));
          i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })); return true; })()`);
        // settled: nothing busy and the visible state unchanged for 1.5 s (max 20 s). A trip
        // or a road waits for its route: the routing server can take seconds to answer.
        const wantsRoute = await ev(`!!(window.__parseTrip(${JSON.stringify(q)}) || window.__parseQuery(${JSON.stringify(q)}).hwy)`);
        let last = '', same = 0;
        for (let i = 0; i < 80 && (same < 6 || (wantsRoute && !last.includes('|true|') && i < 80)); i++) {
          await sleep(250);
          const sig = await ev(`(() => { const s = window.__ccState(); return [s.busy, JSON.stringify(s.center), s.route, s.chains.join(), s.title].join('|'); })()`);
          same = sig === last && !sig.startsWith('true') ? same + 1 : 0; last = sig;
        }
      };
      if (late) {
        await B.send('Browser.setPermission', { origin: ORIGIN, permission: { name: 'geolocation' }, setting: 'granted' });
        const [la, lo] = LOC[who];
        await send('Emulation.setGeolocationOverride', { latitude: la, longitude: lo, accuracy: 30 });
      }
      if (c.prior === 'chosenNY') await search('chargers in new york');
      if (c.prior === 'route') await search('la to las vegas');
      if (c.prior === 'poiDenver') await search('pharmacy in denver');
      if (c.prior === 'starbucks') await search('starbucks in austin');
      await search(c.q);
      if (c.expect.clear) { await ev(`document.getElementById('placeClr').click(), true`); await sleep(1500); }
      res = await ev(`window.__ccState()`);
    } catch (e) { err = e.message; }
    await B.send('Target.closeTarget', { targetId }).catch(() => {});

    // ── judge ──
    const why = [];
    if (err) why.push('error: ' + err);
    else {
      const x = c.expect;
      if (x.near) {
        const pt = typeof x.near[0] === 'string' ? LOC[x.near[0]] : x.near[0];
        const at = res.center ? [res.center.lat, res.center.lon] : res.first[0] ? [res.first[0].lat, res.first[0].lon] : null;
        if (!at) why.push('no area and no results');
        else if (miles(at, pt) > x.near[1]) why.push(`landed ${Math.round(miles(at, pt))} mi from ${x.near[0]} (${res.center ? res.center.label : res.first[0].name + ', ' + res.first[0].st})`);
        if (!res.n) why.push('no results');
      }
      if (x.st) {
        const lab = res.center && res.center.label || '';
        const inLabel = new RegExp(`(,\\s*|\\b)${x.st}\\b`).test(lab) || (x.st === 'DC' && /washington|\bdc\b/i.test(lab));
        const sts = res.first.map(f => f.st);
        const most = sts.filter(s => s === x.st).length >= Math.min(3, sts.length);
        if (!inLabel && !(most && sts.length)) why.push(`wanted ${x.st}, got "${lab}" / results ${sts.join(',')}`);
      }
      if (x.route && !res.route) why.push('no route drawn');
      if (x.hwy && res.hwy !== x.hwy) why.push(`wanted ${x.hwy}, got ${res.hwy}`);
      if (x.chain && !res.chains.includes(x.chain)) why.push(`chain ${x.chain} not set (${res.chains})`);
      if (x.nochain && res.chains.length) why.push(`a filter stayed on: ${res.chains}`);
      if (x.toast && !(res.toast || '').includes(x.toast)) why.push(`wanted a toast with "${x.toast}", got "${res.toast}"`);
    }
    const tag = `${c.who.padEnd(6)} ${c.prior.padEnd(10)} ${JSON.stringify(c.q)}`;
    if (why.length) { fails.push({ c, why, res }); console.log(`FAIL  ${tag}\n        ${why.join('; ')}\n        title: ${res && res.title} | toast: ${res && res.toast}`); }
    else { pass++; console.log(`ok    ${tag}  -> ${res.center ? res.center.label : res.route ? 'route' : res.first[0] ? res.first[0].name + ', ' + res.first[0].st : '-'}`); }
  }
  console.log(`\nsearch audit: ${pass}/${cases.length} pass`);
  B.close(); chrome.kill(); srv.kill();
  try { rmSync(profile, { recursive: true, force: true }); } catch (e) {}
  process.exit(fails.length ? 1 : 0);
}
main().catch(e => { console.error(e); process.exit(2); });
