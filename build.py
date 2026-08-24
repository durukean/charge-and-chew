#!/usr/bin/env python3
"""Generate static SEO pages from data.js:
   near/index.html                      - all chains + states
   near/<chain>/index.html              - "Superchargers near IHOP"
   near/<chain>/<st>/index.html         - "Superchargers near IHOP in Texas"
   sitemap.xml, robots.txt
Run after data/fetch_pois.py.  Usage: python3 build.py [--base https://chargeandchew.com]
"""
import json, os, re, sys, html, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = "Charge & Chew"
BASE = "https://chargeandchew.com"
for i, a in enumerate(sys.argv):
    if a == "--base": BASE = sys.argv[i + 1].rstrip("/")

STATES = {"AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California","CO":"Colorado",
"CT":"Connecticut","DE":"Delaware","DC":"Washington DC","FL":"Florida","GA":"Georgia","HI":"Hawaii","ID":"Idaho",
"IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas","KY":"Kentucky","LA":"Louisiana","ME":"Maine",
"MD":"Maryland","MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi","MO":"Missouri",
"MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire","NJ":"New Jersey","NM":"New Mexico",
"NY":"New York","NC":"North Carolina","ND":"North Dakota","OH":"Ohio","OK":"Oklahoma","OR":"Oregon",
"PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota","TN":"Tennessee","TX":"Texas",
"UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington","WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming"}

raw = open(os.path.join(HERE, "data.js")).read()
D = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
sites = {s["id"]: s for s in D["sites"]}
brands, matches = D["brands"], {int(k): v for k, v in D["matches"].items()}

# match values are [dLat,dLon] integer deltas x1e4 from the charger; convert to metres
# so the rest of this generator (which expects a distance) works unchanged.
def _hav(a1, o1, a2, o2):
    import math
    R = 6371000; p = math.pi / 180
    dla = (a2 - a1) * p; dlo = (o2 - o1) * p
    x = math.sin(dla/2)**2 + math.cos(a1*p)*math.cos(a2*p)*math.sin(dlo/2)**2
    return 2 * R * math.asin(math.sqrt(x))
for _sid, _m in matches.items():
    _s = sites.get(_sid)
    if not _s: continue
    for _k, _v in list(_m.items()):
        if isinstance(_v, list):
            _plat = _s["lat"] + _v[0] / 1e4; _plon = _s["lon"] + _v[1] / 1e4
            _m[_k] = int(_hav(_s["lat"], _s["lon"], _plat, _plon))
WALK = 80

def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
def esc(s): return html.escape(str(s))
def mins(m): return max(1, round(m / WALK))
def art(name):
    """'a IHOP' reads wrong; pick a/an by how the name is actually said."""
    n = (name or "").strip()
    if not n: return "a"
    if re.match(r'^(IHOP|IKEA|IN-N-OUT|H-E-B)\b', n, re.I): return "an"
    return "an" if n[0].lower() in "aeiou" else "a"
def fmt_d(m):
    mi = m / 1609.34
    return f"{round(m*3.281)} ft" if mi < .1 else f"{mi:.1f} mi"

CSS = """
:root{
  --bg:#f4f5f7;--surface:#fff;--surface2:#f1f3f5;--surface3:#e8ebee;--line:#e7eaee;--line2:#d5dae0;
  --txt:#191c1f;--dim:#5b6470;--dim2:#667085;--accent:#2563eb;--accent-ink:#fff;
  --good:#0a7d55;--good-bg:#effaf4;--amber:#f59e0b;--warn:#b45309;--warn-bg:#fef3e2;
  --sh:0 1px 8px rgba(25,28,31,.08);--mono:'JetBrains Mono',ui-monospace,monospace;
}
@media(prefers-color-scheme:dark){:root{
  --bg:#0e1116;--surface:#171a20;--surface2:#1e222a;--surface3:#272c35;--line:#262b33;--line2:#363d48;
  --txt:#eef1f5;--dim:#a2abb7;--dim2:#8b95a3;--accent:#60a5fa;--accent-ink:#0b0e13;
  --good:#4ade80;--good-bg:rgba(74,222,128,.13);--amber:#fbbf24;--warn:#fbbf24;--warn-bg:rgba(251,191,36,.13);
  --sh:0 2px 10px rgba(0,0,0,.35);
}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);line-height:1.5;
  font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
a{color:var(--accent)}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px;border-radius:8px}
.wrap{max-width:880px;margin:0 auto;padding:20px 16px 64px}
header{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:22px}
header .logo{display:flex;align-items:center;gap:8px;font-weight:800;font-size:17px;letter-spacing:-.3px;
  color:var(--txt);text-decoration:none}
header .logo .mk{width:30px;height:30px;border-radius:9px;background:var(--accent);color:var(--accent-ink);
  display:grid;place-items:center;font-size:15px}
header .logo .c{color:var(--accent)}header .logo .h{color:var(--amber)}
header nav{margin-left:auto;display:flex;gap:14px}
header nav a{color:var(--dim);font-size:13.5px;text-decoration:none;font-weight:600}
h1{font-size:clamp(22px,3.4vw,30px);line-height:1.18;margin-bottom:10px;letter-spacing:-.7px;font-weight:800}
.lead{color:var(--dim);margin-bottom:16px;font-size:15.5px;max-width:62ch}
.lead b{color:var(--txt)}
.cta{display:inline-flex;align-items:center;gap:8px;background:var(--accent);color:var(--accent-ink);
  text-decoration:none;font-weight:700;padding:12px 18px;border-radius:12px;margin-bottom:26px;font-size:15px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px;
  margin-bottom:9px;box-shadow:var(--sh);display:flex;gap:13px;align-items:flex-start}
.card .ring{width:50px;height:50px;border-radius:50%;flex-shrink:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;background:var(--good-bg);color:var(--good)}
.card .ring b{font-size:13px;font-weight:800;font-family:var(--mono);line-height:1.1}
.card .ring span{font-size:9px;font-weight:600;opacity:.75}
.card .body{flex:1;min-width:0}
.card .n{font-weight:700;font-size:16px;display:flex;justify-content:space-between;gap:10px;
  align-items:baseline;letter-spacing:-.2px}
.card .n small{color:var(--dim);font-weight:700;font-size:11.5px;white-space:nowrap;font-family:var(--mono);
  background:var(--surface2);border-radius:7px;padding:3px 8px}
.card .a{color:var(--dim2);font-size:12.5px;margin-top:3px}
.card .host{color:var(--warn);font-size:12.5px;margin-top:2px}
.card .c{font-size:12.5px;margin-top:8px;display:flex;flex-wrap:wrap;gap:5px 7px;color:var(--dim)}
.card .c span{background:var(--surface2);border-radius:8px;padding:3px 9px}
.card .c b{color:var(--txt);font-weight:700}
.card .l{margin-top:10px;font-size:12.5px;display:flex;gap:8px;flex-wrap:wrap}
.card .l a{text-decoration:none;font-weight:700;padding:7px 12px;border-radius:9px;
  background:var(--surface2);border:1px solid var(--line);color:var(--txt)}
.card .l a.pri{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
h2{font-size:18px;margin:30px 0 10px;letter-spacing:-.3px;font-weight:800}
.chips{display:flex;flex-wrap:wrap;gap:7px}
.chips a{background:var(--surface);border:1px solid var(--line);color:var(--txt);font-size:13.5px;
  padding:8px 13px;border-radius:100px;text-decoration:none;font-weight:600;box-shadow:var(--sh)}
.chips a small{color:var(--dim2);font-weight:500}
footer{margin-top:44px;color:var(--dim2);font-size:12.5px;border-top:1px solid var(--line);padding-top:16px;
  line-height:1.6}
@media(pointer:coarse){.chips a{padding:11px 15px}.card .l a{padding:10px 14px}}
"""

def page(path, title, desc, body, canonical, jsonld="", thin=False):
    robots = '<meta name="robots" content="noindex,follow">' if thin else ''
    depth = path.count("/")
    root = "../" * depth
    out = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#f4f5f7">
<title>{esc(title)} | {BRAND}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{BASE}/{canonical}">
{robots}
<link rel="icon" href="{BASE}/favicon.svg" type="image/svg+xml">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{BRAND}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{BASE}/{canonical}">
<meta property="og:image" content="{BASE}/og.png">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0d1117">
{jsonld}
<style>{CSS}</style></head><body><div class="wrap">
<header><a class="logo" href="{root}"><span class="mk">\u26a1</span><span><span class="c">Charge</span> &amp; <span class="h">Chew</span></span></a>
<nav><a href="{root}">Map</a><a href="{root}near/">All chains</a></nav></header>
{body}
<footer>Charger data: US DOE / NREL <a href="https://afdc.energy.gov/fuels/electricity-locations">AFDC</a> · Chain locations: <a href="https://www.openstreetmap.org">OpenStreetMap</a> · Updated {D['generated']}.
Walk times are minimums from straight-line distance at ~3 mph; the real walk is usually longer. Not affiliated with Tesla, Inc. or any listed chain. "Supercharger" is a trademark of Tesla, Inc.</footer>
</div>
<script data-goatcounter="https://chargeandchew.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</body></html>"""
    full = os.path.join(HERE, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w").write(out)

def jsonld_state(key, st, sn, sites_list, canonical):
    items = []
    for i, (d, sid) in enumerate(sites_list[:25], 1):
        s = sites[sid]
        items.append({"@type": "ListItem", "position": i, "item": {
            "@type": "Place", "name": f"{s.get('net','DC fast charger')} — {s['name']}",
            "address": {"@type": "PostalAddress", "streetAddress": s["street"],
                        "addressLocality": s["city"], "addressRegion": s["st"], "addressCountry": "US"},
            "geo": {"@type": "GeoCoordinates", "latitude": s["lat"], "longitude": s["lon"]}}})
    blocks = [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Chains", "item": f"{BASE}/near/"},
            {"@type": "ListItem", "position": 2, "name": key, "item": f"{BASE}/near/{slug(key)}/"},
            {"@type": "ListItem", "position": 3, "name": sn, "item": f"{BASE}/{canonical}"}]},
        {"@context": "https://schema.org", "@type": "ItemList",
         "name": f"Fast chargers near {key} in {sn}",
         "numberOfItems": len(sites_list), "itemListElement": items}]
    return "".join(f'<script type="application/ld+json">{json.dumps(x)}</script>' for x in blocks)


def site_card(s, focus, root):
    """Mirrors the app's result card: walk-time ring, mono spec badge, chain pills."""
    m = matches.get(s["id"], {})
    chains = []
    for k, d in sorted(m.items(), key=lambda x: (x[0] != focus, x[1]))[:6]:
        label = f"{brands[k]['e']} {'<b>' + esc(k) + '</b>' if k == focus else esc(k)} ≥{mins(d)} min"
        chains.append(f"<span>{label}</span>")
    focus_d = m.get(focus)
    ring = (f'<div class="ring"><b>≥{mins(focus_d)}</b><span>min</span></div>'
            if focus_d is not None else '<div class="ring">⚡</div>')
    net = f'<div class="host">{esc(s.get("net", ""))}</div>' if s.get("net") else ""
    spec = " · ".join(x for x in [f"{s['kw']} kW" if s.get('kw') else "",
                                  f"{s['stalls']} stalls" if s.get('stalls') else ""] if x)
    extra = f'<span>+{len(m) - 6}</span>' if len(m) > 6 else ""
    return f"""<div class="card">{ring}<div class="body">
<div class="n"><span>{esc(s['name'])}</span><small>{spec}</small></div>
<div class="a">{esc(s['street'])}, {esc(s['city'])}, {s['st']}</div>{net}
<div class="c">{''.join(chains)}{extra}</div>
<div class="l"><a class="pri" href="{root}?chain={esc(focus)}&amp;state={s['st']}">Show on map</a>\
<a href="https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lon']}" target="_blank" rel="noopener">Directions</a></div>
</div></div>"""

urls = []
def add(path): urls.append(f"{BASE}/{path.replace('index.html','')}")

# ---- per chain, per chain+state ----
chain_index_links = []
state_chain = {}  # st -> {chain: count}
for key, b in brands.items():
    hits = sorted([(m[key], sid) for sid, m in matches.items() if key in m])
    if not hits: continue
    cs = slug(key)
    by_state = {}
    for d, sid in hits:
        by_state.setdefault(sites[sid]["st"], []).append((d, sid))
        state_chain.setdefault(sites[sid]["st"], {}).setdefault(key, 0)
        state_chain[sites[sid]["st"]][key] += 1
    n = len(hits)
    chain_index_links.append((n, key, cs))
    state_links = "".join(f'<a href="{st.lower()}/">{STATES.get(st, st)} <small>{len(v)}</small></a>'
                          for st, v in sorted(by_state.items(), key=lambda x: -len(x[1])))
    # national page: top 40 closest, then state links
    top = "".join(site_card(sites[sid], key, "../../") for d, sid in hits[:40])
    title = f"EV fast chargers near {key} ({n} locations)"
    desc = f"{n} EV DC fast chargers within a 10-minute walk of a {key}, across all networks (Tesla, EA, EVgo, ChargePoint and more), ranked by walking distance."
    body = f"""<h1>{b['e']} EV fast chargers near {esc(key)}</h1>
<p class="lead">We found <b>{n} DC fast chargers</b> in the US — across all networks — with {art(key)} {esc(key)} within a 10-minute walk (800 m). Closest first; the first few are practically in the same parking lot.</p>
<a class="cta" href="../../?chain={esc(key)}">Open on the map →</a>
<h2>By state</h2><div class="chips">{state_links}</div>
<h2>Closest {min(40, n)} nationwide</h2>{top}"""
    path = f"near/{cs}/index.html"; page(path, title, desc, body, f"near/{cs}/"); add(path)


# ---- per chain+state (needs complete state_chain from the loop above) ----
for key, b in brands.items():
    hits = [(m[key], sid) for sid, m in matches.items() if key in m]
    if not hits: continue
    cs = slug(key)
    by_state = {}
    for d, sid in sorted(hits): by_state.setdefault(sites[sid]["st"], []).append((d, sid))
    for st, v in by_state.items():
        sn = STATES.get(st, st)
        cards = "".join(site_card(sites[sid], key, "../../../") for d, sid in v)
        others = "".join(f'<a href="../../{slug(k)}/{st.lower()}/">{brands[k]["e"]} {esc(k)} <small>{c}</small></a>'
                         for k, c in sorted(state_chain[st].items(), key=lambda x: -x[1]) if k != key)
        title = f"EV fast chargers near {key} in {sn} ({len(v)})"
        desc = f"All {len(v)} EV DC fast chargers in {sn} with {art(key)} {key} within walking distance — network, power, walk time and directions."
        body = f"""<h1>{b['e']} EV fast chargers near {esc(key)} in {sn}</h1>
<p class="lead"><b>{len(v)} DC fast chargers</b> in {sn} have {art(key)} {esc(key)} within a 10-minute walk. Sorted closest first.</p>
<a class="cta" href="../../../?chain={esc(key)}&amp;state={st}">Open on the map →</a>
{cards}
<h2>Other chains near fast chargers in {sn}</h2><div class="chips">{others or '—'}</div>
<h2>{esc(key)} in other states</h2><div class="chips"><a href="../">All states</a></div>"""
        can = f"near/{cs}/{st.lower()}/"
        path = f"near/{cs}/{st.lower()}/index.html"
        thin = len(v) < 3          # near-duplicate stubs hurt indexing; keep linked, drop from index
        page(path, title, desc, body, can, jsonld_state(key, st, sn, v, can), thin=thin)
        if not thin: add(path)

# ---- near/index.html ----
chain_index_links.sort(reverse=True)
chains_html = "".join(f'<a href="{cs}/">{brands[k]["e"]} {esc(k)} <small>{n}</small></a>' for n, k, cs in chain_index_links)
states_html = "".join(
    f'<h2>{STATES.get(st, st)}</h2><div class="chips">' +
    "".join(f'<a href="{slug(k)}/{st.lower()}/">{brands[k]["e"]} {esc(k)} <small>{c}</small></a>'
            for k, c in sorted(cm.items(), key=lambda x: -x[1])) + "</div>"
    for st, cm in sorted(state_chain.items(), key=lambda x: STATES.get(x[0], x[0])))
body = f"""<h1>EV fast chargers near restaurants &amp; stores</h1>
<p class="lead">{len(matches)} of {len(sites)} US DC fast chargers — every major network — have at least one of these {len(chain_index_links)} chains within a 10-minute walk. Pick a chain, or jump to a state.</p>
<a class="cta" href="../">Open the interactive map →</a>
<h2>By chain</h2><div class="chips">{chains_html}</div>
{states_html}"""
page("near/index.html", "EV fast chargers near every chain, by state", "Browse US EV DC fast chargers by the restaurant or store next to them — IHOP, Walmart, Chick-fil-A, Buc-ee's and more, state by state.", body, "near/")
add("near/index.html")

# ---- sitemap / robots ----
sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
sm += f"<url><loc>{BASE}/</loc></url>\n" + "".join(f"<url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n"
open(os.path.join(HERE, "sitemap.xml"), "w").write(sm)
open(os.path.join(HERE, "robots.txt"), "w").write(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
print(f"Generated {len(urls)} pages + sitemap.xml + robots.txt (base {BASE})")
