#!/usr/bin/env python3
"""Generate static SEO pages from data.js:
   near/index.html                      - all chains + states
   near/<chain>/index.html              - "Superchargers near IHOP"
   near/<chain>/<st>/index.html         - "Superchargers near IHOP in Texas"
   sitemap.xml, robots.txt
Run after data/fetch_pois.py.  Usage: python3 build.py [--base https://chargeandchew.com]
"""
import json, os, re, sys, html, shutil
from collections import Counter

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
  --txt:#191c1f;--dim:#5b6470;--dim2:#5f6879;--accent:#15803d;--accent-ink:#fff;
  --good:#0a7d55;--good-bg:#effaf4;--amber:#f59e0b;--warn:#b45309;--warn-bg:#fef3e2;
  --sh:0 1px 8px rgba(25,28,31,.08);--mono:'JetBrains Mono',ui-monospace,monospace;
}
@media(prefers-color-scheme:dark){:root{
  --bg:#0e1116;--surface:#171a20;--surface2:#1e222a;--surface3:#272c35;--line:#262b33;--line2:#363d48;
  --txt:#eef1f5;--dim:#a2abb7;--dim2:#8b95a3;--accent:#4ade80;--accent-ink:#0b0e13;
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
header .logo .mk{width:32px;height:32px;display:grid;place-items:center;flex-shrink:0}
header .logo .mk svg{width:32px;height:32px}
header .logo .c{color:#16a34a}header .logo .h{color:var(--amber)}
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
.more{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:13px 15px;
  margin:4px 0 8px;font-size:14px;color:var(--dim);box-shadow:var(--sh)}
.more a{font-weight:700}
.stats{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px 16px;
  margin-bottom:22px;font-size:14.5px;line-height:1.6;color:var(--dim);box-shadow:var(--sh)}
.stats b{color:var(--txt)}
.faq{display:flex;flex-direction:column;gap:8px}
.faq details{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:2px 14px;
  box-shadow:var(--sh)}
.faq summary{cursor:pointer;font-weight:700;font-size:14.5px;padding:12px 0;list-style:none}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";float:right;color:var(--accent);font-weight:800}
.faq details[open] summary::after{content:"–"}
.faq p{padding:0 0 13px;color:var(--dim);font-size:14px;line-height:1.6}
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
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#f4f5f7">
<title>{esc(title)} | {BRAND}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{BASE}/{canonical}">
{robots}
<link rel="icon" href="{BASE}/favicon.ico" sizes="32x32">
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
<link rel="stylesheet" href="{root}assets/pages.css"></head><body><div class="wrap">
<header><a class="logo" href="{root}"><span class="mk"><svg viewBox="0 0 64 64" aria-hidden="true"><defs><linearGradient id="ccg" x1="0" y1="0" x2="1" y2="0.35"><stop offset="0%" stop-color="#16a34a"/><stop offset="100%" stop-color="#f59e0b"/></linearGradient><mask id="ccmask"><rect width="64" height="64" fill="#000"/><circle cx="32" cy="32" r="27" fill="#fff"/><path d="M31.5 9 L17 35.5 h9.5 l-2.5 19 L42 27 H31 z" fill="#000"/><circle cx="57" cy="18" r="12.5" fill="#000"/><circle cx="47.5" cy="14.5" r="3.6" fill="#000"/><circle cx="57.5" cy="30.5" r="3.6" fill="#000"/></mask></defs><g mask="url(#ccmask)"><rect width="64" height="64" fill="url(#ccg)"/></g></svg></span><span><span class="c">Charge</span> &amp; <span class="h">Chew</span></span></a>
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


def page_stats(key, rows):
    """Real numbers pulled from the actual result set, so no two pages read alike.
    Templated stubs are exactly why Google logged these as 'crawled, not indexed'."""
    if not rows:
        return {}
    kws = [sites[sid]["kw"] for _, sid in rows if sites[sid].get("kw")]
    stalls = [sites[sid]["stalls"] for _, sid in rows if sites[sid].get("stalls")]
    nets = Counter(sites[sid].get("net", "") for _, sid in rows if sites[sid].get("net"))
    walk1 = sum(1 for d, _ in rows if mins(d) <= 2)
    h24 = sum(1 for _, sid in rows if sites[sid].get("h24"))
    fastest = max(rows, key=lambda r: sites[r[1]].get("kw") or 0)
    closest = min(rows, key=lambda r: r[0])
    return {
        "n": len(rows),
        "median_kw": sorted(kws)[len(kws) // 2] if kws else None,
        "max_kw": max(kws) if kws else None,
        "big": sum(1 for k in kws if k >= 150),
        "median_stalls": sorted(stalls)[len(stalls) // 2] if stalls else None,
        "top_nets": nets.most_common(3),
        "walk1": walk1, "h24": h24,
        "fastest": sites[fastest[1]], "fastest_kw": sites[fastest[1]].get("kw"),
        "closest": sites[closest[1]], "closest_min": mins(closest[0]),
    }


def stats_para(key, st_name, sx):
    """A short, factual paragraph unique to this page."""
    if not sx:
        return ""
    where = f"in {st_name}" if st_name else "across the US"
    bits = []
    if sx["median_kw"]:
        bits.append(f"The typical stop here delivers <b>{sx['median_kw']} kW</b>"
                    + (f", and {sx['big']} of them do 150 kW or more" if sx["big"] else ""))
    if sx["walk1"]:
        bits.append(f"<b>{sx['walk1']}</b> are close enough that the {esc(key)} is a two-minute walk or less")
    if sx["h24"]:
        bits.append(f"<b>{sx['h24']}</b> are listed as open 24 hours")
    lead = f"Of the {sx['n']} fast chargers with {art(key)} {esc(key)} nearby {where}: " + "; ".join(bits) + "."
    fast = sx["fastest"]
    extra = (f" The fastest is <b>{esc(fast['name'])}</b> in {esc(fast['city'])} at "
             f"{sx['fastest_kw']} kW; the closest walk is {sx['closest_min']} min at "
             f"<b>{esc(sx['closest']['name'])}</b>.") if sx.get("fastest_kw") else ""
    nets = ", ".join(f"{n} ({c})" for n, c in sx["top_nets"] if n)
    netline = f" Most are on {nets}." if nets else ""
    return f'<p class="stats">{lead}{extra}{netline}</p>'


def faq_block(key, st_name, sx):
    """Visible FAQ + FAQPage schema — real questions, answered from this page's data."""
    if not sx:
        return "", None
    where = f"in {st_name}" if st_name else "in the US"
    qa = [
        (f"How many EV chargers have {art(key)} {esc(key)} within walking distance {where}?",
         f"{sx['n']} public DC fast chargers {where} have {art(key)} {esc(key)} within a 10-minute "
         f"walk (800 m), based on US Department of Energy charger data matched against OpenStreetMap "
         f"locations."),
        (f"Which {esc(key)} charging stop is fastest {where}?",
         f"{esc(sx['fastest']['name'])} in {esc(sx['fastest']['city'])} at {sx['fastest_kw']} kW."
         if sx.get("fastest_kw") else "Power ratings are not published for these stops."),
        (f"Can I charge a non-Tesla EV at these stops?",
         "Most are CCS or have CCS alongside NACS. Set your car in the map view and it will show "
         "connector compatibility and an estimated charge time for each stop. Tesla Supercharger "
         "sites additionally have to be open to your brand."),
        ("How accurate are the walk times?",
         "They are minimums: straight-line distance at about 3 mph. The real walk is usually longer "
         "because you have to follow paths and crossings."),
    ]
    html = '<h2>Common questions</h2><div class="faq">' + "".join(
        f"<details><summary>{q}</summary><p>{a}</p></details>" for q, a in qa) + "</div>"
    schema = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q,
         "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"<[^>]+>", "", a)}} for q, a in qa]}
    return html, schema


def jsonld_chain(key, sites_list, canonical, faq_schema=None):
    """The national chain pages carried no structured data at all — only the state pages did."""
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
            {"@type": "ListItem", "position": 2, "name": key, "item": f"{BASE}/{canonical}"}]},
        {"@context": "https://schema.org", "@type": "ItemList",
         "name": f"EV fast chargers near {key}",
         "numberOfItems": len(sites_list), "itemListElement": items}]
    if faq_schema:
        blocks.append(faq_schema)
    return "".join(f'<script type="application/ld+json">{json.dumps(x)}</script>' for x in blocks)


def jsonld_state(key, st, sn, sites_list, canonical, faq_schema=None):
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
    if faq_schema:
        blocks.append(faq_schema)
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

# Indexing threshold, corrected 2026-08-25 by actual traffic rather than general advice.
#
# The earlier value (150) came from SEO guidance about thin templated pages dragging down a
# whole URL pattern. This site's own analytics contradicted it: of the eight pages Google was
# sending traffic to, SIX were ones we had just told it to drop — /near/kfc/fl, burger-king/sc,
# chick-fil-a/va, waffle-house/sc, costco/nj, firehouse-subs/ga. They rank because Google
# indexed them before the noindex landed, and they would have vanished at the next crawl.
#
# Those are precisely the long-tail queries this site should win, and they are not thin: each
# carries a unique data-derived stats paragraph, a FAQ, and 14-80 real results. So the cutoff
# now excludes only genuine stubs. The smallest page that was demonstrably earning traffic had
# 14 results; 8 leaves margin below that.
STATE_INDEX_MIN = 8

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
    sx = page_stats(key, hits)
    stats_html = stats_para(key, "", sx)
    faq_html, faq_schema = faq_block(key, "", sx)
    top = "".join(site_card(sites[sid], key, "../../") for d, sid in hits[:40])
    title = f"EV fast chargers near {key} ({n} locations)"
    desc = f"{n} EV DC fast chargers within a 10-minute walk of {art(key)} {key}, across all networks (Tesla, EA, EVgo, ChargePoint and more), ranked by walking distance."
    body = f"""<h1>{b['e']} EV fast chargers near {esc(key)}</h1>
<p class="lead">We found <b>{n} DC fast chargers</b> in the US — across all networks — with {art(key)} {esc(key)} within a 10-minute walk (800 m). Closest first; the first few are practically in the same parking lot.</p>
<a class="cta" href="../../?chain={esc(key)}">Open on the map →</a>
{stats_html}
<h2>By state</h2><div class="chips">{state_links}</div>
<h2>Closest {min(40, n)} nationwide</h2>{top}
{faq_html}"""
    can = f"near/{cs}/"
    path = f"near/{cs}/index.html"
    page(path, title, desc, body, can, jsonld_chain(key, hits, can, faq_schema)); add(path)


# ---- per chain+state (needs complete state_chain from the loop above) ----
for key, b in brands.items():
    hits = [(m[key], sid) for sid, m in matches.items() if key in m]
    if not hits: continue
    cs = slug(key)
    by_state = {}
    for d, sid in sorted(hits): by_state.setdefault(sites[sid]["st"], []).append((d, sid))
    for st, v in by_state.items():
        sn = STATES.get(st, st)
        sx = page_stats(key, v)
        stats_html = stats_para(key, sn, sx)
        faq_html, faq_schema = faq_block(key, sn, sx)
        # Cap the listing. near/starbucks/ca/ was 958 KB and 1,332 cards — nobody scrolls
        # that, it loads slowly, and a giant undifferentiated list reads as low quality.
        STATE_CARD_CAP = 60
        shown = v[:STATE_CARD_CAP]
        cards = "".join(site_card(sites[sid], key, "../../../") for d, sid in shown)
        if len(v) > STATE_CARD_CAP:
            cards += (f'<p class="more">Showing the {STATE_CARD_CAP} closest of {len(v)}. '
                      f'<a href="../../../?chain={esc(key)}&amp;state={st}">Open the map to see them all →</a></p>')
        others = "".join(f'<a href="../../{slug(k)}/{st.lower()}/">{brands[k]["e"]} {esc(k)} <small>{c}</small></a>'
                         for k, c in sorted(state_chain[st].items(), key=lambda x: -x[1]) if k != key)
        title = f"EV fast chargers near {key} in {sn} ({len(v)})"
        desc = f"All {len(v)} EV DC fast chargers in {sn} with {art(key)} {key} within walking distance — network, power, walk time and directions."
        body = f"""<h1>{b['e']} EV fast chargers near {esc(key)} in {sn}</h1>
<p class="lead"><b>{len(v)} DC fast chargers</b> in {sn} have {art(key)} {esc(key)} within a 10-minute walk. Sorted closest first.</p>
<a class="cta" href="../../../?chain={esc(key)}&amp;state={st}">Open on the map →</a>
{stats_html}
{cards}
<h2>Other chains near fast chargers in {sn}</h2><div class="chips">{others or '—'}</div>
<h2>{esc(key)} in other states</h2><div class="chips"><a href="../">All states</a></div>
{faq_html}"""
        can = f"near/{cs}/{st.lower()}/"
        path = f"near/{cs}/{st.lower()}/index.html"
        thin = len(v) < STATE_INDEX_MIN   # keep crawlable, but out of the index for now
        page(path, title, desc, body, can, jsonld_state(key, st, sn, v, can, faq_schema), thin=thin)
        if not thin: add(path)

# ---- near/index.html ----
chain_index_links.sort(reverse=True)
chains_html = "".join(f'<a href="{cs}/">{brands[k]["e"]} {esc(k)} <small>{n}</small></a>' for n, k, cs in chain_index_links)
# Only the strongest few chains per state. Listing all 2,952 combinations turned this into
# a link farm: it dilutes link equity and reads as low quality. The rest stay reachable from
# each chain's own page.
HUB_PER_STATE = 8
states_html = "".join(
    f'<h2>{STATES.get(st, st)}</h2><div class="chips">' +
    "".join(f'<a href="{slug(k)}/{st.lower()}/">{brands[k]["e"]} {esc(k)} <small>{c}</small></a>'
            for k, c in sorted(cm.items(), key=lambda x: -x[1])[:HUB_PER_STATE]) +
    (f'<a href="../?state={st}"><b>all {len(cm)} in {st} →</b></a>' if len(cm) > HUB_PER_STATE else "")
    + "</div>"
    for st, cm in sorted(state_chain.items(), key=lambda x: STATES.get(x[0], x[0])))
body = f"""<h1>EV fast chargers near restaurants &amp; stores</h1>
<p class="lead">{len(matches)} of {len(sites)} US DC fast chargers — every major network — have at least one of these {len(chain_index_links)} chains within a 10-minute walk. Pick a chain, or jump to a state.</p>
<a class="cta" href="../">Open the interactive map →</a>
<p><a class="cta" href="../along/">Browse by interstate instead →</a></p>
<h2>By chain</h2><div class="chips">{chains_html}</div>
{states_html}"""
page("near/index.html", "EV fast chargers near every chain, by state", "Browse US EV DC fast chargers by the restaurant or store next to them — IHOP, Walmart, Chick-fil-A, Buc-ee's and more, state by state.", body, "near/")
add("near/index.html")

# ---- interstate corridor pages: "chargers with food along I-95" ----
# Real search intent that nothing serves well. Only ~30 pages, each genuinely unique, so
# these are indexed even while the chain x state set is throttled back.
HW_PATH = os.path.join(HERE, "data", "highways.json")
CORRIDOR_MI = 3.0
INTERSTATE_MIN_KW = 50

def _hav_m(a1, o1, a2, o2):
    import math
    R = 6371000; p = math.pi / 180
    x = (math.sin((a2-a1)*p/2)**2
         + math.cos(a1*p)*math.cos(a2*p)*math.sin((o2-o1)*p/2)**2)
    return 2 * R * math.asin(math.sqrt(x))

if os.path.exists(HW_PATH):
    highways = json.load(open(HW_PATH))
    hw_links = []
    for ref, pts in sorted(highways.items(), key=lambda x: int(x[0].split()[1])):
        if len(pts) < 50:
            continue
        # grid-index the corridor so this stays fast
        cell = 0.05
        grid = {}
        for i, (la, lo) in enumerate(pts):
            grid.setdefault((round(la / cell), round(lo / cell)), []).append(i)
        maxm = CORRIDOR_MI * 1609.34
        reach = int(maxm / 111000 / cell) + 1
        found = []
        for sid, s_ in sites.items():
            if (s_.get("kw") or 0) < INTERSTATE_MIN_KW:
                continue
            best = None; bi = 0
            ci, cj = round(s_["lat"] / cell), round(s_["lon"] / cell)
            cand = []
            for di in range(-reach, reach + 1):
                for dj in range(-reach, reach + 1):
                    cand.extend(grid.get((ci + di, cj + dj), ()))
            for i in cand:
                d = _hav_m(s_["lat"], s_["lon"], pts[i][0], pts[i][1])
                if best is None or d < best:
                    best = d; bi = i
            if best is not None and best <= maxm:
                found.append((bi, sid, best))
        if len(found) < 12:
            continue
        found.sort()
        slug_ref = ref.lower().replace(" ", "-")
        disp = ref.replace(" ", "-")   # "I 95" -> "I-95", which is how people search
        states = []
        for _, sid, _d in found:
            st_ = sites[sid]["st"]
            if st_ and st_ not in states:
                states.append(st_)
        withchain = [f for f in found if matches.get(f[1])]
        cards = []
        for bi, sid, dist in withchain[:60]:
            s_ = sites[sid]
            m = matches.get(sid, {})
            k0 = min(m, key=lambda k: m[k]) if m else None
            focus = k0 if k0 else ""
            cards.append(site_card(s_, focus, "../../"))
        kws = [sites[f[1]]["kw"] for f in found if sites[f[1]].get("kw")]
        med = sorted(kws)[len(kws)//2] if kws else 0
        big = sum(1 for k in kws if k >= 150)
        h24 = sum(1 for f in found if sites[f[1]].get("h24"))
        title = f"EV fast chargers along {disp} — with food and stores nearby"
        desc = (f"{len(found)} public DC fast chargers within {CORRIDOR_MI:g} miles of {disp}, "
                f"{len(withchain)} of them within a 10-minute walk of a restaurant or store. "
                f"Ordered along the route through {len(states)} states.")
        body = f'''<h1>EV fast chargers along {disp}</h1>
<p class="lead"><b>{len(found)} DC fast chargers</b> sit within {CORRIDOR_MI:g} miles of {disp}, and
<b>{len(withchain)}</b> of those have somewhere to eat or shop within a 10-minute walk. Listed in
order along the route, {" → ".join(states[:12])}{" …" if len(states) > 12 else ""}.</p>
<a class="cta" href="../../">Open the map →</a>
<p class="stats">Typical power along this corridor is <b>{med} kW</b>, with <b>{big}</b> stops at
150 kW or more and <b>{h24}</b> listed as open 24 hours. Chargers under {INTERSTATE_MIN_KW} kW are
left out — on an interstate run they cost more time than they save.</p>
<h2>Stops with food or shopping within a walk</h2>
{"".join(cards)}
<h2>Other interstates</h2><div class="chips" id="hwchips"></div>'''
        path = f"along/{slug_ref}/index.html"
        page(path, title, desc, body, f"along/{slug_ref}/")
        add(path)
        hw_links.append((disp, slug_ref, len(found)))

    # cross-link the corridor pages to each other + an index
    if hw_links:
        chips = "".join(f'<a href="../{sl}/">{r} <small>{n}</small></a>' for r, sl, n in hw_links)
        for r, sl, n in hw_links:
            f = os.path.join(HERE, f"along/{sl}/index.html")
            html_doc = open(f).read().replace('<div class="chips" id="hwchips"></div>',
                f'<div class="chips">{chips}</div>')
            open(f, "w").write(html_doc)
        idx_chips = "".join(f'<a href="{sl}/">{r} <small>{n} chargers</small></a>' for r, sl, n in hw_links)
        body = f'''<h1>EV fast chargers by interstate</h1>
<p class="lead">Pick an interstate to see every fast charger within {CORRIDOR_MI:g} miles of it, in order
along the route, with the restaurants and stores within a 10-minute walk of each stop.</p>
<div class="chips">{idx_chips}</div>
<h2>Or browse by chain</h2>
<p class="lead">After a specific brand instead? <a href="../near/">All 90 chains, state by state →</a></p>'''
        page("along/index.html", "EV fast chargers along the interstates",
             "Fast chargers along I-95, I-10, I-5, I-80 and other major US interstates, in route "
             "order, with nearby food and shopping for each stop.", body, "along/")
        add("along/index.html")
        print(f"Interstate corridor pages: {len(hw_links)}")

# ---- shared stylesheet (was inlined on every page: 4.9 KB x ~3,000 pages) ----
os.makedirs(os.path.join(HERE, "assets"), exist_ok=True)
open(os.path.join(HERE, "assets", "pages.css"), "w").write(CSS)

# ---- sitemap / robots ----
sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
sm += f"<url><loc>{BASE}/</loc></url>\n" + "".join(f"<url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n"
open(os.path.join(HERE, "sitemap.xml"), "w").write(sm)
open(os.path.join(HERE, "robots.txt"), "w").write(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
print(f"Generated {len(urls)} pages + sitemap.xml + robots.txt (base {BASE})")
