#!/usr/bin/env node
/* Meal-timed breaks, checked in the real app: plans real drives (OSRM, so it needs the
   internet) in headless Chrome, picks a leaving time on the card, and checks which meals the
   card suggests, when, and where.

       node tools/breaks_check.mjs              # every case, ~2 minutes
       node tools/breaks_check.mjs denver       # only drives whose route contains this

   Not part of check.sh (routing is a network call); run it before and after touching
   breakPicks / breaksCard. Exit code is the number of failing cases. */
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CHROME = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium']
  .find(p => existsSync(p));
const ONLY = (process.argv[2] || '').toLowerCase();
const sleep = ms => new Promise(r => setTimeout(r, ms));

// Same lists as index.html: no breakfast at these, and these are not a meal at all.
const NO_BREAKFAST = ['Popeyes', 'In-N-Out', 'Chipotle', 'Five Guys', 'Shake Shack', "Raising Cane's", 'Wingstop',
  'Olive Garden', 'Texas Roadhouse', "Chili's", "Applebee's", 'Buffalo Wild Wings', 'Red Robin', 'Panda Express',
  'KFC', "Arby's", "Culver's", 'Dairy Queen', "Zaxby's", "Portillo's", 'Cook Out', 'Little Caesars', "Domino's",
  'Pizza Hut', "Jersey Mike's", 'Firehouse Subs', 'Ice cream shop'];
const NOT_A_MEAL = ['Starbucks', "Dunkin'", 'Dutch Bros', "Peet's Coffee", 'Caribou Coffee', 'Krispy Kreme', 'Ice cream shop'];

// "1:05 pm" -> minutes after midnight
const mins = t => { const m = t.match(/(\d+):(\d+) (am|pm)/); return m ? (+m[1] % 12) * 60 + +m[2] + (m[3] === 'pm' ? 720 : 0) : NaN; };
const meals = r => r.stops.filter(s => s.label !== 'Break').map(s => s.label.replace(', next day', ''));

/* from, to, leave (minutes after midnight where the drive starts, '' = now), time zone, checks.
   Each check returns '' when fine, or what is wrong. */
const CASES = [
  ['Los Angeles, CA', 'Las Vegas, NV', 420, 'America/Los_Angeles', [
    r => meals(r).join() === 'Breakfast' ? '' : `meals ${meals(r)} (want Breakfast only: arrive before lunch)`]],
  ['Los Angeles, CA', 'Las Vegas, NV', 600, 'America/Los_Angeles', [
    r => meals(r).join() === 'Lunch' ? '' : `meals ${meals(r)} (want Lunch only: left after breakfast)`]],
  ['Los Angeles, CA', 'Denver, CO', 420, 'America/Los_Angeles', [
    r => meals(r).join() === 'Breakfast,Lunch,Dinner' ? '' : `meals ${meals(r)}`,
    // Lunch is in Nevada or Utah, at roughly 12:30 LOCAL time
    r => { const l = r.stops.find(s => s.label === 'Lunch'); return l && /, (NV|UT|AZ)$/.test(l.place) && Math.abs(mins(l.clock) - 750) <= 75 ? '' : `lunch ${l && l.place} ${l && l.clock}`; },
    r => { const d = r.stops.find(s => s.label === 'Dinner'); return d && /, (UT|CO)$/.test(d.place) ? '' : `dinner ${d && d.place}`; }]],
  // The Texas line jumps an hour at lunchtime: a LATE lunch is fine, an early one is not.
  ['Albuquerque, NM', 'Dallas, TX', 480, 'America/Denver', [
    r => { const l = r.stops.find(s => s.label === 'Lunch'); return l && mins(l.clock) >= 12 * 60 + 30 - 45 ? '' : `lunch ${l && l.clock}`; }]],
  ['Los Angeles, CA', 'Las Vegas, NV', 720, 'America/Los_Angeles', [
    r => meals(r).join() === '' ? '' : `meals ${meals(r)} (leaving at noon: lunch was had, dinner is in Vegas)`]],
  // Ohio is on Eastern time: lunch near 12:30 THERE, though the drive started on Central time.
  ['Chicago, IL', 'New York, NY', 420, 'America/Chicago', [
    r => meals(r).join() === 'Breakfast,Lunch,Dinner' ? '' : `meals ${meals(r)}`,
    r => { const l = r.stops.find(s => s.label === 'Lunch'); return l && Math.abs(mins(l.clock) - 750) <= 45 ? '' : `lunch at ${l && l.clock}`; }]],
  // Planned from a phone in California: "leaving 7 am" is 7 am in Chicago, so breakfast stays.
  ['Chicago, IL', 'New York, NY', 420, 'America/Los_Angeles', [
    r => meals(r).join() === 'Breakfast,Lunch,Dinner' ? '' : `meals ${meals(r)} (7 am must be Chicago time)`]],
  ['Los Angeles, CA', 'San Diego, CA', '', 'America/Los_Angeles', [
    r => r.title ? '' : 'no card on a short drive']],
  // A short drive with no meal still shows the card: picking a time is how it gets lunch.
  ['Seattle, WA', 'Portland, OR', '', 'America/Los_Angeles', [
    r => r.title ? '' : 'no breaks card']],
  ['Seattle, WA', 'Portland, OR', 600, 'America/Los_Angeles', [
    r => meals(r).join() === 'Lunch' ? '' : `meals ${meals(r)}`]],
];
// Every case: stops in time order (within a zone this is plain order), a meal at a meal place.
const ALWAYS = [
  r => r.stops.every(s => s.label !== 'Breakfast' || !NO_BREAKFAST.includes(s.chain)) ? '' : 'breakfast at a place with no breakfast',
  r => r.stops.every(s => !/^(Lunch|Dinner)/.test(s.label) || !NOT_A_MEAL.includes(s.chain)) ? '' : 'lunch or dinner at a coffee/ice cream place',
  r => r.stops.every((s, i) => !i || s.mile > r.stops[i - 1].mile) ? '' : 'stops out of order',
];

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

const READ = `(() => {
  const card = document.querySelector('.breaks');
  if (!card) return null;
  return { title: card.querySelector('.bh').firstChild.textContent.trim(),
    stops: [...card.querySelectorAll('.brk')].map(b => {
      const line = b.querySelector('.bt span').textContent;
      // "350 kW · 🍔 Wendy's 4 min · mile 74": the part ending in "min", without its emoji
      const seg = line.split(' · ').find(x => / \\d+ min$/.test(x)) || '';
      const chain = seg.replace(/^\\S+ /, '').replace(/ \\d+ min$/, '');
      return { clock: b.querySelector('.bm').firstChild.textContent.trim(), label: b.querySelector('.bm i').textContent,
        place: b.querySelector('.bt b').textContent, chain, mile: +(line.match(/mile (\\d+)/) || [])[1] };
    }) };
})()`;

async function main() {
  if (!CHROME) { console.log('SKIP: Chrome not found'); return 0; }
  const { p: srv, port } = await startServer();
  const profile = mkdtempSync(join(tmpdir(), 'cc-breaks-'));
  const { p: chrome, ws } = await startChrome(profile);
  const B = await cdpConnect(ws);
  let fails = 0;
  for (const [from, to, leave, tz, checks] of CASES) {
    if (ONLY && !(from + ' ' + to).toLowerCase().includes(ONLY)) continue;
    const tag = `${from} -> ${to}, leaving ${leave === '' ? 'now' : Math.floor(leave / 60) + ':' + String(leave % 60).padStart(2, '0')}`;
    const { targetId } = await B.send('Target.createTarget', { url: 'about:blank' });
    const { sessionId: S } = await B.send('Target.attachToTarget', { targetId, flatten: true });
    const send = (m, p) => B.send(m, p, S);
    const ev = async expr => {
      const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    };
    let why = [], res = null;
    try {
      await send('Page.enable'); await send('Runtime.enable');
      await send('Emulation.setTimezoneOverride', { timezoneId: tz });
      await send('Emulation.setFocusEmulationEnabled', { enabled: true });
      await send('Page.navigate', { url: `http://127.0.0.1:${port}/?nosw=1&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}` });
      for (let i = 0; i < 120; i++) { await sleep(500); if (await ev(`!!document.getElementById('leaveSel')`)) break; }
      await ev(`(() => { const s = document.getElementById('leaveSel'); if (!s) return; s.value = ${JSON.stringify(String(leave))}; s.dispatchEvent(new Event('change')); })()`);
      await sleep(400);
      res = await ev(READ);
      if (!res) why.push('no breaks card (route did not load?)');
      else for (const c of [...checks, ...ALWAYS]) { const w = c(res); if (w) why.push(w); }
    } catch (e) { why.push('error: ' + e.message); }
    await B.send('Target.closeTarget', { targetId });
    if (why.length) { fails++; console.log(`FAIL  ${tag}\n        ${why.join('; ')}`); }
    else console.log(`ok    ${tag}`);
    if (res) console.log('        ' + res.stops.map(s => `${s.clock} ${s.label} ${s.place} (${s.chain})`).join(' | '));
  }
  B.close(); chrome.kill(); srv.kill();
  try { rmSync(profile, { recursive: true, force: true }); } catch (e) {}
  console.log(`\nbreaks check: ${fails ? fails + ' failing' : 'all pass'}`);
  return fails;
}
main().then(n => process.exit(n), e => { console.error(e); process.exit(99); });
