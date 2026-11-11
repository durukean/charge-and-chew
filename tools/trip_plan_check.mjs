#!/usr/bin/env node
/* The /trip/ pages' 8 am plan against the app's, row by row. No network.

   build.py writes each trip page's plan with planner.py, a port of the app's breakPicks() /
   breaksCard(). This opens the app in headless Chrome on the same drive the page links to
   (?from=…&to=…&c=5&leave=0800), answers its two network calls itself -- the place search with
   the trip's own end points, the route with the trip's own geometry from data/trips.json --
   pins the clock to the data's date, and compares every row of the breaks card with the page:
   clock, meal or break, mile, stop, chain, walk, the charger-gap row, and the arrival. Then it
   opens each stop link on the page and checks the app lands on that stop.

       node tools/trip_plan_check.mjs            # every trip page (~2 min)
       node tools/trip_plan_check.mjs --quick    # a fixed sample across time zones (check.sh)
       node tools/trip_plan_check.mjs denver     # trips whose slug contains this
       node tools/trip_plan_check.mjs --live [slug]   # the real place search and route (network)

   --live is how a visitor's app sees it: Nominatim's point for each city and OSRM's full road
   geometry instead of the stored one. Small differences are expected there (a stop at the edge
   of the 5-mile corridor, a clock a step of 5 minutes off); it reports them, one trip at a time.

   Exit code: the number of trips that disagree (99 on a crash). */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CHROME = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium']
  .find(p => existsSync(p));
const LIVE = process.argv.includes('--live');
const ARG = (process.argv.slice(2).find(a => a !== '--live') || '').toLowerCase();
const QUICK = ARG === '--quick';
const sleep = ms => new Promise(r => setTimeout(r, ms));
// Several time zones, a zone change mid-drive, the Texas Mountain-time corner, a charger gap,
// a drive with no stop, the longest drives.
const SAMPLE = ['los-angeles-to-las-vegas', 'denver-to-salt-lake-city', 'chicago-to-detroit', 'atlanta-to-nashville',
  'san-antonio-to-el-paso', 'new-york-to-boston', 'san-francisco-to-portland', 'miami-to-key-west',
  'dallas-to-houston', 'seattle-to-spokane', 'denver-to-kansas-city', 'washington-to-charlotte'];

const STATE = { AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California', CO: 'Colorado', CT: 'Connecticut',
  DE: 'Delaware', DC: 'District of Columbia', FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana',
  IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan',
  MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire',
  NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma',
  OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas',
  UT: 'Utah', VT: 'Vermont', VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming' };
const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const tripSlug = t => `${slug(t.a.split(',')[0])}-to-${slug(t.b.split(',')[0])}`;
const text = h => h.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&#x27;/g, "'").replace(/&nbsp;/g, ' ').trim();

// The plan as the page prints it (build.py trip_plan_html).
function pagePlan(html) {
  const t = html.match(/<table class="trip plan">[\s\S]*?<tbody>([\s\S]*?)<\/tbody>/);
  if (!t) return null;
  const rows = [], trs = t[1].match(/<tr[^>]*>[\s\S]*?<\/tr>/g) || [];
  let leave = '', arrive = '';
  for (const tr of trs) {
    const td = (tr.match(/<td>[\s\S]*?<\/td>/g) || []).map(x => x.slice(4, -5));
    if (/^<b>Leave /.test(td[1] || '')) { leave = text(td[0]); continue; }
    if (/^<b>Arrive in /.test(td[1] || '')) { arrive = text(td[0]).replace(/next day$/, ' · next day').replace(/^~/, ''); continue; }
    const clock = text((td[0].match(/^<b>([^<]*)<\/b>/) || [])[1] || '');
    if (/class="gap"/.test(tr)) {
      rows.push({ kind: 'gap', clock, len: +(td[1].match(/No fast charger for (\d+) mi/) || [])[1], from: +(td[1].match(/from mile (\d+)/) || [])[1] });
      continue;
    }
    const food = (td[3].match(/<b>([\s\S]*?)<\/b> (\d+) min/) || []);
    rows.push({ kind: 'stop', clock, label: text((td[0].match(/<i class="ml[^"]*">([^<]*)<\/i>/) || [])[1] || ''),
      mile: +(td[0].match(/mile (\d+)/) || [])[1], id: +(td[1].match(/stop=(\d+)/) || [])[1],
      k: food[1] ? text(food[1]) : '', walk: food[2] ? +food[2] : null });
  }
  return { leave, arrive, rows };
}

// The plan as the app's breaks card shows it.
const READ = `(() => {
  const card = document.querySelector('.breaks');
  if (!card) return null;
  const sel = document.getElementById('leaveSel');
  const rows = [];
  for (const b of card.children) {
    if (b.matches('.brk.gap')) {
      rows.push({ kind: 'gap', clock: b.querySelector('.bm').firstChild.textContent.trim(),
        len: +(b.querySelector('.bt b').textContent.match(/for (\\d+) mi/) || [])[1], from: +(b.querySelector('.bm small').textContent.match(/mile (\\d+)/) || [])[1] });
    } else if (b.matches('.brk[data-brk]')) {
      const line = b.querySelector('.bt span').textContent;
      const seg = line.split(' · ').find(x => / \\d+ min$/.test(x)) || '';
      rows.push({ kind: 'stop', clock: b.querySelector('.bm').firstChild.textContent.trim(), label: b.querySelector('.bm i').textContent,
        mile: +(b.querySelector('.bm small').textContent.match(/mile (\\d+)/) || [])[1], id: +b.dataset.brk,
        k: b.dataset.k || '', walk: seg ? +seg.match(/ (\\d+) min$/)[1] : null });
    }
  }
  return { leave: sel.options[sel.selectedIndex].textContent, arrive: card.querySelector('.bleave > span').textContent.replace(/^arrive ~/, ''), rows };
})()`;

async function cdpConnect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0; const pending = new Map(), listeners = [];
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
    else if (m.method) for (const l of listeners) l(m);
  };
  const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
    const i = ++id; pending.set(i, { res, rej });
    ws.send(JSON.stringify({ id: i, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  return { send, on: l => listeners.push(l), off: l => listeners.splice(listeners.indexOf(l), 1), close: () => ws.close() };
}
function startServer() {
  return new Promise((res, rej) => {
    const p = spawn('python3', ['-u', '-m', 'http.server', '0', '--bind', '127.0.0.1'], { cwd: ROOT });
    const hit = d => { const m = String(d).match(/port (\d+)/); if (m) res({ p, port: +m[1] }); };
    p.stdout.on('data', hit); p.stderr.on('data', hit);
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

async function appPlan(B, port, t, day) {
  const { targetId } = await B.send('Target.createTarget', { url: 'about:blank' });
  const { sessionId: S } = await B.send('Target.attachToTarget', { targetId, flatten: true });
  const send = (m, p) => B.send(m, p, S);
  const ends = [t.a, t.b].map(x => ({ x, city: x.split(',')[0].trim().toLowerCase() }));
  const lat = { [ends[0].city]: [t.alat, t.alon, t.a], [ends[1].city]: [t.blat, t.blon, t.b] };
  const listener = async m => {
    if (m.sessionId !== S || m.method !== 'Fetch.requestPaused') return;
    const { requestId, request } = m.params, u = new URL(request.url);
    const reply = (obj, code = 200) => send('Fetch.fulfillRequest', { requestId, responseCode: code,
      responseHeaders: [{ name: 'Content-Type', value: 'application/json' }, { name: 'Access-Control-Allow-Origin', value: '*' }],
      body: Buffer.from(JSON.stringify(obj)).toString('base64') }).catch(() => {});
    if (u.hostname === '127.0.0.1') return send('Fetch.continueRequest', { requestId }).catch(() => {});
    if (u.hostname === 'nominatim.openstreetmap.org' && u.pathname === '/search') {
      const q = (u.searchParams.get('q') || '').split(',')[0].trim().toLowerCase(), hit = lat[q];
      if (!hit) return reply([]);
      const [la, lo, name] = hit, [city, st] = name.split(',').map(s => s.trim());
      return reply([{ lat: String(la), lon: String(lo), class: 'boundary', type: 'administrative', importance: 0.8,
        display_name: `${city}, ${STATE[st]}, United States`, address: { city, state: STATE[st], country_code: 'us' } }]);
    }
    if (u.hostname === 'router.project-osrm.org')
      return reply({ code: 'Ok', routes: [{ geometry: { type: 'LineString', coordinates: t.pts.map(([a, b]) => [b, a]) },
        distance: t.mi * 1609.34, duration: t.hr * 3600 }] });
    return send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' }).catch(() => {});
  };
  B.on(listener);
  try {
    await send('Page.enable'); await send('Runtime.enable');
    if (!LIVE) await send('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
    await send('Emulation.setFocusEmulationEnabled', { enabled: true });
    /* The data's day at 19:00 UTC (daytime in every US zone, whole minutes), the clock running a
       thousand times slow: the app's "today 8:00 am" is then 8:00:00 to the millisecond, as the
       page's is, and nothing that waits on time stalls. */
    await send('Page.addScriptToEvaluateOnNewDocument', { source: `(() => {
      const RD = Date, base = RD.UTC(${day.slice(0, 4)}, ${+day.slice(5, 7) - 1}, ${+day.slice(8, 10)}, 19), t0 = RD.now();
      const now = () => base + Math.floor((RD.now() - t0) / 1000);
      class D extends RD { constructor(...a) { if (a.length) super(...a); else super(now()); } static now() { return now(); } }
      window.Date = D; })();` });
    const url = `http://127.0.0.1:${port}/?nosw=1&from=${encodeURIComponent(t.a)}&to=${encodeURIComponent(t.b)}&c=5&leave=0800`;
    await send('Page.navigate', { url });
    for (let i = 0; i < (LIVE ? 240 : 120); i++) {
      await sleep(250);
      const r = await send('Runtime.evaluate', { expression: `!!document.querySelector('.breaks') && !!document.getElementById('leaveSel')`, returnByValue: true });
      if (r.result.value) break;
    }
    await sleep(150);
    const r = await send('Runtime.evaluate', { expression: READ, returnByValue: true });
    const plan = r.result.value;
    /* Each stop on the page links to the app at that stop (&stop=): it must open that stop's
       card on the planned drive, at the plan's mile, leading with the chain the plan promised,
       and without the keyboard focus ring a script click once put on it. */
    if (plan) for (const row of plan.rows.filter(x => x.kind === 'stop')) {
      await send('Page.navigate', { url: url + '&stop=' + row.id });
      let got = null;
      for (let i = 0; i < 60 && !got; i++) {
        await sleep(150);
        got = (await send('Runtime.evaluate', { returnByValue: true, expression: `(() => {
          const p = document.querySelector('.leaflet-popup-content .pp-mile');
          if (!p || !document.querySelector('.breaks')) return null;
          const lead = document.querySelector('.leaflet-popup-content .pp-nb');
          return { mile: +(p.textContent.match(/mile (\\d+)/) || [])[1], lead: lead ? lead.textContent : '',
            ring: !!document.querySelector('.leaflet-popup :focus-visible') };
        })()` })).result.value;
      }
      row.link = got ? (got.mile === row.mile && (!row.k || got.lead.includes(row.k)) && !got.ring ? 'ok'
        : `opened at mile ${got.mile}, leading with "${got.lead}"${got.ring ? ', with a focus ring' : ''}`) : 'did not open the stop';
    }
    return plan;
  } finally {
    B.off(listener);
    await B.send('Target.closeTarget', { targetId }).catch(() => {});
  }
}

function compare(page, app) {
  if (!page) return ['no plan table on the page'];
  if (!app) return ['the app showed no breaks card'];
  const why = [];
  if (page.leave !== app.leave) why.push(`leaving: page ${page.leave}, app ${app.leave}`);
  if (page.arrive !== app.arrive) why.push(`arrive: page ${page.arrive}, app ${app.arrive}`);
  const n = Math.max(page.rows.length, app.rows.length);
  for (const a of app.rows) if (a.link && a.link !== 'ok') why.push(`the page's link to the ${a.label} stop at mile ${a.mile} ${a.link}`);
  for (let i = 0; i < n; i++) {
    const p = page.rows[i], a = app.rows[i];
    if (!p || !a) { why.push(`row ${i + 1}: page ${JSON.stringify(p)}, app ${JSON.stringify(a)}`); continue; }
    for (const f of ['kind', 'clock', 'label', 'mile', 'id', 'k', 'walk', 'len', 'from'])
      if (p[f] !== a[f]) why.push(`row ${i + 1} ${f}: page ${JSON.stringify(p[f])}, app ${JSON.stringify(a[f])}`);
  }
  return why;
}

async function main() {
  if (!CHROME) { console.log('SKIP: Chrome not found'); return 0; }
  const trips = JSON.parse(readFileSync(join(ROOT, 'data', 'trips.json'), 'utf8'));
  const day = (readFileSync(join(ROOT, 'data.js'), 'utf8').match(/"generated":"(\d{4}-\d\d-\d\d)"/) || [])[1];
  if (!day) throw new Error('no generated date in data.js');
  let todo = Object.values(trips).map(t => ({ t, sl: tripSlug(t) }))
    .filter(x => existsSync(join(ROOT, 'trip', x.sl, 'index.html')));       // build.py skips thin routes
  if (QUICK) todo = todo.filter(x => SAMPLE.includes(x.sl));
  else if (ARG) todo = todo.filter(x => x.sl.includes(ARG));
  if (!todo.length) { console.log('no trips to check'); return 1; }
  const { p: srv, port } = await startServer();
  const profile = mkdtempSync(join(tmpdir(), 'cc-tripplan-'));
  const { p: chrome, ws } = await startChrome(profile);
  const B = await cdpConnect(ws);
  let bad = 0, rows = 0;
  const queue = todo.slice();
  const worker = async () => {
    for (let x; (x = queue.shift());) {
      let why;
      try {
        const page = pagePlan(readFileSync(join(ROOT, 'trip', x.sl, 'index.html'), 'utf8'));
        const app = await appPlan(B, port, x.t, day);
        why = compare(page, app);
        rows += page ? page.rows.length : 0;
        if (!why.length) console.log(`ok    ${x.sl}: ${page.rows.map(r => r.kind === 'gap' ? `gap ${r.len} mi` : `${r.clock} ${r.label}`).join(', ') || 'no stop'}, arrive ${page.arrive}`);
      } catch (e) { why = ['error: ' + e.message]; }
      if (why.length) { bad++; console.log(`FAIL  ${x.sl}\n        ${why.slice(0, 6).join('\n        ')}`); }
    }
  };
  await Promise.all(Array.from({ length: LIVE ? 1 : 4 }, worker));
  B.close(); chrome.kill(); srv.kill();
  try { rmSync(profile, { recursive: true, force: true }); } catch (e) {}
  console.log(`\ntrip plan check: ${todo.length - bad} of ${todo.length} trips match the app (${rows} rows)`);
  return bad;
}
main().then(n => process.exit(Math.min(n, 98)), e => { console.error(e); process.exit(99); });
