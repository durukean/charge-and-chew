#!/usr/bin/env node
/* Search, checked for EVERY chain, from all over the country -- with the right answer worked
   out from the app's own data instead of written by hand.

   tools/search_audit.mjs checks hand-picked cases. This asks the question for all of them:
   "type a chain's name; does the app show the stops nearest to me?" For each chain and each
   place a person could be, the expected answer is computed from the shipped data: the
   nearest stop with that chain, and whether any is within the 25-mile area. Then the real
   app is driven in headless Chrome with that location faked, and its first listed stop must
   be that close.

       node tools/search_matrix.mjs near     every chain x 12 locations x (located / late / no location)
       node tools/search_matrix.mjs in       every chain "in <city>" x 6 cities
       node tools/search_matrix.mjs in --offline   the same with the place lookup down
       node tools/search_matrix.mjs places   every nickname, landmark and town alias the app knows
       node tools/search_matrix.mjs kinds    every kind of place ("pharmacy", "gym") near you and in a town

   "near" runs with every outside service blocked (deterministic, offline). The others look
   places up on Nominatim / Overpass like the app does. Several isolated browser contexts run
   in parallel; a full "near" run is ~30 minutes.
*/
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CHROME = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium']
  .find(p => existsSync(p));
const MODE = process.argv[2] || 'near';
const WORKERS = +(process.argv.find(a => a.startsWith('--workers=')) || '--workers=4').split('=')[1];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const miles = (a, b) => {
  const R = 3958.8, t = Math.PI / 180;
  const x = Math.sin((b[0] - a[0]) * t / 2) ** 2 + Math.cos(a[0] * t) * Math.cos(b[0] * t) * Math.sin((b[1] - a[1]) * t / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
};

// Where people are: big cities, and places where the nearest of most chains is a long way off.
const LOCS = {
  'Los Angeles': [34.0983, -118.3267, 'America/Los_Angeles'], 'San Francisco': [37.7749, -122.4194, 'America/Los_Angeles'],
  'Seattle': [47.6062, -122.3321, 'America/Los_Angeles'], 'Phoenix': [33.4484, -112.074, 'America/Phoenix'],
  'Dallas': [32.7767, -96.797, 'America/Chicago'], 'Chicago': [41.8781, -87.6298, 'America/Chicago'],
  'Atlanta': [33.749, -84.388, 'America/New_York'], 'Miami': [25.7617, -80.1918, 'America/New_York'],
  'New York': [40.7505, -73.9934, 'America/New_York'], 'Cheyenne WY': [41.14, -104.8202, 'America/Denver'],
  'Bozeman MT': [45.677, -111.0429, 'America/Denver'], 'Bangor ME': [44.8016, -68.7712, 'America/New_York'],
};
const LATE = ['Los Angeles', 'Dallas', 'New York', 'Bozeman MT'];
// The app's time-zone guess when there is no location (TZ_ORIGIN in index.html).
const TZ_ORIGIN = { 'America/Los_Angeles': [34.05, -118.24], 'America/Chicago': [41.88, -87.63], 'America/New_York': [40.71, -74.01] };
const CITIES = { 'los angeles': 'CA', 'austin': 'TX', 'denver': 'CO', 'chicago': 'IL', 'atlanta': 'GA', 'boston': 'MA' };
const BLOCK = ['*nominatim.openstreetmap.org*', '*overpass*', '*router.project-osrm.org*', '*arcgisonline.com*',
  '*basemaps.cartocdn.com*', '*goatcounter*', '*gc.zgo.at*', '*fonts.g*'];
const BLOCK_TILES = BLOCK.filter(u => !/nominatim|overpass/.test(u));

/* ── CDP plumbing ── */
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
    const on = d => { const m = String(d).match(/port (\d+)/); if (m) res({ p, port: +m[1] }); };
    p.stdout.on('data', on); p.stderr.on('data', on);
    setTimeout(() => rej(new Error('server did not start')), 8000);
  });
}
async function startChrome(profile) {
  const p = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  const ws = await new Promise((res, rej) => {
    p.stderr.on('data', d => { const m = String(d).match(/DevTools listening on (ws:\/\/\S+)/); if (m) res(m[1]); });
    setTimeout(() => rej(new Error('chrome did not start')), 15000);
  });
  return { p, ws };
}

/* One worker = one isolated browser context (its own storage) and one tab. */
async function makeWorker(B, ORIGIN, block) {
  const { browserContextId } = await B.send('Target.createBrowserContext', { disposeOnDetach: true });
  const { targetId } = await B.send('Target.createTarget', { url: 'about:blank', browserContextId });
  const { sessionId: S } = await B.send('Target.attachToTarget', { targetId, flatten: true });
  const send = (m, p) => B.send(m, p, S);
  const ev = async expr => {
    const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  };
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Network.setBlockedURLs', { urls: block });
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  const perm = setting => B.send('Browser.setPermission', { origin: ORIGIN, browserContextId, permission: { name: 'geolocation' }, setting });

  /* Load the app fresh at a location. geo: [lat, lon] | null (refused) ; late: refused at
     start-up, given before the search. restored: a remembered area from a previous visit. */
  async function open({ geo, tz, late, restored }) {
    await perm(geo && !late ? 'granted' : 'denied');
    if (geo) await send('Emulation.setGeolocationOverride', { latitude: geo[0], longitude: geo[1], accuracy: 30 });
    await send('Emulation.setTimezoneOverride', { timezoneId: tz });
    await send('Page.navigate', { url: ORIGIN + '/favicon.svg' }); await sleep(150);
    await ev(`Object.keys(localStorage).filter(k => !k.startsWith('cc_geo') && !k.startsWith('cc_ovp')).forEach(k => localStorage.removeItem(k));
              localStorage.setItem('cc_hero', '0');
              ${restored ? `localStorage.setItem('cc_area', JSON.stringify({ lat: ${restored[0]}, lon: ${restored[1]}, label: 'Remembered', kind: 'place', r: 25, t: Date.now() }));` : ''} true`);
    await send('Page.navigate', { url: ORIGIN + '/?nosw=1' });
    for (let i = 0; i < 120; i++) { await sleep(150); if (await ev(`typeof window.__ccState === 'function' && window.__ccState().ready`).catch(() => false)) break; }
    await sleep(1200);                       // the start-up location attempt
    if (late) await perm('granted');
  }
  async function search(q, wantsRoute) {
    await ev(`(() => { const i = document.getElementById('placeIn'); i.value = ${JSON.stringify(q)};
      i.dispatchEvent(new Event('input', { bubbles: true }));
      i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })); return true; })()`);
    let last = '', same = 0;
    for (let i = 0; i < 100 && same < 5; i++) {
      await sleep(200);
      const sig = await ev(`(() => { const s = window.__ccState(); return [s.busy, JSON.stringify(s.center), s.route, s.chains.join(), s.title, s.n].join('|'); })()`);
      same = sig === last && !sig.startsWith('true') ? same + 1 : 0; last = sig;
    }
    return ev(`window.__ccState()`);
  }
  return { ev, open, search, close: () => B.send('Target.disposeBrowserContext', { browserContextId }).catch(() => {}) };
}

/* ── the expected answers, from the shipped data ── */
function dataIndex(D) {
  const byBrand = {};
  for (const s of D.sites) {
    const m = D.matches[s.id]; if (!m) continue;
    for (const k of Object.keys(m)) (byBrand[k] = byBrand[k] || []).push([s.lat, s.lon, !!s.dlr]);
  }
  /* Inside an area the list leads with public stations and dealer lots follow -- but every
     stop in the area is within it, so "within the area" still holds. Outside one (the nearest
     ones, nationwide) it is plain distance. Either way: the first stop is about the nearest. */
  const nearest = (k, p) => { let d = Infinity; for (const q of byBrand[k] || []) d = Math.min(d, miles(p, q)); return d; };
  return { brands: Object.keys(D.brands), nearest };
}

async function main() {
  if (!CHROME) { console.log('SKIP: Chrome not found'); return; }
  const { p: srv, port } = await startServer();
  const ORIGIN = `http://127.0.0.1:${port}`;
  const profile = mkdtempSync(join(tmpdir(), 'cc-matrix-'));
  const { p: chrome, ws } = await startChrome(profile);
  const B = await cdpConnect(ws);

  // read the data once, in a page, to work out the answers
  const probe = await makeWorker(B, ORIGIN, BLOCK);
  await probe.open({ geo: null, tz: 'America/Los_Angeles' });
  const D = await probe.ev(`({ sites: window.PITSTOP_DATA.sites.map(s => ({ id: s.id, lat: s.lat, lon: s.lon, dlr: s.dlr ? 1 : 0 })),
                                matches: Object.fromEntries(Object.entries(window.PITSTOP_DATA.matches).map(([k, v]) => [k, Object.fromEntries(Object.keys(v).map(b => [b, 1]))])),
                                brands: window.PITSTOP_DATA.brands })`);
  const IDX = dataIndex(D);
  const qFor = k => k.toLowerCase().replace(/[.]/g, '');    // how a person types it

  const cases = [];
  if (MODE === 'near') {
    for (const k of IDX.brands) {
      for (const [name, [la, lo, tz]] of Object.entries(LOCS)) cases.push({ k, q: qFor(k), at: name, geo: [la, lo], tz });
      for (const name of LATE) { const [la, lo, tz] = LOCS[name]; cases.push({ k, q: qFor(k), at: name + ' (late, remembered NY)', geo: [la, lo], tz, late: true, restored: [40.7128, -74.006] }); }
      for (const tz of Object.keys(TZ_ORIGIN)) cases.push({ k, q: qFor(k), at: 'no location, ' + tz, geo: null, tz, origin: TZ_ORIGIN[tz] });
    }
  } else if (MODE === 'places') {
    /* Every town alias the app carries (CITY_ALIAS in index.html), typed alone, from LA. The
       expected state is the alias's own ", ST". */
    const html = (await import('node:fs')).readFileSync(join(ROOT, 'index.html'), 'utf8');
    const body = html.slice(html.indexOf('const CITY_ALIAS = {'), html.indexOf('};', html.indexOf('const CITY_ALIAS = {')));
    for (const m of body.matchAll(/(?:'([^']+)'|([a-z]+)):\s*'([^']+), ([A-Z]{2})'/g)) {
      const q = m[1] || m[2];
      cases.push({ k: null, q, at: 'Los Angeles', geo: LOCS['Los Angeles'].slice(0, 2), tz: 'America/Los_Angeles', st: m[4] });
    }
  } else if (MODE === 'kinds') {
    // Every kind-of-place word (POI_TAGS / POI_PHRASES), near you and "in denver".
    const html = (await import('node:fs')).readFileSync(join(ROOT, 'index.html'), 'utf8');
    const words = new Set();
    for (const name of ['const POI_TAGS = {', 'const POI_PHRASES = {']) {
      const body = html.slice(html.indexOf(name), html.indexOf('};', html.indexOf(name)));
      for (const m of body.matchAll(/(?:'([^']+)'|(\b[a-z]+)):\s*\[/g)) words.add(m[1] || m[2]);
    }
    words.delete('const');
    for (const w of words) {
      cases.push({ k: null, q: w, at: 'Los Angeles', geo: LOCS['Los Angeles'].slice(0, 2), tz: 'America/Los_Angeles', nearLA: true });
      cases.push({ k: null, q: `${w} in denver`, at: 'Los Angeles', geo: LOCS['Los Angeles'].slice(0, 2), tz: 'America/Los_Angeles', st: 'CO' });
    }
  } else if (MODE === 'in') {
    for (const k of IDX.brands) for (const [city, st] of Object.entries(CITIES))
      cases.push({ k, q: `${qFor(k)} in ${city}`, at: 'Los Angeles', geo: LOCS['Los Angeles'].slice(0, 2), tz: 'America/Los_Angeles', st, city });
  }

  const LIMIT = +(process.argv.find(a => a.startsWith('--limit=')) || '--limit=0').split('=')[1];
  // --chain=a,b,c: only these chains (substring match)
  const ONLYK = (process.argv.find(a => a.startsWith('--chain=')) || '').split('=')[1];
  if (ONLYK) { const ks = ONLYK.toLowerCase().split(','); cases.splice(0, cases.length, ...cases.filter(c => c.k && ks.some(x => c.k.toLowerCase().includes(x)))); }
  if (LIMIT) cases.splice(LIMIT);
  // --offline: the place lookup is down too -- towns must still be found from the data
  const block = MODE === 'near' || process.argv.includes('--offline') ? BLOCK : BLOCK_TILES;
  // Overpass (kinds) and Nominatim (places) are shared public services: one at a time.
  const nW = MODE === 'kinds' || MODE === 'places' ? 1 : WORKERS;
  const workers = [];
  for (let i = 0; i < Math.min(nW, cases.length); i++) workers.push(await makeWorker(B, ORIGIN, block));
  let next = 0, done = 0; const fails = []; const t0 = Date.now();

  async function judge(c, w) {
    await w.open(c);
    const r = await w.search(c.q);
    const why = [];
    if (c.k && !r.chains.includes(c.k)) why.push(`chain not set (got ${r.chains.join(', ') || 'none'})`);
    if (MODE === 'places' || MODE === 'kinds') {
      const lab = r.center && r.center.label || '';
      if (c.st && !(new RegExp(`\\b${c.st}\\b`).test(lab) || (c.st === 'DC' && /washington/i.test(lab))))
        why.push(`area "${lab || (r.route ? 'a route' : 'none')}", wanted ${c.st}`);
      if (c.nearLA) {
        const at = r.center ? [r.center.lat, r.center.lon] : null;
        if (!at || miles(at, c.geo) > 30) why.push(`area "${lab || 'none'}", wanted near Los Angeles`);
      }
      return { why, r };
    }
    if (MODE === 'near') {
      const from = c.geo || c.origin;
      const dmin = IDX.nearest(c.k, from);
      const first = r.first[0];
      if (!first) why.push(`no results (nearest ${c.k} is ${Math.round(dmin)} mi away)`);
      else {
        const d = miles(from, [first.lat, first.lon]);
        // nearest-first: the first stop should be (about) the nearest one; inside the
        // 25-mile area anything inside the area is fine
        if (d > Math.max(26, dmin * 1.05 + 3)) why.push(`first stop ${Math.round(d)} mi away (${first.name}, ${first.st}); nearest is ${Math.round(dmin)} mi`);
      }
    } else if (MODE === 'in') {
      const lab = r.center && r.center.label || '';
      if (!new RegExp(`\\b${c.st}\\b`).test(lab)) why.push(`area "${lab}", wanted ${c.st}`);
      if (r.center) {
        const dmin = IDX.nearest(c.k, [r.center.lat, r.center.lon]);
        if (dmin <= 24 && !r.n) why.push(`0 stops but one is ${Math.round(dmin)} mi from ${c.city}`);
        if (r.n && r.first[0] && miles([r.center.lat, r.center.lon], [r.first[0].lat, r.first[0].lon]) > 26) why.push('first stop outside the area');
      }
    }
    return { why, r };
  }
  async function run(w) {
    while (next < cases.length) {
      const c = cases[next++];
      let res;
      try { res = await judge(c, w); } catch (e) { res = { why: ['error: ' + e.message], r: null }; }
      done++;
      if (res.why.length) { fails.push({ c, why: res.why, title: res.r && res.r.title, toast: res.r && res.r.toast }); console.log(`FAIL  ${JSON.stringify(c.q)} @ ${c.at}: ${res.why.join('; ')}`); }
      if (done % 50 === 0) console.log(`  ... ${done}/${cases.length} (${fails.length} failing, ${Math.round((Date.now() - t0) / 1000)} s)`);
    }
  }
  await Promise.all(workers.map(run));
  console.log(`\nsearch matrix (${MODE}): ${cases.length - fails.length}/${cases.length} pass`);
  writeFileSync(join(tmpdir(), `cc-matrix-${MODE}.json`), JSON.stringify(fails, null, 1));
  for (const w of workers) await w.close();
  await probe.close();
  B.close(); chrome.kill(); srv.kill();
  try { rmSync(profile, { recursive: true, force: true }); } catch (e) {}
  process.exit(fails.length ? 1 : 0);
}
main().catch(e => { console.error(e); process.exit(2); });
