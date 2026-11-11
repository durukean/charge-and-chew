#!/usr/bin/env node
/* The route corridor against brute force. No network, no browser.

   applyCorridor() (index.html) and planner.corridor() (planner.py, the /trip/ pages) find the
   stops within the corridor by sweeping 0.05-degree cells instead of measuring every stop
   against every point of the line. The sweep once used the same number of cells east-west as
   north-south, and a degree of longitude is shorter in the north: at the 25-mile corridor it
   lost 1-2 stops at the edge north of ~43.5 degrees (Seattle -> Spokane, Boston -> Bar Harbor).

   This runs the app's own applyCorridor (cut out of index.html, the map stubbed) and
   planner.corridor on stored routes, northern and southern, at 5, 10 and 25 miles, and checks
   both against brute force on the same points (every point, or every third on a line of more
   than 3,000, as the app samples): the same stops, the same nearest point, the same mile.

       node tools/corridor_check.mjs

   Exit code: the number of mismatching route/corridor pairs (99 on a crash). */
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const html = readFileSync(join(ROOT, 'index.html'), 'utf8');
const w = {}; new Function('window', readFileSync(join(ROOT, 'data.js'), 'utf8'))(w);
const SITES = w.PITSTOP_DATA.sites;
const trips = JSON.parse(readFileSync(join(ROOT, 'data', 'trips.json'), 'utf8'));

// The app's own code: hav, MI and the whole applyCorridor, run against stubs for the map.
const grab = re => { const m = html.match(re); if (!m) throw new Error('not found in index.html: ' + re); return m[0]; };
const havSrc = grab(/const hav = \(a1, o1, a2, o2\) => \{[\s\S]*?\n\};/);
const miSrc = grab(/const WALK_MPM = \d+, MI = [\d.]+;/);
const fnSrc = grab(/function applyCorridor\(verts, mi, hr, hwy\) \{[\s\S]*?\n\}\n/);
const app = new Function('SITES', `
  const L = { polyline: () => ({ addTo() { return this; } }) }, map = {};
  const track = () => {}, clearRoute = () => {}, clearLivePoi = () => {}, fitRouteWhenReady = () => {},
    showRouteSummary = () => {}, render = () => {}, setSheet = () => {}, syncUrl = () => {}, settleFit = () => {};
  let livePoiGen = 0, routeCase = null, routeLayer = null, route = null, curDark = false, corridorMi = 5;
  const routeRenderer = null;
  ${havSrc}
  ${miSrc}
  ${fnSrc}
  return (verts, mi, c) => { corridorMi = c; applyCorridor(verts, mi, 1, null); return route; };`)(SITES);
const hav = new Function(`${havSrc}; return hav;`)();
const MI = new Function(`${miSrc}; return MI;`)();

// Brute force: every stop against every sampled point; ties go to the earliest point. A point
// further north or south than the corridor cannot be within it (distance >= R * dLat), so
// skipping those is still exact.
function brute(verts, mi, c) {
  const maxM = c * MI, step = verts.length > 3000 ? 3 : 1, dLat = maxM / 6371000 * 180 / Math.PI + 1e-9;
  const order = new Map();
  for (const s of SITES) {
    let best = 9e9, bi = 0;
    for (let i = 0; i < verts.length; i += step) {
      if (Math.abs(verts[i][0] - s.lat) > dLat) continue;
      const d = hav(s.lat, s.lon, verts[i][0], verts[i][1]);
      if (d < best) { best = d; bi = i; }
    }
    if (best <= maxM) order.set(s.id, bi);
  }
  const cum = new Float64Array(verts.length);
  for (let i = 1; i < verts.length; i++) cum[i] = cum[i - 1] + hav(verts[i - 1][0], verts[i - 1][1], verts[i][0], verts[i][1]);
  const k = cum[verts.length - 1] > 0 ? mi / (cum[verts.length - 1] / MI) : 1;
  const mileAt = new Map([...order].map(([id, bi]) => [id, Math.round(cum[bi] / MI * k)]));
  return { order, mileAt };
}

// Northern routes (where the old sweep lost stops) and southern ones; one made dense enough
// (> 3,000 points) that the app measures every third point.
const ROUTES = ['Seattle, WA -> Spokane, WA', 'Boston, MA -> Bar Harbor, ME', 'Minneapolis, MN -> Chicago, IL',
  'Minneapolis, MN -> Duluth, MN', 'Detroit, MI -> Mackinaw City, MI', 'Portland, OR -> Boise, ID',
  'Los Angeles, CA -> Las Vegas, NV', 'Miami, FL -> Key West, FL', 'Houston, TX -> San Antonio, TX', 'Phoenix, AZ -> Tucson, AZ'];
const cases = ROUTES.map(k => { if (!trips[k]) throw new Error('no stored route ' + k); return [k, trips[k].pts, trips[k].mi]; });
{ // Seattle -> Spokane with seven extra points between each pair: 8x the points
  const p = trips['Seattle, WA -> Spokane, WA'].pts, d = [];
  for (let i = 0; i < p.length; i++) { d.push(p[i]); if (i + 1 < p.length) for (const f of [1, 2, 3, 4, 5, 6, 7].map(x => x / 8)) d.push([+(p[i][0] + (p[i + 1][0] - p[i][0]) * f).toFixed(5), +(p[i][1] + (p[i + 1][1] - p[i][1]) * f).toFixed(5)]); }
  if (d.length <= 3000) throw new Error('the dense route is not dense enough');
  cases.push(['Seattle, WA -> Spokane, WA (dense)', d, trips['Seattle, WA -> Spokane, WA'].mi]);
}

// planner.corridor on the same inputs, in one python run.
const dir = mkdtempSync(join(tmpdir(), 'cc-corr-'));
writeFileSync(join(dir, 'in.json'), JSON.stringify(cases.map(([, v, mi]) => [v, mi])));
const py = spawnSync('python3', ['-c', `
import json, sys
sys.path.insert(0, ${JSON.stringify(ROOT)})
import planner
from data_reader import load_data
S = load_data(${JSON.stringify(join(ROOT, 'data.js'))})["sites"]
out = []
for v, mi in json.load(open(${JSON.stringify(join(dir, 'in.json'))})):
    for c in (5, 10, 25):
        o, m = planner.corridor(v, mi, S, c)
        out.append({str(k): [o[k], m[k]] for k in o})
json.dump(out, open(${JSON.stringify(join(dir, 'out.json'))}, 'w'))
`], { encoding: 'utf8' });
if (py.status !== 0) { console.error(py.stderr); process.exit(99); }
const pyOut = JSON.parse(readFileSync(join(dir, 'out.json'), 'utf8'));
rmSync(dir, { recursive: true, force: true });

let bad = 0, n = 0;
for (const [name, verts, mi] of cases) for (const c of [5, 10, 25]) {
  const want = brute(verts, mi, c), got = app(verts, mi, c), pyr = pyOut[n++];
  const why = [];
  const diff = (label, ord, mile) => {
    const miss = [...want.order.keys()].filter(id => !ord.has(id)), extra = [...ord.keys()].filter(id => !want.order.has(id));
    const moved = [...want.order].filter(([id, bi]) => ord.has(id) && (ord.get(id) !== bi || mile.get(id) !== want.mileAt.get(id)));
    if (miss.length) why.push(`${label} misses ${miss.length} (${miss.slice(0, 4).join(', ')})`);
    if (extra.length) why.push(`${label} adds ${extra.length} (${extra.slice(0, 4).join(', ')})`);
    if (moved.length) why.push(`${label}: ${moved.length} stops at another point or mile`);
  };
  diff('app', got.order, got.mileAt);
  diff('planner.py', new Map(Object.entries(pyr).map(([k, v]) => [+k, v[0]])), new Map(Object.entries(pyr).map(([k, v]) => [+k, v[1]])));
  if (why.length) { bad++; console.log(`FAIL  ${name}, ${c} mi: ${want.order.size} by brute force; ${why.join('; ')}`); }
  else console.log(`ok    ${name}, ${c} mi: ${want.order.size} stops`);
}
console.log(`\ncorridor check: ${bad ? bad + ' of ' + n + ' differ from brute force' : 'all ' + n + ' match brute force'}`);
process.exit(Math.min(bad, 98));
