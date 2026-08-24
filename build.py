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
def fmt_d(m):
    mi = m / 1609.34
    return f"{round(m*3.281)} ft" if mi < .1 else f"{mi:.1f} mi"

CSS = """
:root{--bg:#0d1117;--panel:#161b22;--line:#2b333d;--txt:#e6edf3;--dim:#8b949e;--red:#e82127;--amber:#d29922;--blue:#58a6ff}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;line-height:1.5}
.wrap{max-width:860px;margin:0 auto;padding:18px 16px 60px}
header{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:18px}
header .logo{font-weight:800;letter-spacing:1px;font-size:18px;color:var(--txt);text-decoration:none}
header .logo span{color:var(--red)}
header nav a{color:var(--dim);font-size:13px;text-decoration:none;margin-left:12px}
h1{font-size:24px;line-height:1.25;margin-bottom:8px}
.lead{color:var(--dim);margin-bottom:14px;font-size:15px}
.cta{display:inline-block;background:var(--red);color:#fff;text-decoration:none;font-weight:700;padding:10px 16px;border-radius:8px;margin-bottom:22px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:8px}
.card .n{font-weight:600;font-size:15px;display:flex;justify-content:space-between;gap:8px}
.card .n small{color:var(--dim);font-weight:400;font-size:12px;white-space:nowrap}
.card .a{color:var(--dim);font-size:12px}
.card .host{color:var(--amber);font-size:12px}
.card .c{font-size:13px;margin-top:4px}
.card .c b{font-weight:600}
.card .c span{color:var(--dim)}
.card .l{margin-top:6px;font-size:12px}
.card .l a{color:var(--blue);text-decoration:none;margin-right:12px}
h2{font-size:17px;margin:26px 0 8px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chips a{background:var(--panel);border:1px solid var(--line);color:var(--txt);font-size:13px;padding:5px 10px;border-radius:16px;text-decoration:none}
.chips a small{color:var(--dim)}
footer{margin-top:40px;color:var(--dim);font-size:12px;border-top:1px solid var(--line);padding-top:12px}
footer a{color:var(--blue)}
"""

def page(path, title, desc, body, canonical, jsonld=""):
    depth = path.count("/")
    root = "../" * depth
    out = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} | {BRAND}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{BASE}/{canonical}">
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
<header><a class="logo" href="{root}">CHARGE <span>&amp;</span> CHEW</a>
<nav><a href="{root}">Map</a><a href="{root}near/">All chains</a></nav></header>
{body}
<footer>Charger data: US DOE / NREL <a href="https://afdc.energy.gov/fuels/electricity-locations">AFDC</a> · Chain locations: <a href="https://www.openstreetmap.org">OpenStreetMap</a> · Updated {D['generated']}.
Walk times are straight-line estimates at ~3 mph; verify before relying on them. Not affiliated with Tesla, Inc. or any listed chain. "Supercharger" is a trademark of Tesla, Inc.</footer>
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
    m = matches.get(s["id"], {})
    chains = []
    for k, d in m.items():
        t = f"{brands[k]['e']} {esc(k)} <span>{mins(d)} min · {fmt_d(d)}</span>"
        chains.append(f"<b>{t}</b>" if k == focus else t)
    net = f'<div class="host">{esc(s.get("net",""))}</div>' if s.get("net") else ""
    spec = " · ".join(x for x in [f"{s['kw']} kW" if s.get('kw') else "", f"{s['stalls']} stalls" if s.get('stalls') else ""] if x)
    return f"""<div class="card"><div class="n"><span>{esc(s['name'])}</span><small>{spec}</small></div>
<div class="a">{esc(s['street'])}, {esc(s['city'])}, {s['st']}</div>{net}
<div class="c">{' · '.join(chains[:6])}</div>
<div class="l"><a href="https://www.google.com/maps/search/?api=1&query={s['lat']},{s['lon']}" target="_blank" rel="noopener">Google Maps</a>
<a href="{root}?chain={esc(focus)}&amp;state={s['st']}">Show on map</a></div></div>"""

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
<p class="lead">We found <b>{n} DC fast chargers</b> in the US — across all networks — with a {esc(key)} within a 10-minute walk (800 m). Closest first; the first few are practically in the same parking lot.</p>
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
        desc = f"All {len(v)} EV DC fast chargers in {sn} with a {key} within walking distance — network, power, walk time and directions."
        body = f"""<h1>{b['e']} EV fast chargers near {esc(key)} in {sn}</h1>
<p class="lead"><b>{len(v)} DC fast chargers</b> in {sn} have a {esc(key)} within a 10-minute walk. Sorted closest first.</p>
<a class="cta" href="../../../?chain={esc(key)}&amp;state={st}">Open on the map →</a>
{cards}
<h2>Other chains near fast chargers in {sn}</h2><div class="chips">{others or '—'}</div>
<h2>{esc(key)} in other states</h2><div class="chips"><a href="../">All states</a></div>"""
        can = f"near/{cs}/{st.lower()}/"
        path = f"near/{cs}/{st.lower()}/index.html"
        page(path, title, desc, body, can, jsonld_state(key, st, sn, v, can)); add(path)

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
