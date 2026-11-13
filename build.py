#!/usr/bin/env python3
"""Generate static SEO pages from data.js:
   near/index.html                      - all chains + states
   near/<chain>/index.html              - "Superchargers near IHOP"
   near/<chain>/<st>/index.html         - "Superchargers near IHOP in Texas"
   sitemap.xml, robots.txt
Run after data/fetch_pois.py.  Usage: python3 build.py [--base https://chargeandchew.com]
"""
import json, math, os, re, sys, html, shutil
from urllib.parse import quote
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

from data_reader import load_data
D = load_data(os.path.join(HERE, "data.js"))
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
# The trip plans (planner.py) measure walks exactly as the app does, from the raw deltas, so
# they keep their own copy before the conversion below rounds them to whole metres.
RAW_MATCHES = {k: dict(v) for k, v in matches.items()}
for _sid, _m in matches.items():
    _s = sites.get(_sid)
    if not _s: continue
    for _k, _v in list(_m.items()):
        if isinstance(_v, list):
            _plat = _s["lat"] + _v[0] / 1e4; _plon = _s["lon"] + _v[1] / 1e4
            _m[_k] = int(_hav(_s["lat"], _s["lon"], _plat, _plon))
WALK = 80

def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
from html import unescape   # 'html' itself is shadowed by locals named html below
def esc(s): return html.escape(str(s))
def bn(s):
    """A brand name as printed: one unbreakable unit. "...have an In-" / "N-Out" broke at the
    hyphen at 375 px. A nowrap span, not U+2011, so the text (and what search engines and
    copy-paste see) is unchanged."""
    e = esc(s)
    return f'<span class="nw">{e}</span>' if "-" in str(s) else e


def ld_script(x):
    """One JSON-LD block. Search engines and AI tools quote these strings verbatim, so they
    must be plain text: the FAQ text used to be HTML-escaped first and showed up as
    "Arby&#x27;s" on 527 pages. Only "</" needs neutralising inside a script element."""
    return ('<script type="application/ld+json">'
            + json.dumps(x, ensure_ascii=False).replace("</", "<\\/") + "</script>")


def place_name(s):
    """"Tesla Supercharger — Woodburn, OR - Tesla Supercharger" doubled the network ~10,000
    times; only prefix the network when the station name does not already say it."""
    net, name = s.get("net") or "DC fast charger", s["name"]
    return name if net.lower() in name.lower() else f"{net} — {name}"
def mins(m): return max(1, round(m / WALK))
# Precomputed categories read as a kind of place, not a brand: "near an ice cream shop".
CATEGORY_KEYS = {"Ice cream shop"}
def near(key):
    """What follows "near" in a title: the brand, or "an ice cream shop" for a category."""
    return f"{art(key)} {key.lower()}" if key in CATEGORY_KEYS else key

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
/* Fonts, self-hosted (assets/fonts, SIL OFL 1.1, licences beside them): a slow or blocked
   font host can no longer hold the first paint (BUG-B03). swap: text paints at once in the
   metric-matched fallbacks below and the real face replaces it when it lands. The fallbacks
   are local Arial scaled to each face's average letter width and line metrics, so the swap
   barely moves a line (the guide pages' CLS came from it). Not preloaded: Chrome holds the
   first paint for a preloaded font, measured at 4x CPU with the fonts 3 s away as FCP 904 ms
   preloaded against 156 ms without. */
@font-face{font-family:Inter;font-style:normal;font-weight:400 800;font-display:swap;src:url(fonts/inter-latin.woff2) format("woff2")}
@font-face{font-family:"Bricolage Grotesque";font-style:normal;font-weight:600 800;font-display:swap;src:url(fonts/bricolage-grotesque-latin.woff2) format("woff2")}
@font-face{font-family:"JetBrains Mono";font-style:normal;font-weight:600 700;font-display:swap;src:url(fonts/jetbrains-mono-latin.woff2) format("woff2")}
@font-face{font-family:"Inter Fallback";font-weight:400 500;src:local("Arial"),local("ArialMT");size-adjust:107.5%;ascent-override:90.1%;descent-override:22.4%;line-gap-override:0%}
@font-face{font-family:"Inter Fallback";font-weight:600 800;src:local("Arial Bold"),local("Arial-BoldMT");size-adjust:101.3%;ascent-override:95.6%;descent-override:23.8%;line-gap-override:0%}
@font-face{font-family:"Bricolage Fallback";font-weight:600 800;src:local("Arial Bold"),local("Arial-BoldMT");size-adjust:102.7%;ascent-override:90.5%;descent-override:26.3%;line-gap-override:0%}
:root{
  --bg:#f6f3ee;--surface:#fffdfa;--surface2:#f2eee8;--surface3:#e9e4dc;--line:#e8e2d9;--line2:#d8d0c5;
  --txt:#1c1917;--dim:#5f574f;--dim2:#6c635a;--accent:#0f7a43;--accent-ink:#fff;
  --chew:#a6510a;--chew-bg:#fbefdc;
  --good:#0f7a43;--good-bg:#e7f4ec;--amber:#f59e0b;--warn:#b45309;--warn-bg:#fdf0dc;
  --sh:0 1px 8px rgba(28,25,23,.08);--mono:'JetBrains Mono',ui-monospace,monospace;
  --sans:Inter,"Inter Fallback",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;--amber-text:#c2640c;
  --display:"Bricolage Grotesque","Bricolage Fallback",Inter,"Inter Fallback",-apple-system,system-ui,sans-serif;
  color-scheme:light;
}
/* Same theme as the map: the head script copies the choice saved there (cc_theme) onto
   data-theme; with no choice the OS decides. */
:root[data-theme="dark"]{
  --bg:#121110;--surface:#1b1a18;--surface2:#24221f;--surface3:#2e2b27;--line:#2c2925;--line2:#3b3732;
  --txt:#f4f1ec;--dim:#b3aba1;--dim2:#9f968c;--accent:#34c97a;--accent-ink:#0b1a10;--amber-text:#fbbf24;
  --chew:#fbbf24;--chew-bg:rgba(251,191,36,.13);
  --good:#34c97a;--good-bg:rgba(52,201,122,.13);--amber:#fbbf24;--warn:#fbbf24;--warn-bg:rgba(251,191,36,.13);
  --sh:0 3px 14px rgba(0,0,0,.36);color-scheme:dark;
}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#121110;--surface:#1b1a18;--surface2:#24221f;--surface3:#2e2b27;--line:#2c2925;--line2:#3b3732;
  --txt:#f4f1ec;--dim:#b3aba1;--dim2:#9f968c;--accent:#34c97a;--accent-ink:#0b1a10;--amber-text:#fbbf24;
  --chew:#fbbf24;--chew-bg:rgba(251,191,36,.13);
  --good:#34c97a;--good-bg:rgba(52,201,122,.13);--amber:#fbbf24;--warn:#fbbf24;--warn-bg:rgba(251,191,36,.13);
  --sh:0 3px 14px rgba(0,0,0,.36);color-scheme:dark;
}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);line-height:1.5;
  font-family:var(--sans);
  -webkit-font-smoothing:antialiased}
a{color:var(--accent)}
:focus-visible{outline:2.5px solid var(--accent);outline-offset:2px;border-radius:8px}
.wrap{max-width:880px;margin:0 auto;padding:20px 16px 64px}
header{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:22px}
header .logo{display:flex;align-items:center;gap:8px;font-family:var(--display);font-weight:800;font-size:18px;letter-spacing:-.3px;
  color:var(--txt);text-decoration:none}
header .logo .mk{width:32px;height:32px;display:grid;place-items:center;flex-shrink:0}
header .logo .mk svg{width:32px;height:32px}
header .logo .c{color:var(--accent)}header .logo .h{color:var(--amber-text)}
header nav{margin-left:auto;display:flex;gap:14px}
@media(max-width:480px){header nav{margin-left:-6px}}
header nav a{color:var(--dim);font-size:13.5px;text-decoration:none;font-weight:600}
h1{font-family:var(--display);text-wrap:balance;font-size:clamp(24px,3.6vw,34px);line-height:1.18;margin-bottom:10px;letter-spacing:-.7px;font-weight:800}
.lead{color:var(--dim);margin-bottom:16px;font-size:15.5px;max-width:62ch}
.lead b{color:var(--txt)}
.nw{white-space:nowrap}
.cta{display:inline-flex;align-items:center;gap:8px;background:var(--accent);color:var(--accent-ink);
  text-decoration:none;font-weight:700;padding:12px 18px;border-radius:12px;margin-bottom:26px;font-size:15px}
.cta.sec{background:var(--surface2);color:var(--txt);border:1px solid var(--line)}
.card{display:flex;gap:13px;align-items:flex-start;padding:16px 2px;border-bottom:1px solid var(--line)}
/* Mirrors the app's list row: the network's mark leads, speed coloured by tier, food amber. */
.card .lead{flex-shrink:0;width:42px;display:flex;justify-content:center;padding-top:2px}
.card .nm{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;font:800 15px/1 var(--display);
  letter-spacing:-.3px;overflow:hidden}
.card .nm.two{font-size:12px}
.card .nm svg{width:100%;height:100%;display:block}
.card .nm.other{background:var(--surface3);color:var(--dim)}
.card .nm.other svg{width:18px;height:18px}
.card .body{flex:1;min-width:0}
.card .n{font-family:var(--display);font-weight:700;font-size:17.5px;line-height:1.25;letter-spacing:-.2px}
.card .sp{margin-top:6px;font-size:12.5px;color:var(--dim);display:flex;flex-wrap:wrap;align-items:center;gap:6px 9px}
.card .sp b{color:var(--txt);font-weight:600}
.spd{text-decoration:none;font:700 11.5px/1.5 var(--mono);border-radius:6px;padding:2px 7px;background:var(--surface2);color:var(--dim)}
.spd.ultra{background:var(--good);color:var(--accent-ink)}
.spd.fast{background:var(--good-bg);color:var(--good)}
.spd.slow{background:transparent;box-shadow:inset 0 0 0 1px var(--line2)}
.card .a{color:var(--dim2);font-size:12.5px;margin-top:4px}
.card .c{font-size:12.5px;margin-top:9px;display:flex;flex-wrap:wrap;gap:5px 7px;color:var(--txt)}
.card .c>span{background:var(--chew-bg);border-radius:8px;padding:3px 9px}   /* the chip, not a name's own .nw span */
.card .c>span i{font-style:normal;color:var(--chew);font-weight:700;margin-left:2px}
.xh{font-size:10.5px;font-weight:700;color:var(--warn);margin-left:5px;white-space:nowrap}
.card .c b{font-weight:700}
.card .l{margin-top:12px;font-size:12.5px;display:flex;gap:8px;flex-wrap:wrap}
.card .l a{text-decoration:none;font-weight:700;padding:8px 14px;border-radius:10px;
  background:var(--surface2);border:1px solid var(--line);color:var(--txt)}
.card .l a.pri{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
h2{font-family:var(--display);font-size:20px;margin:30px 0 10px;letter-spacing:-.3px;font-weight:700}
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
/* Wide content must scroll inside its own box; the page body must never scroll sideways. */
.tripwrap{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 0 22px;
  border:1px solid var(--line);border-radius:14px;box-shadow:var(--sh);
  /* A shadow at whichever edge has more table behind it: on a phone the last column was cut
     mid-word with nothing saying the table scrolls. */
  background:linear-gradient(90deg,var(--surface) 30%,transparent) left/40px 100% no-repeat local,
    linear-gradient(270deg,var(--surface) 30%,transparent) right/40px 100% no-repeat local,
    radial-gradient(farthest-side at 0 50%,rgba(0,0,0,.18),transparent) left/12px 100% no-repeat scroll,
    radial-gradient(farthest-side at 100% 50%,rgba(0,0,0,.18),transparent) right/12px 100% no-repeat scroll,
    var(--surface)}
/* The Road Food Index: findings, ranked tables with a share bar, method, citation. */
ol.find{margin:4px 0 24px;padding:0;list-style:none;counter-reset:f;display:flex;flex-direction:column;gap:10px}
ol.find li{counter-increment:f;position:relative;background:var(--surface);border:1px solid var(--line);border-radius:14px;
  padding:13px 16px 13px 50px;box-shadow:var(--sh);font-size:15px;line-height:1.55;color:var(--dim)}
ol.find li::before{content:counter(f);position:absolute;left:14px;top:13px;width:24px;height:24px;border-radius:50%;
  background:var(--chew-bg);color:var(--chew);font:800 13px/24px var(--display);text-align:center}
ol.find b{color:var(--txt)}
table.idx{border-collapse:collapse;width:100%;font-size:14px}
table.idx th{text-align:left;font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--dim2);
  font-weight:700;padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:bottom}
table.idx td{padding:10px 12px;border-bottom:1px solid var(--line);color:var(--dim);vertical-align:top;line-height:1.45}
table.idx tr:last-child td{border-bottom:0}
table.idx .n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.idx a{color:var(--txt);font-weight:600;text-decoration:underline;text-decoration-color:var(--line2);text-underline-offset:3px}
table.idx b{color:var(--txt)}
table.idx small{color:var(--dim2);font-size:12.5px}
table.idx .bar{display:block;height:4px;border-radius:2px;width:64px;margin:5px 0 0 auto;
  background:linear-gradient(90deg,var(--accent) var(--v),var(--surface3) var(--v))}
ul.method{margin:0 0 12px 18px;color:var(--dim);font-size:14.5px;line-height:1.6}
ul.method li{margin-bottom:6px}
ul.method b{color:var(--txt)}
.cite{background:var(--surface2);border-left:3px solid var(--accent);border-radius:8px;padding:12px 14px;
  font-size:14px;line-height:1.6;color:var(--txt);margin-bottom:12px}
@media(max-width:520px){table.idx .opt{display:none}table.idx th,table.idx td{padding:9px 8px}}
h2+p,h2+.lead{margin-bottom:12px}
table.trip{border-collapse:collapse;width:100%;min-width:460px;font-size:14px}
table.trip th{text-align:left;font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--dim2);font-weight:700;padding:11px 14px;border-bottom:1px solid var(--line)}
table.trip td{padding:12px 14px;vertical-align:top;line-height:1.5;color:var(--dim);
  border-bottom:1px solid var(--line)}
table.trip tr:last-child td{border-bottom:0}
table.trip td b{color:var(--txt)}
table.trip td:first-child{white-space:nowrap;color:var(--txt);font-variant-numeric:tabular-nums}
table.trip small{color:var(--dim2);font-size:12.5px}
table.trip td a{color:inherit;text-decoration:underline;text-decoration-color:var(--line2);text-underline-offset:3px}
table.trip i.ml{font-style:normal;font-weight:700;color:var(--dim)}
table.trip i.ml.meal{color:var(--chew)}
table.trip tr.gap td b{color:var(--warn)}
.plannote{color:var(--dim);font-size:14px;line-height:1.6;margin:-8px 0 22px}
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
@media(pointer:coarse){.chips a{padding:11px 15px}.card .l a{padding:10px 14px}
  header nav{gap:6px}header nav a{padding:12px 6px}footer a{display:inline-block;padding:10px 2px}}
/* On a phone the table's last column was cut off mid-word; there each stop is a stack. */
@media(max-width:520px){
  table.trip,table.trip tbody{display:block;width:100%;min-width:0}
  table.trip thead{display:none}
  table.trip tr{display:block;padding:11px 14px;border-bottom:1px solid var(--line)}
  table.trip tr:last-child{border-bottom:0}
  table.trip td{display:block;padding:1px 0;border:0}
  table.trip td:first-child{font-family:var(--display);font-size:15px}
}
"""

# Shared by every generated page and 404.html: one theme-color per scheme (two unlabelled tags
# left the browser to pick either), the map's saved theme applied before the first paint, and
# the app's fonts (self-hosted, @font-face in pages.css) never hold that paint up.
HEAD_THEME = """<meta name="theme-color" media="(prefers-color-scheme: light)" content="#f6f3ee">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#121110">
<script>try{var t=localStorage.getItem('cc_theme'),h=new Date().getHours();document.documentElement.dataset.theme=(t==='dark'||(t!=='light'&&(h<7||h>=19)))?'dark':'light'}catch(e){}</script>"""


def page(path, title, desc, body, canonical, jsonld="", thin=False, og=None):
    robots = '<meta name="robots" content="noindex,follow">' if thin else ''
    # Per-chain social card when one has been rendered (see make_og.py); the generic card
    # otherwise, so a missing og/ directory can never break the build.
    og_url = f"{BASE}/og/{og}.png" if og and os.path.exists(os.path.join(HERE, "og", og + ".png")) else f"{BASE}/og.png"
    depth = path.count("/")
    root = "../" * depth
    out = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="apple-itunes-app" content="app-id=6809134093">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
{HEAD_THEME}
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
<meta property="og:image" content="{og_url}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
{jsonld}
<link rel="stylesheet" href="{root}assets/pages.css"></head><body><div class="wrap">
<header><a class="logo" href="{root}"><span class="mk"><svg viewBox="0 0 64 64" aria-hidden="true"><defs><linearGradient id="ccg" x1="0" y1="0" x2="1" y2="0.35"><stop offset="0%" stop-color="#16a34a"/><stop offset="100%" stop-color="#f59e0b"/></linearGradient><mask id="ccmask"><rect width="64" height="64" fill="#000"/><circle cx="32" cy="32" r="27" fill="#fff"/><path d="M31.5 9 L17 35.5 h9.5 l-2.5 19 L42 27 H31 z" fill="#000"/><circle cx="57" cy="18" r="12.5" fill="#000"/><circle cx="47.5" cy="14.5" r="3.6" fill="#000"/><circle cx="57.5" cy="30.5" r="3.6" fill="#000"/></mask></defs><g mask="url(#ccmask)"><rect width="64" height="64" fill="url(#ccg)"/></g></svg></span><span><span class="c">Charge</span> &amp; <span class="h">Chew</span></span></a>
<nav><a href="{root}">Map</a><a href="{root}near/">All chains</a><a href="{root}trip/">Road trips</a></nav></header>
{body}
<footer>Charger data: US DOE / NREL <a href="https://afdc.energy.gov/fuels/electricity-locations">AFDC</a> · Chain locations: <a href="https://www.openstreetmap.org">OpenStreetMap</a> · Updated {UPDATED} · <a href="{root}road-food-index/">Road Food Index</a> · <a href="{root}in/">Cities</a> · <a href="{root}privacy/">Privacy</a> · <a href="{root}support/">Support</a>.
Walk times are minimums from straight-line distance at ~3 mph; the real walk is usually longer. Not affiliated with Tesla, Inc. or any listed chain. "Supercharger" is a trademark of Tesla, Inc.</footer>
</div>
<script data-goatcounter="https://chargeandchew.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>
</body></html>"""
    full = os.path.join(HERE, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    open(full, "w").write(out)
    WRITTEN.add(os.path.normpath(full))


# Every page this run writes. Anything else under the generated sections is a page a past run
# made that no longer qualifies; it is deleted at the end instead of living on with old data
# (near/domino-s/me was still serving August numbers in October).
WRITTEN = set()
# The footer names the MONTH of the data, not the day. The refresh runs weekly; a full date
# rewrote every one of ~1,800 pages each week (about 6 MB of history per run) even when only
# a handful had new chargers. The sitemap's lastmod still carries the exact build date.
import datetime as _dt
UPDATED = _dt.date.fromisoformat(D['generated']).strftime('%B %Y')
GENERATED_DIRS = ("near", "along", "trip", "in")


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
        bits.append(f"<b>{sx['walk1']}</b> are close enough that the {bn(key)} is a two-minute walk or less")
    if sx["h24"]:
        bits.append(f"<b>{sx['h24']}</b> are listed as open 24 hours")
    lead = f"Of the {sx['n']} fast chargers with {art(key)} {bn(key)} nearby {where}: " + "; ".join(bits) + "."
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
        (f"How many EV chargers have {art(key)} {bn(key)} within walking distance {where}?",
         f"{sx['n']} public DC fast chargers {where} have {art(key)} {bn(key)} within a 10-minute "
         f"walk (800 m), based on US Department of Energy charger data matched against OpenStreetMap "
         f"locations."),
        (f"Which {bn(key)} charging stop is fastest {where}?",
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
        {"@type": "Question", "name": unescape(re.sub(r"<[^>]+>", "", q)),
         "acceptedAnswer": {"@type": "Answer",
                            "text": unescape(re.sub(r"<[^>]+>", "", a))}} for q, a in qa]}
    return html, schema


def jsonld_chain(key, sites_list, canonical, faq_schema=None):
    """The national chain pages carried no structured data at all — only the state pages did."""
    items = []
    for i, (d, sid) in enumerate(sites_list[:25], 1):
        s = sites[sid]
        items.append({"@type": "ListItem", "position": i, "item": {
            "@type": "Place", "name": place_name(s),
            "address": {"@type": "PostalAddress", "streetAddress": s["street"],
                        "addressLocality": s["city"], "addressRegion": s["st"], "addressCountry": "US"},
            "geo": {"@type": "GeoCoordinates", "latitude": s["lat"], "longitude": s["lon"]}}})
    blocks = [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Chains", "item": f"{BASE}/near/"},
            {"@type": "ListItem", "position": 2, "name": key, "item": f"{BASE}/{canonical}"}]},
        {"@context": "https://schema.org", "@type": "ItemList",
         "name": f"EV fast chargers near {near(key)}",
         "numberOfItems": len(sites_list), "itemListElement": items}]
    if faq_schema:
        blocks.append(faq_schema)
    return "".join(ld_script(x) for x in blocks)


def jsonld_route(name, kind, stop_ids, canonical, total, faq_schema=None):
    """Structured data for the corridor pages (/along/, /trip/).

    These were the only sections shipping none, and they are the ones the site most wants to
    win -- "LA to Las Vegas EV charging" is a whole question answered by one page. Same shape
    as the chain pages: a breadcrumb plus an ItemList of real Places."""
    items = []
    for i, sid in enumerate(stop_ids[:25], 1):
        s_ = sites[sid]
        items.append({"@type": "ListItem", "position": i, "item": {
            "@type": "Place", "name": place_name(s_),
            "address": {"@type": "PostalAddress", "streetAddress": s_["street"],
                        "addressLocality": s_["city"], "addressRegion": s_["st"], "addressCountry": "US"},
            "geo": {"@type": "GeoCoordinates", "latitude": s_["lat"], "longitude": s_["lon"]}}})
    crumb_root = f"{BASE}/trip/" if kind == "trip" else f"{BASE}/along/"
    crumb_name = "Road trips" if kind == "trip" else "Interstates"
    blocks = [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": crumb_name, "item": crumb_root},
            {"@type": "ListItem", "position": 2, "name": name, "item": f"{BASE}/{canonical}"}]},
        {"@context": "https://schema.org", "@type": "ItemList",
         "name": f"EV fast chargers with food along {name}",
         "numberOfItems": total, "itemListElement": items}]
    if faq_schema:
        blocks.append(faq_schema)
    return "".join(ld_script(x) for x in blocks)


def jsonld_state(key, st, sn, sites_list, canonical, faq_schema=None):
    items = []
    for i, (d, sid) in enumerate(sites_list[:25], 1):
        s = sites[sid]
        items.append({"@type": "ListItem", "position": i, "item": {
            "@type": "Place", "name": place_name(s),
            "address": {"@type": "PostalAddress", "streetAddress": s["street"],
                        "addressLocality": s["city"], "addressRegion": s["st"], "addressCountry": "US"},
            "geo": {"@type": "GeoCoordinates", "latitude": s["lat"], "longitude": s["lon"]}}})
    blocks = [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Chains", "item": f"{BASE}/near/"},
            {"@type": "ListItem", "position": 2, "name": key, "item": f"{BASE}/near/{slug(key)}/"},
            {"@type": "ListItem", "position": 3, "name": sn, "item": f"{BASE}/{canonical}"}]},
        {"@context": "https://schema.org", "@type": "ItemList",
         "name": f"Fast chargers near {near(key)} in {sn}",
         "numberOfItems": len(sites_list), "itemListElement": items}]
    if faq_schema:
        blocks.append(faq_schema)
    return "".join(ld_script(x) for x in blocks)


def _read_marks():
    src = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    tt = re.search(r"const TESLA_T = '([^']*)' \+\s*'([^']*)';", src)
    path = tt.group(1) + tt.group(2)
    out = {}
    for m in re.finditer(r"'([^']+)':\s*\{ bg: '([^']+)', ink: '([^']+)', (?:t: '([^']+)'|path: TESLA_T) \}", src):
        out[m.group(1)] = (m.group(2), m.group(3), m.group(4), None if m.group(4) else path)
    return out
NET_MARKS = _read_marks()
BOLT_SVG = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12z"/></svg>'

def mark_html(net):
    m = NET_MARKS.get(net)
    if not m:
        return f'<span class="nm other" title="{esc(net)}">{BOLT_SVG}</span>'
    bg, ink, t, path = m
    inner = f'<svg viewBox="0 0 24 24"><path d="{path}" fill="currentColor"/></svg>' if path else esc(t)
    return f'<span class="nm{" two" if t and len(t) > 1 else ""}" title="{esc(net)}" style="background:{bg};color:{ink}">{inner}</span>'

def speed_tier(kw):
    return "" if not kw else "ultra" if kw >= 250 else "fast" if kw >= 150 else "std" if kw >= 50 else "slow"

# Honest walk times, as in the app: a walk whose straight line crosses a freeway or a divided
# highway at street level (data.js "xh", from the data build) says so, and such places list
# after the ones on the charger's side. The minutes stay the straight-line minimum.
XH_MARK = ('<small class="xh" title="Across a highway from the charger: the walk is longer than the straight '
           'line, or there may be no safe way across">across hwy</small>')

def xh_mark(s, k):
    return XH_MARK if k in (s.get("xh") or ()) else ""

def site_card(s, focus, root):
    """Mirrors the app's list row: network mark, speed badge by tier, food chips in amber."""
    m = matches.get(s["id"], {})
    chains = []
    xh = s.get("xh") or ()
    for k, d in sorted(m.items(), key=lambda x: (x[0] != focus, x[0] in xh, x[1]))[:6]:
        name = '<b>' + bn(k) + '</b>' if k == focus else bn(k)
        chains.append(f"<span>{brands[k]['e']} {name} <i>{mins(d)} min</i>{xh_mark(s, k)}</span>")
    kw = s.get("kw") or 0
    spd = f'<s class="spd {speed_tier(kw)}">{kw} kW</s>' if kw else ""
    stalls = f"<b>{s['stalls']} stall{'s' if s['stalls'] != 1 else ''}</b>" if s.get("stalls") else ""
    net = esc(s.get("net", ""))
    extra = f'<span>+{len(m) - 6}</span>' if len(m) > 6 else ""
    return f"""<div class="card"><div class="lead">{mark_html(s.get("net", ""))}</div><div class="body">
<div class="n">{esc(s['name'])}</div>
<div class="sp">{spd}{stalls}<span>{net}</span></div>
<div class="a">{esc(s['street'])}, {esc(s['city'])}, {s['st']}</div>
<div class="c">{''.join(chains)}{extra}</div>
<div class="l"><a class="pri" href="https://www.google.com/maps/dir/?api=1&destination={s['lat']},{s['lon']}" target="_blank" rel="noopener">Directions</a>\
<a href="{root}?chain={esc(focus)}&amp;state={s['st']}">Show on map</a></div>
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
# Each chain page gets the road trips that pass it ("<!--trips-->"), filled in once the trip
# pages below are built: (page, chain, state or None for the national page).
NEAR_TRIP_SLOTS = []
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
    state_links = "".join(f'<a href="{st.lower()}/">{STATES.get(st, st)} <small>{len(v):,}</small></a>'
                          for st, v in sorted(by_state.items(), key=lambda x: -len(x[1])))
    # national page: top 40 closest, then state links
    sx = page_stats(key, hits)
    stats_html = stats_para(key, "", sx)
    faq_html, faq_schema = faq_block(key, "", sx)
    top = "".join(site_card(sites[sid], key, "../../") for d, sid in hits[:40])
    title = f"EV fast chargers near {near(key)} ({n:,} locations)"
    desc = f"{n} EV DC fast chargers within a 10-minute walk of {art(key)} {key}, across all networks (Tesla, EA, EVgo, ChargePoint and more), ranked by walking distance."
    body = f"""<h1>{b['e']} EV fast chargers near {bn(near(key))}</h1>
<p class="lead">We found <b>{n} DC fast chargers</b> in the US — across all networks — with {art(key)} {bn(key)} within a 10-minute walk (800 m). Closest first; the first few are practically in the same parking lot.</p>
<a class="cta" href="../../?chain={esc(key)}">Open on the map →</a>
{stats_html}
<h2>By state</h2><div class="chips">{state_links}</div>
<!--trips-->
<h2>Closest {min(40, n)} nationwide</h2>{top}
{faq_html}"""
    can = f"near/{cs}/"
    path = f"near/{cs}/index.html"
    page(path, title, desc, body, can, jsonld_chain(key, hits, can, faq_schema), og=slug(key)); add(path)
    NEAR_TRIP_SLOTS.append((path, key, None))


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
            cards += (f'<p class="more">Showing the {STATE_CARD_CAP} closest of {len(v):,}. '
                      f'<a href="../../../?chain={esc(key)}&amp;state={st}">Open the map to see them all →</a></p>')
        others = "".join(f'<a href="../../{slug(k)}/{st.lower()}/">{brands[k]["e"]} {bn(k)} <small>{c}</small></a>'
                         for k, c in sorted(state_chain[st].items(), key=lambda x: -x[1]) if k != key)
        title = f"EV fast chargers near {near(key)} in {sn} ({len(v):,})"
        desc = f"All {len(v):,} EV DC fast chargers in {sn} with {art(key)} {key} within walking distance — network, power, walk time and directions."
        body = f"""<h1>{b['e']} EV fast chargers near {bn(near(key))} in {sn}</h1>
<p class="lead"><b>{len(v):,} DC fast chargers</b> in {sn} have {art(key)} {bn(key)} within a 10-minute walk, shortest walk first.</p>
<a class="cta" href="../../../?chain={esc(key)}&amp;state={st}">Open on the map →</a>
{stats_html}
{cards}
<!--trips-->
<h2>Other chains near fast chargers in {sn}</h2><div class="chips">{others or '—'}</div>
<!--cities-->
<h2>{bn(key)} in other states</h2><div class="chips"><a href="../">All states</a></div>
{faq_html}"""
        can = f"near/{cs}/{st.lower()}/"
        path = f"near/{cs}/{st.lower()}/index.html"
        thin = len(v) < STATE_INDEX_MIN   # keep crawlable, but out of the index for now
        page(path, title, desc, body, can, jsonld_state(key, st, sn, v, can, faq_schema), thin=thin, og=slug(key))
        if not thin: add(path)
        NEAR_TRIP_SLOTS.append((path, key, st))

# ---- near/index.html ----
chain_index_links.sort(reverse=True)
chains_html = "".join(f'<a href="{cs}/">{brands[k]["e"]} {bn(k)} <small>{n}</small></a>' for n, k, cs in chain_index_links)
# Only the strongest few chains per state. Listing all 2,952 combinations turned this into
# a link farm: it dilutes link equity and reads as low quality. The rest stay reachable from
# each chain's own page.
HUB_PER_STATE = 8
states_html = "".join(
    f'<h2>{STATES.get(st, st)}</h2><div class="chips">' +
    "".join(f'<a href="{slug(k)}/{st.lower()}/">{brands[k]["e"]} {bn(k)} <small>{c}</small></a>'
            for k, c in sorted(cm.items(), key=lambda x: -x[1])[:HUB_PER_STATE]) +
    (f'<a href="../?state={st}"><b>all {len(cm)} in {st} →</b></a>' if len(cm) > HUB_PER_STATE else "")
    + "</div>"
    for st, cm in sorted(state_chain.items(), key=lambda x: STATES.get(x[0], x[0])))
body = f"""<h1>EV fast chargers near restaurants &amp; stores</h1>
<p class="lead">{len(matches):,} of {len(sites):,} US DC fast chargers — every major network — have at least one of these {len(chain_index_links)} chains within a 10-minute walk. Pick a chain, or jump to a state.</p>
<a class="cta" href="../">Open the interactive map →</a>
<p><a class="cta sec" href="../along/">Browse by interstate instead →</a> <a class="cta sec" href="../in/">Browse by city →</a></p>
<h2>By chain</h2><div class="chips">{chains_html}</div>
{states_html}"""
page("near/index.html", "EV fast chargers near every chain, by state", "Browse US EV DC fast chargers by the restaurant or store next to them — IHOP, Walmart, Chick-fil-A, Buc-ee's and more, state by state.", body, "near/")
add("near/index.html")

# ---- interstate corridor pages: "chargers with food along I-95" ----
# Real search intent that nothing serves well. Only ~30 pages, each genuinely unique, so
# these are indexed even while the chain x state set is throttled back.
def _hav_km(a, b, c, e):
    R, p = 6371.0, math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((e - b) * p / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def chain_highway(pts, cell_km=1.5):
    # 1) one point per ~cell: merges the two carriageways and the dense city sections
    c=cell_km/111.0; seen={}; 
    for la,lo in pts:
        k=(round(la/c),round(lo/(c/max(0.2,math.cos(math.radians(la))))))
        seen.setdefault(k,(la,lo))
    P=list(seen.values()); n=len(P)
    if n<3: return P
    # 2) start at an end: the point farthest from the centroid along the longer axis
    la_span=max(p[0] for p in P)-min(p[0] for p in P); lo_span=(max(p[1] for p in P)-min(p[1] for p in P))*0.8
    start=min(range(n),key=lambda i:P[i][0]) if la_span>=lo_span else min(range(n),key=lambda i:P[i][1])
    # 3) greedy nearest neighbour
    g={}; G=0.2
    for i,(la,lo) in enumerate(P): g.setdefault((int(la/G),int(lo/G)),[]).append(i)
    used=[False]*n; order=[start]; used[start]=True; cur=start
    for _ in range(n-1):
        la,lo=P[cur]; best=None; r=1
        while best is None and r<60:
            for di in range(-r,r+1):
                for dj in range(-r,r+1):
                    for j in g.get((int(la/G)+di,int(lo/G)+dj),()):
                        if not used[j]:
                            d=_hav_km(la,lo,*P[j])
                            if best is None or d<best[0]: best=(d,j)
            r*=2
        if best is None: break
        used[best[1]]=True; order.append(best[1]); cur=best[1]
    return [P[i] for i in order]

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
        title = f"EV chargers with food along {disp}"
        desc = (f"{len(found):,} public DC fast chargers within {CORRIDOR_MI:g} miles of {disp}, "
                f"{len(withchain):,} of them within a 10-minute walk of a restaurant or store. "
                f"Ordered along the route through {len(states)} states.")
        body = f'''<h1>EV fast chargers along {disp}</h1>
<p class="lead"><b>{len(found):,} DC fast chargers</b> sit within {CORRIDOR_MI:g} miles of {disp}, and
<b>{len(withchain):,}</b> of those have somewhere to eat or shop within a 10-minute walk. Listed in
order along the route, {" → ".join(states[:12])}{" …" if len(states) > 12 else ""}.</p>
<a class="cta" href="../../?hwy={disp}">Open {disp} in the map →</a>
<p class="stats">Typical power along this corridor is <b>{med} kW</b>, with <b>{big}</b> stops at
150 kW or more and <b>{h24}</b> listed as open 24 hours. Chargers under {INTERSTATE_MIN_KW} kW are
left out — on an interstate run they cost more time than they save.<!--rfi--></p>
<h2>Stops with food or shopping within a walk</h2>
{"".join(cards)}
<h2>Other interstates</h2><div class="chips" id="hwchips"></div>'''
        path = f"along/{slug_ref}/index.html"
        page(path, title, desc, body, f"along/{slug_ref}/",
             jsonld_route(disp, "along", [f[1] for f in withchain], f"along/{slug_ref}/", len(withchain)))
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
<h2>Which is best for food?</h2>
<p class="lead">The <a href="../road-food-index/#interstates">Road Food Index</a> ranks every interstate by how many of its fast chargers have somewhere to eat within a walk, with the longest gap on each.</p>
<h2>Planning a specific drive?</h2>
<p class="lead">City-to-city guides pick the stops for you: <a href="../trip/">EV road trip charging with food nearby →</a></p>
<h2>Or browse by chain</h2>
<p class="lead">After a specific brand instead? <a href="../near/">All 90 chains, state by state →</a></p>'''
        page("along/index.html", "EV fast chargers along the interstates",
             "Fast chargers along I-95, I-10, I-5, I-80 and other major US interstates, in route "
             "order, with nearby food and shopping for each stop.", body, "along/")
        add("along/index.html")
        print(f"Interstate corridor pages: {len(hw_links)}")

    # The same highways for the app: "I-5" in the search box, or ?hwy=I-5 from the page above,
    # draws the interstate as a corridor. The stored points are sorted by latitude or longitude,
    # not along the road -- drawn as-is, I-95 was a 50,000 km scribble. chain_highway() keeps
    # one point per ~1.5 km (merging the two carriageways) and walks them nearest-first from
    # one end: path lengths then match the real roads (I-95 3,048 km, I-5 2,203 km).
    hw_out = {}
    for disp, sl, n in hw_links:
        kept = []
        for a, b in chain_highway(highways[disp.replace("-", " ")]):
            if not kept or _hav_km(kept[-1][0], kept[-1][1], a, b) >= 3.0:   # a point every ~3 km
                kept.append([round(a, 3), round(b, 3)])
        hw_out[disp] = kept
    open(os.path.join(HERE, "highways.js"), "w").write(
        "window.CC_HWYS = " + json.dumps(hw_out, separators=(",", ":")) + ";\n")
    print(f"highways.js: {len(hw_out)} interstates, {sum(len(v) for v in hw_out.values())} points")

# ---- trip pages: "EV charging stops from Los Angeles to Las Vegas" ----
# The interstate pages answer "what is on I-15". These answer the question people actually
# type, which names two cities and not a road number. Route geometry is pre-fetched and
# committed by tools/add_trips.py (the list of drives lives there), so this build never
# depends on a routing server being up.
TRIP_PATH = os.path.join(HERE, "data", "trips.json")
TRIP_MI = 5.0
TRIP_MIN_KW = 50

def trip_slug(a, b):
    return f"{slug(a.split(',')[0])}-to-{slug(b.split(',')[0])}"

def trip_card(s, focus, root, href):
    """site_card, but every link points back at this trip rather than a chain+state view."""
    return site_card(s, focus, root).replace(
        f'href="{root}?chain={esc(focus)}&amp;state={s["st"]}"', f'href="{href}"')

# ---- the drive itself, as the app plans it (planner.py) ----
# Each page carries the plan the app shows for that drive leaving at 8:00 am where it starts:
# the meal stops at their local hours, the breaks, the longest charger gap and the arrival. It
# is the app's own code ported, fed the same route, so "Open this drive in the app" opens on the
# same stops at the same times (tools/trip_plan_check.mjs holds the two together). The date is
# the data's: clocks only move with daylight saving, so the pages change with the data.
import planner
PLAN_DAY = _dt.date.fromisoformat(D["generated"])
PLAN_LEAVE = 8 * 60
FAQ_CARS = ("Tesla Model Y", "Ford Mustang Mach-E", "Hyundai Ioniq 5")
CARS = D.get("cars", {})


def kw_for(s, bit):
    """kwFor(): the power of one plug type at a stop."""
    if not bit or not (s.get("conn", 0) & bit) or not s.get("pk"):
        return s.get("kw") or 0
    return s["pk"][0 if bit == 1 else 1 if bit == 2 else 2] or s.get("kw") or 0


def place(s):
    return f"{s['city']}, {s['st']}"


def drive_label(hr):
    """"4h 59m" from hours, never "4h 60m"."""
    m = int(round(hr * 60))
    return f"{m // 60}h {m % 60:02d}m"


def plan_clock(clock, day):
    return clock + ("" if not day else " the next day" if day == 1 else f" on day {day + 1}")


def trip_plan_html(plan, a, b, app):
    """The plan as a sentence (what a search snippet or a group chat wants) and as a table,
    each stop linking to the app at that stop. Returns (sentence, html, short) where `short`
    is the one-line form for the meta description."""
    A, B = a.split(",")[0], b.split(",")[0]
    rows = plan.rows()
    stops = [r for r in rows if r["kind"] == "stop"]
    arr, arr_day = plan.arrive()
    leave = plan.leave_label()
    bits = [f"Leave {esc(A)} at {leave}"]
    for r in stops:
        what = "take a break" if r["label"] == "Break" else f"stop for {r['label'].lower()}"
        bits.append(f"{what} in {esc(r['s']['city'])} at {plan_clock(r['clock'], r['day'])}")
    bits.append(f"arrive in {esc(B)} around {plan_clock(arr, arr_day)}")
    sentence = ", ".join(bits[:-1]) + " and " + bits[-1] + "."
    if not stops:
        sentence = (f"Leave {esc(A)} at {leave} and arrive in {esc(B)} around {plan_clock(arr, arr_day)}: "
                    "the drive is short enough that the plan has no stop. In the app, a later leaving "
                    "time plans a meal on the way when one falls during the drive.")
    short = "; ".join(f"{('break' if r['label'] == 'Break' else r['label'].lower())} in {r['s']['city']} {r['clock']}"
                      for r in stops[:3])
    short = f"Leaving at 8 am: {short + ', ' if short else ''}arrive ~{arr}."
    trs = [f'<tr><td><b>{leave}</b></td><td><b>Leave {esc(a)}</b></td><td></td><td></td></tr>']
    for r in rows:
        when = f"<b>{r['clock']}</b>" + ("<br><small>next day</small>" if r["day"] == 1 else
                                         f"<br><small>day {r['day'] + 1}</small>" if r["day"] > 1 else "")
        if r["kind"] == "gap":
            g = r["gap"]
            trs.append(f'<tr class="gap"><td>{when}</td><td><b>No fast charger for {g["len"]} mi</b><br>'
                       f'<small>from mile {g["from"]} {"to the end" if g["to"] == g["end"] else "to mile " + str(g["to"])}</small></td>'
                       f'<td></td><td>None within {TRIP_MI:g}&nbsp;mi of the route</td></tr>')
            continue
        s, k = r["s"], r["k"]
        m = matches.get(s["id"], {})
        others = [(d, x) for _, d, x in sorted((x in (s.get("xh") or ()), d, x) for x, d in m.items()
                                                if x != k and brands.get(x, {}).get("cat") == "food")[:2]]
        # Each "🌮 Taco Bell 1 min" is one unbreakable unit: on a phone the cell broke between
        # the number and "min" ("Denny's 3 / min,"), or left the emoji at the end of a line.
        food = ([f"<span class=\"nw\">{brands[k]['e']} <b>{bn(k)}</b> {r['walk']} min{xh_mark(s, k)}</span>"] if k else []) + \
               [f"<span class=\"nw\">{brands[x]['e']} {bn(x)} {mins(d)} min{xh_mark(s, x)}</span>" for d, x in others]
        kw = s.get("kw") or 0
        trs.append(f'<tr><td>{when}<br><small><i class="ml{" meal" if r["label"] != "Break" else ""}">{r["label"]}</i> &middot; mile {r["mi"]}</small></td>'
                   f'<td><a href="{app}&amp;stop={s["id"]}"><b>{esc(place(s))}</b></a><br><small>{esc(s["name"])}</small></td>'
                   f'<td>{str(kw) + " kW" if kw else "&mdash;"}<br><small>{s.get("stalls", 0)} stall{"s" if s.get("stalls", 0) != 1 else ""}</small></td>'
                   f'<td>{", ".join(food) or "&mdash;"}</td></tr>')
    trs.append(f'<tr><td><b>~{arr}</b>{"<br><small>next day</small>" if arr_day == 1 else ""}</td>'
               f'<td><b>Arrive in {esc(b)}</b></td><td></td><td></td></tr>')
    table = ('<div class="tripwrap"><table class="trip plan"><thead><tr><th>When</th><th>Where</th>'
             f'<th>Charger</th><th>Food within a walk</th></tr></thead><tbody>{"".join(trs)}</tbody></table></div>')
    return sentence, table, short


def trip_faq(plan, a, b, t, found, withfood, big, tesla, halfway, n_all, food_all):
    """Questions people ask about a drive, answered from this route's data. The same strings
    make the visible answers and the FAQPage markup, so the two cannot disagree."""
    A, B = esc(a.split(",")[0]), esc(b.split(",")[0])
    stops = [r for r in plan.rows() if r["kind"] == "stop"]
    meals = [r for r in stops if r["label"] != "Break"]
    brk = [r for r in stops if r["label"] == "Break"]
    arr, arr_day = plan.arrive()
    leave = plan.leave_label()
    # Every DC fast charger on the drive, counted as the app counts them (see the trip loop).
    nfound, nfood = n_all, food_all
    qa = []

    def at_stop(r):
        kw = r["s"].get("kw") or 0
        return (f"{bn(r['k'])} is a {r['walk']}-minute walk from a {str(kw) + ' kW ' if kw else ''}charger"
                + (" (across the highway, so further on foot)" if r["k"] in (r["s"].get("xh") or ()) else "")
                if r["k"] else f"there is a {str(kw) + ' kW ' if kw else ''}charger")

    # 1. Where to eat
    if meals:
        ans = f"Leaving {A} at {leave}, " + "; ".join(
            f"{r['label'].lower()} falls in {esc(place(r['s']))} around {plan_clock(r['clock'], r['day'])}, where {at_stop(r)}"
            for r in meals) + "."
        if brk:
            ans += (" The break in " if len(brk) == 1 else " The breaks: ") + "; ".join(
                f"{esc(place(r['s']))} at {plan_clock(r['clock'], r['day'])}" + (" has " if len(brk) == 1 else ", ") +
                f"{bn(r['k'])} {r['walk']} min from the charger" +
                (" (across the highway)" if r["k"] in (r["s"].get("xh") or ()) else "") for r in brk) + "."
    elif brk:
        ans = (f"Leaving {A} at {leave}, no mealtime falls on the way. The plan's break" + ("s" if len(brk) > 1 else "") + " "
               + "; ".join(f"in {esc(place(r['s']))} at {plan_clock(r['clock'], r['day'])}: {at_stop(r)}" for r in brk) + ".")
    else:
        ans = f"Leaving {A} at {leave} you arrive around {plan_clock(arr, arr_day)}, too soon for a meal stop."
        if halfway:
            s, k, w = halfway
            ans += (f" About halfway, {esc(place(s))} (mile {plan.mile_at[s['id']]}) has {bn(k)} a {mins(w)}-minute walk "
                    f"from a {s.get('kw') or 0} kW charger" + (" (across the highway)" if k in (s.get("xh") or ()) else "") + ".")
    ans += f" In all, {nfood:,} of the roughly {nfound:,} fast chargers along the way have a restaurant within a 10-minute walk."
    qa.append((f"Where should I stop to eat between {A} and {B}?", ans))

    # 2. How many chargers
    qa.append((f"How many fast chargers are there between {A} and {B}?",
               f"About {nfound:,} DC fast chargers are within {TRIP_MI:g} miles of the {t['mi']:,.0f}-mile route, "
               f"{len(found):,} of them {TRIP_MIN_KW} kW or more. {big:,} charge at 150 kW or more, {tesla:,} are on "
               f"the Tesla network, and {nfood:,} have a restaurant within a 10-minute walk."))

    # 3. The longest gap
    g = plan.longest()
    if g["len"] >= 30:
        def at_mile(mi):
            for s in plan.vis:
                if plan.mile_at[s["id"]] == mi: return f" ({esc(place(s))})"
            return ""
        where = (f"from the start to mile {g['to']}{at_mile(g['to'])}" if g["from"] == 0 else
                 f"from mile {g['from']}{at_mile(g['from'])} to the end" if g["to"] == g["end"] else
                 f"between mile {g['from']}{at_mile(g['from'])} and mile {g['to']}{at_mile(g['to'])}")
        gap_a = f"{g['len']} miles, {where}, with no DC fast charger within {TRIP_MI:g} miles of the route."
    else:
        gap_a = (f"No stretch is longer than {max(g['len'], 1)} miles: there is a DC fast charger within "
                 f"{TRIP_MI:g} miles of the route at least that often.")
    qa.append((f"What is the longest stretch without a fast charger between {A} and {B}?", gap_a))

    # 4. Chains
    cnt = Counter(k for f in found for k in matches.get(f[1], {})
                  if brands.get(k, {}).get("cat") == "food" and k not in CATEGORY_KEYS)   # "Ice cream shop" is no chain
    top = sorted(cnt.items(), key=lambda x: (-x[1], x[0]))[:6]
    if top:
        names = [f"{bn(k)} (near {n} charger{'s' if n != 1 else ''})" if i == 0 else f"{bn(k)} ({n})"
                 for i, (k, n) in enumerate(top)]
        lst = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        qa.append((f"Which restaurant chains are on the way from {A} to {B}?",
                   f"Counting the fast chargers of {TRIP_MIN_KW} kW or more on the route, the chains most often "
                   f"within a 10-minute walk are {lst}."))

    # 5. Charging time: the app's own estimate, for three common cars, at the plan's stops
    pool = [r["s"] for r in stops] or ([halfway[0]] if halfway else [])
    est = []
    for car in FAQ_CARS:
        spec = CARS.get(car)
        if not spec: continue
        best = None
        for s in pool:
            if s.get("conn", 0) & spec[2] and (best is None or kw_for(s, spec[2]) > kw_for(best, spec[2])):
                best = s
        m_ = planner.charge_min(best, spec) if best else None
        if m_:
            est.append(f"about {planner.hm_label(m_)} for a {esc(car)} at the {kw_for(best, spec[2])} kW charger in {esc(place(best))}")
    if est:
        qa.append((f"How long does it take to charge on the way from {A} to {B}?",
                   "It depends on the car. The app's estimate for a 10–80% charge is " + "; ".join(est) +
                   ". These are rough figures from each car's battery size and peak charging speed; a cold "
                   "battery or a busy site takes longer."))

    # 6. Drive time with the stops
    nb, nm = len(brk), len(meals)
    parts = ([f"{nb} break{'s' if nb != 1 else ''} of about {planner.DWELL_BREAK} minutes"] if nb else []) + \
            ([f"{nm} meal{'s' if nm != 1 else ''} of about {planner.DWELL_MEAL}"] if nm else [])
    qa.append((f"How long is the drive from {A} to {B} with stops?",
               f"About {drive_label(t['hr'])} of driving for {t['mi']:,.0f} miles. " +
               (f"Leaving at {leave} with the plan's {' and '.join(parts)}, you arrive around {plan_clock(arr, arr_day)}."
                if parts else f"Leaving at {leave} without a stop, you arrive around {plan_clock(arr, arr_day)}.")))

    html_ = '<h2>Questions about this drive</h2><div class="faq">' + "".join(
        f"<details><summary>{q}</summary><p>{x}</p></details>" for q, x in qa) + "</div>"
    plain = lambda h: unescape(re.sub(r"<[^>]+>", "", h))
    schema = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": plain(q), "acceptedAnswer": {"@type": "Answer", "text": plain(x)}} for q, x in qa]}
    return html_, schema


TRIP_REGIONS = [
    ("The West", "CA NV AZ UT CO NM OR WA ID MT WY"),
    ("Texas and the South Central states", "TX OK AR LA"),
    ("The Southeast", "GA FL TN AL MS NC SC KY"),
    ("The Northeast and Mid-Atlantic", "NY MA PA DC MD VA NJ CT RI VT NH ME DE WV"),
    ("The Midwest", "IL MI OH IN MO MN WI IA NE KS ND SD"),
]

trip_links, trip_meta, chain_trips = [], {}, {}
TRIP_PLANS = {}   # the same plans, for the Road Food Index's gap table
if os.path.exists(TRIP_PATH):
    trips = json.load(open(TRIP_PATH))
    for tk in sorted(trips, key=lambda k: trips[k]["a"]):
        t = trips[tk]
        pts = t["pts"]
        cum = [0.0]
        for i in range(1, len(pts)):
            cum.append(cum[-1] + _hav_m(pts[i-1][0], pts[i-1][1], pts[i][0], pts[i][1]) / 1609.34)
        total_mi = cum[-1]
        a, b = t["a"], t["b"]
        # The app on this drive, leaving at 8:00 am: what the plan below shows. Distance and time
        # go through the same arithmetic as an OSRM answer does in the app (metres / MI).
        app_url = f"../../?from={quote(a)}&amp;to={quote(b)}&amp;c={TRIP_MI:g}&amp;leave=0800"
        plan = planner.Plan(D["sites"], RAW_MATCHES, brands, pts, t["mi"] * planner.MI / planner.MI,
                            t["hr"] * 3600 / 3600, PLAN_DAY, PLAN_LEAVE, TRIP_MI)
        TRIP_PLANS[tk] = plan
        # The chargers on the drive are the app's: the plan's corridor (applyCorridor's cells,
        # nearest point and ties). This page had its own grid, narrower than the corridor, and
        # counted only 50 kW and up, so it said "228 DC fast chargers" where the app on the same
        # drive said "236 chargers". The count is every DC fast charger, as the app's; the lists
        # below keep to 50 kW and up, and say so. The app's live route is denser than the line
        # stored here, which moves the count by a charger or two at the corridor's edge: "about".
        onroute = sorted((bi, sid) for sid, bi in plan.order.items())
        n_all = len(onroute)
        food_all = sum(1 for _, sid in onroute if any(brands.get(k, {}).get("cat") == "food" for k in matches.get(sid, {})))
        found = [(bi, sid, _hav_m(sites[sid]["lat"], sites[sid]["lon"], pts[bi][0], pts[bi][1]))
                 for bi, sid in onroute if (sites[sid].get("kw") or 0) >= TRIP_MIN_KW]
        if len(found) < 10:
            print(f"  skip trip {tk}: only {len(found):,} chargers")
            continue
        found.sort()
        is_food = lambda k: brands.get(k, {}).get("cat") == "food"
        withfood = [f for f in found if any(is_food(k) for k in matches.get(f[1], {}))]

        sl = trip_slug(a, b)
        sentence, plan_tbl, plan_short = trip_plan_html(plan, a, b, app_url)

        # Halfway: the strongest stop near the middle with a meal a short walk away. Only the Q&A
        # uses it, for a drive too short for the plan to stop.
        half = None
        for bi_, sid, _d in withfood:
            if abs(cum[bi_] - total_mi / 2) > total_mi * 0.15: continue
            m = matches.get(sid, {})
            fk = [(d, k) for k, d in m.items() if is_food(k) and k not in planner.NOT_A_MEAL]
            if not fk: continue
            d, k = min(fk)
            sx = sites[sid]
            rank = (d > 400, -min(sx.get("kw") or 0, 350), -min(sx.get("stalls") or 0, 40), d)
            if half is None or rank < half[0]:
                half = (rank, (sx, k, d))
        half = half[1] if half else None

        # Spread the cards across the whole drive. Taking the first 48 in route order would
        # fill the page with the origin city's suburbs and never reach the far end.
        NBINS = 40
        if len(withfood) > NBINS:
            bins = {}
            for f in withfood:
                bi_ = min(NBINS - 1, int(cum[f[0]] / max(total_mi, 1) * NBINS))
                sx = sites[f[1]]
                m = matches.get(f[1], {})
                walk = min((d for k, d in m.items() if is_food(k)), default=9e9)
                rank = (-min(sx.get("kw") or 0, 350), -min(sx.get("stalls") or 0, 40), walk)
                if bi_ not in bins or rank < bins[bi_][0]:
                    bins[bi_] = (rank, f)
            shown = [v[1] for _, v in sorted(bins.items())]
        else:
            shown = withfood
        cards = []
        for bi, sid, dist in shown:
            m = matches.get(sid, {})
            fk = [k for k in m if is_food(k)]
            focus = min(fk, key=lambda k: m[k]) if fk else (min(m, key=lambda k: m[k]) if m else "")
            # "Show on map" opens this drive in the app, at this stop.
            cards.append(trip_card(sites[sid], focus, "../../", f"{app_url}&amp;stop={sid}"))

        kws = [sites[f[1]]["kw"] for f in found if sites[f[1]].get("kw")]
        med = sorted(kws)[len(kws) // 2] if kws else 0
        big = sum(1 for k in kws if k >= 150)
        tesla = sum(1 for f in found if "Tesla" in (sites[f[1]].get("net") or ""))
        drive = drive_label(t["hr"])
        # The longest stretch with no fast charger near the route, by the app's rule (any DC
        # fast charger within the corridor), so the page, its Q&A and the app's gap row agree.
        g = plan.longest()
        if g["len"] >= 60:
            where = (f"from the start to mile {g['to']}" if g["from"] == 0 else
                     f"from mile {g['from']} to the end" if g["to"] == g["end"] else
                     f"between mile {g['from']} and mile {g['to']}")
            gap_txt = f" Counting every DC fast charger, the longest stretch without one is <b>{g['len']} miles</b>, {where}."
        else:
            gap_txt = f" Counting every DC fast charger, there is one at least every <b>{max(g['len'], 1)} miles</b> of the way."
        faq_html, faq_schema = trip_faq(plan, a, b, t, found, withfood, big, tesla, half, n_all, food_all)

        # Google truncates near 60 characters and the suffix adds 16, so lead with the two
        # cities -- that is what people type -- and keep the whole thing inside the budget.
        title = f"{a.split(',')[0]} to {b.split(',')[0]} EV charging stops"
        desc = (f"{plan_short} About {n_all:,} fast chargers on the {t['mi']:,.0f}-mile drive from {a} to {b}, "
                f"{food_all:,} with a restaurant a short walk away.")
        plan_sec = (f"<h2>Leaving {esc(a.split(',')[0])} at {plan.leave_label()}</h2>\n"
                    f'<p class="lead">{sentence}</p>\n{plan_tbl}\n'
                    f'<p class="plannote">Meals fall near their local hour (times are local at each stop), with about '
                    f"{planner.DWELL_BREAK} minutes for a break and {planner.DWELL_MEAL} for a meal. "
                    "It is a driver&rsquo;s plan, not a charging plan: where you need to charge depends on "
                    f'your car. <a href="{app_url}">Open this drive in the app</a> to pick another leaving time.</p>')
        spread = (" &mdash; the strongest stop in each stretch of the drive, so the list covers "
                  "the whole route rather than filling up with the city you left"
                  if len(withfood) > NBINS else "")
        body = (f"<h1>EV charging stops from {esc(a)} to {esc(b)}</h1>\n"
                f'<p class="lead">The drive is <b>{t["mi"]:,.1f} miles</b>, about <b>{drive}</b>. Along it '
                f"sit <b>about {n_all:,} DC fast chargers</b> within {TRIP_MI:g} miles of the route "
                f"&mdash; and <b>{food_all:,}</b> of those have somewhere to eat within a "
                "10-minute walk, so the charging stop and the meal are the same stop.</p>\n"
                f'<a class="cta" href="{app_url}">Open this drive in the app &rarr;</a>\n'
                f"{plan_sec}\n"
                f'<p class="stats">Typical power along this route is <b>{med} kW</b>, with <b>{big}</b> '
                f"stops at 150 kW or more and <b>{tesla}</b> on the Tesla network. Chargers under "
                f"{TRIP_MIN_KW} kW are left out of the list &mdash; on a drive this length they cost more "
                f"time than they save.{gap_txt}</p>\n"
                "<h2>Every stop with food within a walk</h2>\n"
                f"<p>In order along the route{spread}.</p>\n"
                f'{"".join(cards)}\n'
                f"{faq_html}\n"
                '<h2>Other road trips</h2><div class="chips" id="tripchips"></div>\n<!--cities-->')
        path = f"trip/{sl}/index.html"
        # Trip pages are the ones people share; make_og.py renders a card naming the drive.
        page(path, title, desc, body, f"trip/{sl}/",
             jsonld_route(f"{a.split(',')[0]} to {b.split(',')[0]}", "trip",
                          [f[1] for f in shown], f"trip/{sl}/", len(withfood), faq_schema),
             og=f"trip-{sl}")
        add(path)
        trip_links.append((a.split(",")[0], b.split(",")[0], sl, len(withfood)))
        trip_meta[sl] = (a, b, ((t["alat"] + t["blat"]) / 2, (t["alon"] + t["blon"]) / 2))
        # Which chains this drive passes, and in which states: for the chain pages' trip links.
        for f in found:
            for k in matches.get(f[1], {}):
                chain_trips.setdefault((k, sites[f[1]]["st"]), Counter())[sl] += 1
                chain_trips.setdefault((k, None), Counter())[sl] += 1

    if trip_links:
        names = {sl: (x, y, n) for x, y, sl, n in trip_links}
        chip = lambda sl, pre, unit="": (f'<a href="{pre}{sl}/">{esc(names[sl][0])} &rarr; {esc(names[sl][1])} '
                                         f'<small>{names[sl][2]}{unit}</small></a>')
        # Related drives, not all 150: the way back, the other drives from the same start or to
        # the same end (nearest first, so Atlanta -> Miami also gets Orlando -> Miami), the drives
        # on from the destination, then the nearest others.
        for sl, (a, b, mid) in trip_meta.items():
            def rel(o):
                oa, ob, om = trip_meta[o]
                tier = (0 if (oa, ob) == (b, a) else 1 if oa == a or ob == b else
                        2 if oa == b or ob == a else 3)
                return (tier, _hav_km(mid[0], mid[1], om[0], om[1]), o)
            near_ = sorted((o for o in trip_meta if o != sl), key=rel)[:10]
            f = os.path.join(HERE, f"trip/{sl}/index.html")
            doc = open(f).read().replace('<h2>Other road trips</h2><div class="chips" id="tripchips"></div>',
                '<h2>More road trips</h2><div class="chips">' + "".join(chip(o, "../") for o in near_) +
                '<a href="../"><b>All road trips &rarr;</b></a></div>')
            open(f, "w").write(doc)
        # The index: by region of the start, then by start and destination.
        groups = []
        for title_, sts in TRIP_REGIONS:
            mine = sorted((sl for sl, (a, b, _) in trip_meta.items() if a.split(", ")[1] in sts.split()),
                          key=lambda sl: (names[sl][0], names[sl][1]))
            if mine:
                groups.append(f"<h2>{title_}</h2>\n" + '<div class="chips">' +
                              "".join(chip(sl, "", " stops") for sl in mine) + "</div>")
        missing = set(trip_meta) - {sl for g in groups for sl in re.findall(r'href="([^"/]+)/"', g)}
        if missing:
            sys.exit(f"build.py: trips in no TRIP_REGIONS group: {sorted(missing)}")
        idx_body = (
            "<h1>EV road trip charging, planned around food</h1>\n"
            f'<p class="lead">{len(trip_links)} popular drives, each with the plan for leaving at 8 am '
            f"(where the meal stops fall, and when you arrive), every fast charger within {TRIP_MI:g} "
            "miles of the route, and the restaurants within a 10-minute walk of each one.</p>\n"
            + "\n".join(groups) + "\n"
            "<h2>Not your route?</h2>\n"
            '<p class="lead">The map plans any drive: type a start and a destination and it finds '
            'the chargers along it. <a class="cta" href="../">Open the map &rarr;</a></p>\n'
            "<h2>Or browse by road</h2>\n"
            '<p class="lead"><a href="../along/">Every charger along the interstates &rarr;</a></p>\n'
            "<h2>Where the gaps are</h2>\n"
            '<p class="lead">The longest stretches without a fast charger on these drives, and the chains, '
            'interstates and states best for a meal while you charge: <a href="../road-food-index/">the Road Food '
            'Index &rarr;</a></p>\n'
            "<h2>Or start from a city</h2>\n"
            '<p class="lead"><a href="../in/">Fast chargers near food, city by city &rarr;</a></p>')
        page("trip/index.html", "EV road trip charging stops with food nearby",
             "Charging stops for popular US road trips - LA to Las Vegas, New York to Boston, "
             "Dallas to Austin and more - with the restaurants within a 10-minute walk of each stop.",
             idx_body, "trip/")
        add("trip/index.html")
        print(f"Trip pages: {len(trip_links)}")
        # The app shares a planned drive with a link to its guide when there is one, so it
        # needs the list of guides: one constant in index.html, space-separated slugs.
        _ix = os.path.join(HERE, "index.html")
        _h = open(_ix, encoding="utf-8").read()
        _h2, _n = re.subn(r"const TRIP_PAGES = '[^']*';",
                          "const TRIP_PAGES = '" + " ".join(sorted(sl for _, _, sl, _ in trip_links)) + "';", _h)
        if _n != 1:
            sys.exit(f"build.py: expected exactly one TRIP_PAGES constant in index.html, found {_n}")
        if _h2 != _h:
            open(_ix, "w", encoding="utf-8").write(_h2)

trip_names = {sl: (x, y) for x, y, sl, n in trip_links}
# The chain pages: the drives that pass that chain (in that state), most stops first.
for path, key, st in NEAR_TRIP_SLOTS:
    f = os.path.join(HERE, path)
    cnt = chain_trips.get((key, st), Counter())
    top = sorted(cnt.items(), key=lambda x: (-x[1], x[0]))[:6 if st else 8]
    pre = "../../../trip/" if st else "../../trip/"
    sec = ""
    if top:
        sec = (f"<h2>Road trips with {bn(near(key))} on the way</h2>"
               f"<p>How many of each drive&rsquo;s fast chargers{' in ' + esc(STATES.get(st, st)) if st else ''} "
               f"have {art(key)} {bn(key)} within a walk:</p><div class=\"chips\">" +
               "".join(f'<a href="{pre}{sl}/">{esc(trip_names[sl][0])} &rarr; {esc(trip_names[sl][1])} '
                       f'<small>{c} stop{"s" if c != 1 else ""}</small></a>' for sl, c in top) + "</div>")
    doc = open(f).read()
    open(f, "w").write(doc.replace("<!--trips-->\n", sec + ("\n" if sec else ""), 1))


# ---- the Road Food Index: a data page for press and answer engines ----
# Every number comes from tools/road_food_index.py, which verify.py runs again and compares
# with this page and its CSVs. Nothing here is typed in: the findings name whoever is first
# or last in the data, so they stay true after a refresh.
sys.path.insert(0, os.path.join(HERE, "tools"))
import road_food_index as rfi
RFI = rfi.compute(HERE, plans=TRIP_PLANS)
RFI_DIR = "road-food-index"
rfi.write_csvs(RFI, os.path.join(HERE, RFI_DIR))
RFI_TITLE = "The Road Food Index"
RFI_DATE = PLAN_DAY.strftime("%B %-d, %Y")


def rfi_bold(sentence):
    """The findings as the page shows them: the numbers in bold, the words unchanged."""
    parts = re.split(r"(?<![\w-])(\d[\d,]*(?:\.\d+)?%?(?: miles)?)(?![\w-])", sentence)
    return "".join(f"<b>{esc(x)}</b>" if i % 2 else esc(x) for i, x in enumerate(parts))


def rfi_table(cols, rows, cap=""):
    """cols: (label, class) where class has n (a number, right-aligned) and/or opt (hidden on a
    phone, where the table keeps to the columns that carry the point)."""
    th = "".join(f'<th class="{c}" scope="col">{l}</th>' for l, c in cols)
    trs = "".join("<tr>" + "".join(f'<td class="{c}">{v}</td>' for (l, c), v in zip(cols, r)) + "</tr>" for r in rows)
    cap = f"<caption>{cap}</caption>" if cap else ""
    return f'<div class="tripwrap"><table class="idx">{cap}<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def rfi_bar(v):
    """A share as a number over a thin bar on a 0-100 scale."""
    return f'{v}%<span class="bar" style="--v:{v}%"></span>'


_food = [c for c in RFI["chains"] if c["type"] == "food"]
_chain_rows = [[c["rank"], f'<a href="../near/{c["slug"]}/">{c["emoji"]}&nbsp;{bn(c["chain"])}</a>',
                f'{c["sites"]:,}', rfi_bar(c["share"]), f'{c["close"]:,}', f'{c["median_walk"]} min']
               for c in RFI["chains"][:25]]
_ready = rfi.ready_ranked(RFI)
_ready_rows = [[i, f'<a href="../near/{c["slug"]}/">{c["emoji"]}&nbsp;{bn(c["chain"])}</a>', f'{c["locations"]:,}',
                f'{c["ready"]:,}', rfi_bar(c["ready_share"])] for i, c in enumerate(_ready[:15], 1)]
_low = _ready[-3:][::-1]
_road_rows = [[r["rank"], f'<a href="../along/{r["slug"]}/">{r["interstate"]}</a>', f'{r["miles"]:,}',
               f'{r["chargers"]:,}', rfi_bar(r["food_share"]), f'{r["food_per_100"]}',
               "&mdash;" if r["gap"] is None else f'{r["gap"]} mi'] for r in RFI["interstates"]]
_nogap = [r["interstate"] for r in RFI["interstates"] if r["gap"] is None]
_pairs = rfi.unique_pairs(RFI["drives"])[:10]
_gap_rows = [[f'<a href="../trip/{d["slug"]}/">{esc(d["a"])} &rarr; {esc(d["b"])}</a>', f'<b>{d["gap"]} mi</b>',
              f'{esc(d["gap_from_place"])} &rarr; {esc(d["gap_to_place"])}<br><small>mile {d["gap_from"]} to {d["gap_to"]} of {d["miles"]:,}</small>']
             for d in _pairs]
_ranked = [s for s in RFI["states"] if s.get("rank")]
_state_rows = [[s["rank"], esc(s["state"]), f'{s["sites"]:,}', rfi_bar(s["food_share"]), f'{s["big"]:,}',
                f'{bn(s["top_chain"])} <small>{s["top_chain_sites"]:,}</small>' if s["top_chain"] else "&mdash;"]
               for s in _ranked]
_unranked = [s for s in RFI["states"] if not s.get("rank")]

# Long drives with the plan's lunch stop. Named for Thanksgiving only in the run-up to it.
_tg = _dt.date.fromisoformat(RFI["thanksgiving"])
_long = sorted(rfi.unique_pairs(sorted(RFI["drives"], key=lambda d: (-d["hours"], d["slug"]))),
               key=lambda d: (-d["hours"], d["slug"]))[:12]
_long_rows = [[f'<a href="../trip/{d["slug"]}/">{esc(d["a"])} &rarr; {esc(d["b"])}</a>',
               f'{d["miles"]:,} mi<br><small>{drive_label(d["hours"])}</small>',
               (f'{esc(d["lunch_place"])} <span class="nw">at {d["lunch_clock"]}</span>' +
                (f'<br><small>{brands[d["lunch_chain"]]["e"]} {bn(d["lunch_chain"])} {d["lunch_walk"]} min walk</small>'
                 if d["lunch_chain"] else "")) if d["lunch_place"] else "&mdash;",
               f'{d["gap"]} mi'] for d in _long]
if PLAN_DAY.month == 11 and PLAN_DAY <= _tg:
    _long_h = "Driving for Thanksgiving"
    _long_lead = (f"Thanksgiving is {_tg.strftime('%A, %B %-d')}. These are the {len(_long)} longest of the "
                  f"{len(RFI['drives'])} drives we plan, with where lunch falls if you leave at 8 am. Each "
                  "guide has the full plan, every charger on the way and the food a walk from each one.")
else:
    _long_h = "The longest drives we plan"
    _long_lead = (f"The {len(_long)} longest of the {len(RFI['drives'])} drives we plan, with where lunch falls if "
                  "you leave at 8 am. Each guide has the full plan, every charger on the way and the food a walk "
                  "from each one.")

_csvs = [("chains", "Chains", f"all {len(RFI['chains'])}"),
         ("interstates", "Interstates", f"all {len(RFI['interstates'])}"),
         ("states", "States", f"all {len(RFI['states'])}"),
         ("drives", "Drives", f"all {len(RFI['drives'])}, with their longest gaps")]
RFI_DESC = (f"Which restaurant chains, interstates and states are best for a meal while an EV charges: "
            f"{len(RFI['chains'])} chains matched against all {RFI['n_sites']:,} US DC fast-charger sites, "
            f"{len(RFI['interstates'])} interstates and the longest charger gaps on {len(RFI['drives'])} drives. "
            f"Data as of {RFI_DATE}.")
_find = rfi.headlines(RFI)
rfi_body = f"""<h1>{RFI_TITLE}</h1>
<p class="lead">How often is there somewhere to eat within a 10-minute walk of a US fast charger, and
which chains, interstates and states do best? We matched all <b>{RFI['n_sites']:,}</b> public DC fast-charger
sites in the US Department of Energy&rsquo;s database against <b>{len(RFI['chains'])}</b> restaurant and store
chains mapped in OpenStreetMap. Data as of <b>{RFI_DATE}</b>.</p>
<h2>Key findings</h2>
<ol class="find">{''.join(f'<li>{rfi_bold(x)}</li>' for x in _find)}</ol>
<a class="cta" href="../">Find a stop with food on the map &rarr;</a>

<h2 id="chains">Chains next to the most fast chargers</h2>
<p>Out of {RFI['n_sites']:,} DC fast-charger sites, how many have the chain within a 10-minute walk (800 m), how
many within two minutes, and the typical walk. The top 25; the CSV has all {len(RFI['chains'])}.</p>
{rfi_table([("#", "n"), ("Chain", ""), ("Sites", "n"), ("Share", "n"), ("2-min walk", "n opt"), ("Typical walk", "n opt")], _chain_rows)}

<h2 id="locations">Chains with a charger at the most of their locations</h2>
<p>The other way round: of each chain&rsquo;s US locations, the share with a DC fast charger within a
10-minute walk. Chains with at least {rfi.CHAIN_MIN_LOCATIONS} locations; the top 15. At the other end:
{', '.join(f"{bn(c['chain'])} ({c['ready_share']}% of {c['locations']:,})" for c in _low)}.</p>
{rfi_table([("#", "n"), ("Chain", ""), ("Locations", "n opt"), ("With a charger", "n opt"), ("Share", "n")], _ready_rows)}

<h2 id="interstates">Interstates, best to worst for food</h2>
<p>Every fast charger of {rfi.INTERSTATE_MIN_KW} kW or more within {rfi.CORRIDOR_MI:g} miles of the interstate,
the share with somewhere to eat within a 10-minute walk, how many such stops there are per 100 miles, and the
longest stretch with none of those chargers.{(' ' + ', '.join(_nogap) + ' have no gap figure: their mapped line is not one continuous road.') if _nogap else ''}</p>
{rfi_table([("#", "n"), ("Interstate", ""), ("Miles", "n opt"), ("Chargers", "n opt"), ("With food", "n"), ("Food stops / 100 mi", "n opt"), ("Longest gap", "n")], _road_rows)}

<h2 id="gaps">The longest gaps on popular drives</h2>
<p>On each of the {len(RFI['drives'])} drives we plan, the longest stretch with no DC fast charger within
{rfi.TRIP_MI:g} miles of the road, counting the start and the end. A drive and its way back are listed once.</p>
{rfi_table([("Drive", ""), ("Gap", "n"), ("Between", "")], _gap_rows)}

<h2 id="states">States</h2>
<p>The share of each state&rsquo;s fast-charger sites with somewhere to eat within a 10-minute walk, sites of
150 kW or more, and the chain most often next to them. States with at least {rfi.STATE_MIN_SITES} sites;
{', '.join(f"{esc(s['state'])} ({s['sites']})" for s in _unranked) or 'none'} {'has' if len(_unranked) == 1 else 'have'} fewer.</p>
{rfi_table([("#", "n"), ("State", ""), ("Sites", "n opt"), ("With food", "n"), ("150 kW+", "n opt"), ("Most common chain", "opt")], _state_rows)}

<h2 id="drives">{_long_h}</h2>
<p>{_long_lead}</p>
{rfi_table([("Drive", ""), ("Distance", "opt"), ("Lunch, leaving 8 am", ""), ("Longest gap", "n opt")], _long_rows)}
<p><a href="../trip/"><b>All {len(RFI['drives'])} road trip guides &rarr;</b></a></p>

<h2 id="method">How we counted</h2>
<ul class="method">
<li><b>Chargers</b>: every public DC fast-charger site in the US DOE / NREL
<a href="https://afdc.energy.gov/fuels/electricity-locations">Alternative Fuels Data Center</a> station list, all
networks, as the map shows them: under 24 kW, private and truck-only sites left out, and one site per location
however many stalls it lists. {RFI['n_sites']:,} sites.</li>
<li><b>Chains</b>: restaurant and store locations from <a href="https://www.openstreetmap.org">OpenStreetMap</a>,
by brand. Map entries of one chain within {rfi.LOCATION_M} m of each other count as one location (a store and its
fuel station are often mapped separately). OpenStreetMap is volunteer-made and misses some locations.</li>
<li><b>Within a walk</b>: within {D['walkM']} m in a straight line, about 10 minutes at 3 mph. Walk times are
minimums; the real walk is usually longer, and a place whose straight line crosses a freeway or a divided
highway is marked &ldquo;across hwy&rdquo;. &ldquo;Somewhere to eat&rdquo; is any of the {len(_food)} restaurant
chains we track or an ice cream shop.</li>
<li><b>Interstates</b>: the road as OpenStreetMap maps it; miles are measured along the line the map draws, which
merges both directions and can differ a little from official lengths.</li>
<li><b>Drives</b>: the {len(RFI['drives'])} routes of our road trip guides, as the app plans them.</li>
</ul>
<p class="lead">Data as of <b>{RFI_DATE}</b>. It is refreshed weekly, so the numbers on this page move with it.</p>

<h2 id="download">Download the data</h2>
<div class="chips">{''.join(f'<a href="{n}.csv" download>{l} <small>CSV, {d}</small></a>' for n, l, d in _csvs)}</div>

<h2 id="cite">How to cite</h2>
<p class="cite">Charge &amp; Chew, &ldquo;{RFI_TITLE},&rdquo; data as of {RFI_DATE}, {BASE}/{RFI_DIR}/. Charger data from
the US Department of Energy (AFDC); chain locations &copy; OpenStreetMap contributors (ODbL).</p>
<p>The tables and charts on this page are free to reuse, including commercially, under
<a href="https://creativecommons.org/licenses/by/4.0/" rel="license">CC BY 4.0</a>: credit
&ldquo;Charge &amp; Chew Road Food Index&rdquo; with a link to this page, and keep the OpenStreetMap credit above.</p>
<p>Questions about the data: <a href="mailto:chargeandchew@gmail.com">chargeandchew@gmail.com</a>.</p>"""

RFI_LD = {
    "@context": "https://schema.org", "@type": "Dataset", "name": RFI_TITLE, "description": RFI_DESC,
    "url": f"{BASE}/{RFI_DIR}/", "dateModified": D["generated"],
    "creator": {"@type": "Organization", "name": BRAND, "url": f"{BASE}/"},
    "creditText": f"{BRAND}, {RFI_TITLE}",
    "license": "https://creativecommons.org/licenses/by/4.0/",
    "spatialCoverage": {"@type": "Place", "name": "United States"},
    "isBasedOn": ["https://afdc.energy.gov/fuels/electricity-locations", "https://www.openstreetmap.org"],
    "keywords": ["EV charging", "DC fast chargers", "restaurants", "road trips", "interstates"],
    "variableMeasured": [
        "Fast-charger sites with each chain within a 10-minute walk",
        "Share of each chain's locations with a fast charger within a 10-minute walk",
        "Share of each interstate's fast chargers with food within a 10-minute walk",
        "Longest gap between fast chargers on each drive",
        "Share of each state's fast-charger sites with food within a 10-minute walk"],
    "distribution": [{"@type": "DataDownload", "name": f"{l} ({d})", "encodingFormat": "text/csv",
                      "contentUrl": f"{BASE}/{RFI_DIR}/{n}.csv"} for n, l, d in _csvs],
}
page(f"{RFI_DIR}/index.html", f"{RFI_TITLE}: food at US EV fast chargers", RFI_DESC, rfi_body, f"{RFI_DIR}/",
     ld_script(RFI_LD), og=RFI_DIR)
add(f"{RFI_DIR}/index.html")
_ord = lambda n: f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
for _x in RFI["interstates"]:
    _f = os.path.join(HERE, "along", _x["slug"], "index.html")
    if os.path.exists(_f):
        _doc = open(_f).read()
        open(_f, "w").write(_doc.replace("<!--rfi-->", (
            f' On the <a href="../../{RFI_DIR}/#interstates">Road Food Index</a>, {_x["interstate"]} ranks '
            f'<b>{_ord(_x["rank"])}</b> of {len(RFI["interstates"])} interstates for food: <b>{_x["food_share"]}%</b> of '
            f"these chargers have somewhere to eat within a 10-minute walk."), 1))
print(f"Road Food Index: {len(RFI['chains'])} chains, {len(RFI['interstates'])} interstates, {len(RFI['drives'])} drives")


# ---- city pages: "EV fast chargers near food in Austin, TX" ----
# People type "[city] superchargers" far more than "chargers near Best Buy in Iowa". One page
# per metro (data/metros.json), covering the fast chargers within the app's default 25 miles of
# downtown, measured the way the app's area view measures them (planner.hav, planner.MI), so
# "Open Austin in the map" shows the same set. A metro whose centre is within 25 miles of a
# larger one's would repeat that page, and one with fewer stops than the list holds is too thin
# to be worth a search result: both are skipped (counted in the build log).
CITY_MI = 25
CITY_BEST = 12
CITY_INDEX_MIN = CITY_BEST       # stops with food: fewer cannot fill the list
CITY_NEAR_MI = 150               # "nearby cities"
_metros = json.load(open(os.path.join(HERE, "data", "metros.json")))["metros"]
_trips_all = json.load(open(TRIP_PATH)) if os.path.exists(TRIP_PATH) else {}
_is_food = lambda k: brands.get(k, {}).get("cat") == "food"
CITIES, CITY_SKIPPED = [], []
for _m in _metros:
    _big = next((c for c in CITIES if planner.hav(_m["lat"], _m["lon"], c["lat"], c["lon"]) <= CITY_MI * planner.MI), None)
    if _big is None:
        _big = next((c for c in CITY_SKIPPED if c.get("why") == "thin" and
                     planner.hav(_m["lat"], _m["lon"], c["lat"], c["lon"]) <= CITY_MI * planner.MI), None)
    if _big is not None:
        CITY_SKIPPED.append(dict(_m, why=f"within {CITY_MI} mi of {_big['name']}"))
        continue
    _in = [s for s in D["sites"] if abs(s["lat"] - _m["lat"]) < 0.5 and
           planner.hav(_m["lat"], _m["lon"], s["lat"], s["lon"]) <= CITY_MI * planner.MI]
    _food = [s for s in _in if any(_is_food(k) for k in matches.get(s["id"], {}))]
    if len(_food) < CITY_INDEX_MIN:
        CITY_SKIPPED.append(dict(_m, why="thin", n_food=len(_food)))
        continue
    CITIES.append(dict(_m, slug=f"{slug(_m['name'])}-{_m['st'].lower()}", sites=_in, food=_food))
CITY_BY_SLUG = {c["slug"]: c for c in CITIES}


def city_walk(s):
    """The nearest place to eat at a stop: (metres, chain)."""
    m = matches.get(s["id"], {})
    return min(((d, k) for k, d in m.items() if _is_food(k)), default=(9e9, None))


def city_rank(s):
    """Fastest first, then the most stalls, then the shortest walk to food."""
    return (-(s.get("kw") or 0), -min(s.get("stalls") or 0, 40), city_walk(s)[0], s["id"])


def city_ends(c):
    """The road trip guides that start or end in this city."""
    out = []
    for tk, t in _trips_all.items():
        sl = trip_slug(t["a"], t["b"])
        if sl not in trip_meta: continue
        if (planner.hav(c["lat"], c["lon"], t["alat"], t["alon"]) <= CITY_MI * planner.MI or
                planner.hav(c["lat"], c["lon"], t["blat"], t["blon"]) <= CITY_MI * planner.MI):
            out.append(sl)
    return sorted(out, key=lambda sl: (trip_names[sl][0] != c["name"], trip_names[sl]))


def lst(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


for c in CITIES:
    N, ST, cs = c["name"], c["st"], c["slug"]
    where = f"{N}, {ST}"
    root = "../../"
    app = f"{root}?at={c['lat']:.4f},{c['lon']:.4f}&amp;r={CITY_MI}"
    sites_, food_ = c["sites"], c["food"]
    best = sorted(food_, key=city_rank)[:CITY_BEST]
    kws = sorted(s.get("kw") or 0 for s in sites_ if s.get("kw"))
    med = kws[len(kws) // 2] if kws else 0
    big = sum(1 for k in kws if k >= 150)
    h24 = [s for s in food_ if s.get("h24")]
    nets = Counter(s.get("net") for s in sites_ if s.get("net")).most_common(3)
    ch = Counter(k for s in sites_ for k in matches.get(s["id"], {}) if k not in CATEGORY_KEYS)
    chains_ = sorted(ch.items(), key=lambda x: (-x[1], x[0]))[:16]
    food_chains = [(k, n) for k, n in sorted(ch.items(), key=lambda x: (-x[1], x[0])) if _is_food(k)][:5]
    trips_ = city_ends(c)
    near_ = sorted((o for o in CITIES if o is not c and
                    planner.hav(c["lat"], c["lon"], o["lat"], o["lon"]) <= CITY_NEAR_MI * planner.MI),
                   key=lambda o: planner.hav(c["lat"], c["lon"], o["lat"], o["lon"]))[:8]
    c.update(n_all=len(sites_), n_food=len(food_), trips=trips_)

    def chain_href(k):
        return (f"{root}near/{slug(k)}/{ST.lower()}/" if os.path.exists(os.path.join(HERE, "near", slug(k), ST.lower(), "index.html"))
                else f"{root}near/{slug(k)}/")
    cards = []
    for s in best:
        d, k = city_walk(s)
        cards.append(site_card(s, k, root).replace(f'href="{root}?chain={esc(k)}&amp;state={s["st"]}"',
                                                     f'href="{app}&amp;stop={s["id"]}"'))
    netline = ", ".join(f"{esc(n)} ({c_})" for n, c_ in nets)
    stats = (f'<p class="stats">Typical power here is <b>{med} kW</b>, and <b>{big}</b> of the {len(sites_):,} '
             f"charge at 150 kW or more. <b>{len(h24)}</b> of the stops with food are listed as open 24 hours. "
             f"Most are on {netline}.</p>")
    # Questions, answered from this city's data. The same strings make the visible answers and
    # the FAQPage markup, so the two cannot disagree.
    qa = [(f"How many EV fast chargers near {esc(N)} have food within walking distance?",
           f"{len(food_):,} of the {len(sites_):,} public DC fast chargers within {CITY_MI} miles of downtown {esc(N)} "
           f"have somewhere to eat within a 10-minute walk (800 m), based on US Department of Energy charger data "
           f"matched against OpenStreetMap.")]
    if best:
        s0 = best[0]; d0, k0 = city_walk(s0)
        qa.append((f"What is the fastest charger with food nearby in {esc(N)}?",
                   f"{esc(s0['name'])} in {esc(s0['city'])}, {s0['st']}, at {s0.get('kw') or 0} kW"
                   + (f" with {s0['stalls']} stall{'s' if s0['stalls'] != 1 else ''}" if s0.get("stalls") else "")
                   + f". {bn(k0)} is a {mins(d0)}-minute walk away."))
    if food_chains:
        qa.append((f"Which restaurant chains are next to the most fast chargers around {esc(N)}?",
                   lst([f"{bn(k)} ({n})" for k, n in food_chains]) +
                   f": the number of fast chargers within {CITY_MI} miles with each one within a 10-minute walk."))
    if h24:
        s1 = max(h24, key=lambda s: (s.get("kw") or 0, s.get("stalls") or 0, -s["id"]))
        qa.append((f"Are there 24-hour fast chargers with food near {esc(N)}?",
                   f"{len(h24)} of the stops with somewhere to eat nearby are listed as open 24 hours, the fastest "
                   f"being {esc(s1['name'])} in {esc(s1['city'])} at {s1.get('kw') or 0} kW. The restaurants keep "
                   f"their own hours."))
    else:
        qa.append((f"Are there 24-hour fast chargers with food near {esc(N)}?",
                   "None of the stops with somewhere to eat nearby is listed as open 24 hours. Check the network's "
                   "app for hours before a late stop."))
    if nets:
        qa.append((f"Which charging networks are around {esc(N)}?",
                   f"Within {CITY_MI} miles: " + lst([f"{esc(n)} ({c_} sites)" for n, c_ in nets]) +
                   ". Set your car in the map and it shows which stops your plug fits."))
    if trips_:
        qa.append((f"Which road trips from {esc(N)} have charging guides?",
                   lst([f"{esc(trip_names[sl][0])} to {esc(trip_names[sl][1])}" for sl in trips_[:8]]) +
                   ": each guide plans the meal stops for leaving at 8 am and lists every charger on the way."))
    faq_html = '<h2>Common questions</h2><div class="faq">' + "".join(
        f"<details><summary>{q}</summary><p>{a}</p></details>" for q, a in qa) + "</div>"
    plain = lambda h: unescape(re.sub(r"<[^>]+>", "", h))
    faq_schema = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": plain(q), "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in qa]}
    items = [{"@type": "ListItem", "position": i, "item": {
        "@type": "Place", "name": place_name(s),
        "address": {"@type": "PostalAddress", "streetAddress": s["street"], "addressLocality": s["city"],
                    "addressRegion": s["st"], "addressCountry": "US"},
        "geo": {"@type": "GeoCoordinates", "latitude": s["lat"], "longitude": s["lon"]}}} for i, s in enumerate(best, 1)]
    ld = "".join(ld_script(x) for x in [
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Cities", "item": f"{BASE}/in/"},
            {"@type": "ListItem", "position": 2, "name": where, "item": f"{BASE}/in/{cs}/"}]},
        {"@context": "https://schema.org", "@type": "ItemList", "name": f"EV fast chargers near food in {where}",
         "numberOfItems": len(food_), "itemListElement": items},
        faq_schema])
    body = (f"<h1>EV fast chargers near food in {esc(where)}</h1>\n"
            f'<p class="lead"><b>{len(sites_):,} DC fast chargers</b> sit within {CITY_MI} miles of downtown {esc(N)}, '
            f"across every network, and <b>{len(food_):,}</b> of them have somewhere to eat within a 10-minute walk, "
            "so the charging stop and the meal are the same stop.</p>\n"
            f'<a class="cta" href="{app}">Open {esc(N)} in the map &rarr;</a>\n{stats}\n'
            f"<h2>The best stops with food</h2>\n<p>The {len(best)} fastest of the {len(food_):,} with somewhere to eat "
            "within a walk; with equal power, the most stalls, then the shortest walk.</p>\n" + "".join(cards) + "\n"
            f"<h2>Chains next to fast chargers around {esc(N)}</h2>\n<p>How many of the {len(sites_):,} have each within a "
            "10-minute walk:</p>\n<div class=\"chips\">" +
            "".join(f'<a href="{chain_href(k)}">{brands[k]["e"]} {bn(k)} <small>{n}</small></a>' for k, n in chains_) + "</div>\n" +
            ((f"<h2>Road trips from {esc(N)}</h2>\n<div class=\"chips\">" +
              "".join(f'<a href="{root}trip/{sl}/">{esc(trip_names[sl][0])} &rarr; {esc(trip_names[sl][1])}</a>' for sl in trips_) +
              "</div>\n") if trips_ else "") +
            (("<h2>Nearby cities</h2>\n<div class=\"chips\">" +
              "".join(f'<a href="../{o["slug"]}/">{esc(o["name"])}, {o["st"]} <small>{len(o["food"]):,}</small></a>' for o in near_) +
              '<a href="../"><b>All cities &rarr;</b></a></div>\n') if near_ else
             '<h2>Other cities</h2>\n<div class="chips"><a href="../"><b>All cities &rarr;</b></a></div>\n') +
            faq_html)
    title = f"EV fast chargers near food in {where}"
    desc = (f"{len(food_):,} of the {len(sites_):,} EV DC fast chargers within {CITY_MI} miles of {where} have somewhere "
            f"to eat within a 10-minute walk. The fastest stops, the chains next to them, and road trips from {N}.")
    page(f"in/{cs}/index.html", title, desc, body, f"in/{cs}/", ld, og="cities")
    add(f"in/{cs}/index.html")

# The index of cities, by region (the trip index's regions, with Alaska and Hawaii in the West).
CITY_REGIONS = [(t, sts + (" AK HI" if t == "The West" else "")) for t, sts in TRIP_REGIONS]
_groups = []
for t, sts in CITY_REGIONS:
    mine = sorted((c for c in CITIES if c["st"] in sts.split()), key=lambda c: (c["name"], c["st"]))
    if mine:
        _groups.append(f"<h2>{t}</h2>\n" + '<div class="chips">' + "".join(
            f'<a href="{c["slug"]}/">{esc(c["name"])}, {c["st"]} <small>{c["n_food"]:,}</small></a>' for c in mine) + "</div>")
_lost = [c["slug"] for c in CITIES if not any(f'href="{c["slug"]}/"' in g for g in _groups)]
if _lost:
    sys.exit(f"build.py: cities in no region: {_lost}")
page("in/index.html", "EV fast chargers near food, city by city",
     f"EV DC fast chargers with somewhere to eat within a 10-minute walk in {len(CITIES)} US cities, from New York "
     "and Los Angeles to Boise and Savannah: the fastest stops and the chains next to them.",
     "<h1>EV fast chargers near food, city by city</h1>\n"
     f'<p class="lead">{len(CITIES)} US cities and metro areas: the fast chargers within {CITY_MI} miles of each '
     "downtown, the fastest ones with somewhere to eat a short walk away, and the chains next to them. The number "
     "is how many have food within a 10-minute walk.</p>\n" + "\n".join(_groups) + "\n"
     "<h2>Not your city?</h2>\n"
     '<p class="lead">The map covers every fast charger in the US: search a town, or press and hold anywhere. '
     '<a class="cta" href="../">Open the map &rarr;</a></p>\n'
     '<p class="lead">Or browse <a href="../trip/">road trips</a>, <a href="../along/">interstates</a> or '
     '<a href="../near/">chains by state</a>.</p>', "in/")
add("in/index.html")
print(f"City pages: {len(CITIES)} (skipped {len(CITY_SKIPPED)}: "
      + "; ".join(f"{c['name']}, {c['st']} ({c['why'] if c['why'] != 'thin' else str(c['n_food']) + ' with food'})"
                  for c in CITY_SKIPPED) + ")")

# Link them where a reader already is: a chain's state page lists that state's cities, and a
# road trip lists the cities it starts and ends in.
_city_st = {}
for c in CITIES:
    _city_st.setdefault(c["st"], []).append(c)
for path, key, st in NEAR_TRIP_SLOTS:
    f = os.path.join(HERE, path)
    doc = open(f).read()
    sec = ""
    if st and _city_st.get(st):
        sec = (f"<h2>Fast chargers near food in {esc(STATES.get(st, st))} cities</h2><div class=\"chips\">" +
               "".join(f'<a href="../../../in/{c["slug"]}/">{esc(c["name"])}</a>'
                       for c in sorted(_city_st[st], key=lambda c: -c["n_food"])) + "</div>\n")
    open(f, "w").write(doc.replace("<!--cities-->\n", sec, 1))
for sl in trip_meta:
    f = os.path.join(HERE, f"trip/{sl}/index.html")
    doc = open(f).read()
    mine = [c for c in CITIES if sl in c["trips"]]
    sec = ""
    if mine:
        sec = ("<h2>Charging around " + " and ".join(esc(c["name"]) for c in mine[:2]) + "</h2><div class=\"chips\">" +
               "".join(f'<a href="../../in/{c["slug"]}/">{esc(c["name"])}, {c["st"]} <small>{c["n_food"]:,} stops with food</small></a>'
                       for c in mine) + "</div>")
    open(f, "w").write(doc.replace("\n<!--cities-->", "\n" + sec if sec else "", 1))


# ---- llms.txt: what this site is, for AI answer engines (llmstxt.org) ----
# Plain facts and the pages that hold the detail, with this week's numbers. Linked from nowhere:
# the tools that read it look for it at the root.
LLMS_PAGES = [
    ("Road Food Index", f"{RFI_DIR}/", "which chains, interstates and states are best for food at US fast chargers, "
     "and the longest charger gaps on popular drives; CSV downloads and a citation line"),
    ("Road trip guides", "trip/", f"{len(trip_links)} US drives, each with a meal-timed plan for leaving at 8 am, "
     "every fast charger within 5 miles of the route and the food a walk from each"),
    ("City guides", "in/", f"the fast chargers with food a walk away in {len(CITIES)} US cities"),
    ("Chains", "near/", f"fast chargers near each of the {len(RFI['chains'])} chains, nationally and by state"),
    ("Interstates", "along/", "the fast chargers along major interstates, in route order"),
    ("Support", "support/", "how to use the app, what the numbers mean, how to report a problem"),
    ("Privacy", "privacy/", "what the app does with your data"),
]
llms = f"""# {BRAND}

> A free map of every public DC fast charger in the US and the restaurants and stores within a
> 10-minute walk of each one, so an EV driver can plan a charging stop around a meal. On the web
> at {BASE}/ and as an iPhone app. No account, no ads.

Data as of {RFI_DATE}, refreshed weekly: {RFI['n_sites']:,} DC fast-charger sites, {RFI['n_food']:,} of them
with somewhere to eat within a 10-minute walk, matched against {len(RFI['chains'])} restaurant and store chains.

## What the app does

- Search a chain ("IHOP"), a town, a kind of shop ("ice cream") or a whole drive ("LA to Las Vegas with In-N-Out"); the map lists the fast chargers with that place within a walk, shortest walk first.
- Plan a drive: the chargers along the route in driving order, the meal stops that fall at mealtimes in local time, and the longest stretch with no fast charger. It is a driver's plan, not a charging plan: it does not model battery charge.
- Set your car to see which stops your plug fits and a rough 10-80% charge time.
- iPhone app: the same map, plus a home-screen widget for the nearest stop with food and Siri shortcuts.

## Key pages

{chr(10).join(f"- [{n}]({BASE}/{p}): {d}" for n, p, d in LLMS_PAGES)}

## Data and its limits

- Chargers: US Department of Energy / NREL Alternative Fuels Data Center (https://afdc.energy.gov/fuels/electricity-locations), all networks; under 24 kW, private and truck-only sites left out.
- Restaurants and stores: OpenStreetMap (https://www.openstreetmap.org), © OpenStreetMap contributors, ODbL.
- "Within a walk" is within {D['walkM']} m in a straight line, about 10 minutes at 3 mph; walk times are minimums, and a place across a freeway or divided highway from the charger is marked "across hwy".
- No live availability, prices or wait times: check the network's own app before relying on a stop.

## Privacy

No account and no sign-in. Location is used on the device to centre the map and is never sent to {BRAND}. Saved stops and settings stay in the browser or the app. Page views are counted anonymously (GoatCounter, no cookies).

## Findings from the Road Food Index ({RFI_DATE})

{chr(10).join(f"- {x}" for x in rfi.headlines(RFI))}

Cite as: {BRAND}, "{RFI_TITLE}," data as of {RFI_DATE}, {BASE}/{RFI_DIR}/. Free to reuse under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/) with that credit.

## Contact

chargeandchew@gmail.com
"""
open(os.path.join(HERE, "llms.txt"), "w", encoding="utf-8").write(llms)

# ---- privacy + support (App Store requires both URLs; they are useful pages regardless) ----
PRIVACY_BODY = """<h1>Privacy</h1>
<p class="lead">Charge &amp; Chew has no accounts, no sign-in and no advertising. Here is exactly what
happens with your data, on the website and in the iOS app.</p>
<h2>Your location</h2>
<p>Used only when you tap the locate button, to center the map on you. It is never sent to us.
Some of it reaches the map services the app needs, none of which is ours: a town-level position
(rounded to about a kilometre) goes to <a href="https://nominatim.openstreetmap.org">OpenStreetMap's
Nominatim</a> to put a place name on the area; your start and destination go to the
<a href="https://project-osrm.org">OSRM</a> router when you plan a route; and map tiles and nearby-place
lookups reveal the area you are looking at to the services listed below. Deny location and
everything still works by searching a city or pressing on the map.</p>
<h2>What we keep on your device</h2>
<p>Saved stops, your car, theme and filter choices, and the last area you looked at — in your
browser's local storage, or the app's. Nothing is sent to us. Clearing site data, or deleting the
app, removes all of it.</p>
<h2>Analytics</h2>
<p>We count page views with <a href="https://www.goatcounter.com">GoatCounter</a>, which is
open-source and privacy-first: no cookies, no personal data, no cross-site tracking. It tells us
roughly how many people used the site and which pages, and nothing about who you are.</p>
<h2>Other services the app talks to</h2>
<p>Map tiles from Esri; charger data from the US DOE / NREL Alternative Fuel Stations database (bundled, refreshed
monthly); chain and shop locations from OpenStreetMap, including live lookups through its Overpass
service. Tapping a place or "Directions" opens Google Maps or Apple Maps, which are governed by
their own policies.</p>
<h2>Contact</h2>
<p>Questions or a deletion request (there is nothing on our side to delete, but ask anyway):
<a href="mailto:chargeandchew@gmail.com">chargeandchew@gmail.com</a>.</p>
<p class="stats">Last updated 2026-11-12.</p>"""
page("privacy/index.html", "Privacy", "What Charge & Chew does with your data: no accounts, no ads, your location is never sent to us, anonymous page counts only.", PRIVACY_BODY, "privacy/")
add("privacy/index.html")

SUPPORT_BODY = """<h1>Support</h1>
<p class="lead">Charge &amp; Chew finds DC fast chargers within a short walk of the restaurants and stores
you'd actually stop at. Free, no account. Here is how to get the most out of it, and how to reach us.</p>
<h2>How to use it</h2>
<p><b>Search</b> a chain ("IHOP"), a place ("Barstow"), a kind of shop ("tire shop"), or a whole
drive ("LA to Las Vegas"). <b>Tap a stop</b> to see every walkable place with minutes, and get
directions. <b>Press and hold the map</b> to search that spot. <b>Set your car</b> (the car icon) for
connector compatibility and a rough charge time at each stop.</p>
<h2>On iPhone</h2>
<p>Charge &amp; Chew is also an iPhone app, with a home-screen widget for the nearest stop with
food and Siri shortcuts: <a href="https://apps.apple.com/us/app/charge-chew-ev-stops/id6809134093">get it
on the App Store</a>.</p>
<h2>Things worth knowing</h2>
<p>Walk times are straight-line estimates at about 3 mph. Charge times assume a typical peak rate
for your car. Charger hours, pricing and stall counts come from public data and can be out of date —
always check the network's own app before relying on a stop, and treat a single-stall site with
caution.</p>
<h2>Something wrong?</h2>
<p>A dead charger, a closed restaurant, a chain we should add, a bug:
<a href="https://github.com/durukean/charge-and-chew/issues/new?title=Problem%20report">open an
issue</a> or email <a href="mailto:chargeandchew@gmail.com">chargeandchew@gmail.com</a>. Include the
stop's name and city.</p>
<h2>Data sources</h2>
<p>US DOE / NREL <a href="https://afdc.energy.gov/fuels/electricity-locations">Alternative Fuel
Stations</a> database; <a href="https://www.openstreetmap.org">OpenStreetMap</a> for places; Esri
basemap. Not affiliated with Tesla, Inc. or any listed chain or network.</p>
<p><a href="../privacy/">Privacy</a></p>"""
page("support/index.html", "Support", "How to use Charge & Chew, what the numbers mean, and how to report a problem.", SUPPORT_BODY, "support/")
add("support/index.html")

# ---- shared stylesheet (was inlined on every page: 4.9 KB x ~3,000 pages) ----
os.makedirs(os.path.join(HERE, "assets"), exist_ok=True)
open(os.path.join(HERE, "assets", "pages.css"), "w").write(CSS)

# ---- retire pages this run no longer generates ----
_retired = [os.path.normpath(os.path.join(_root, "index.html"))
            for _d in GENERATED_DIRS for _root, _dirs, _files in os.walk(os.path.join(HERE, _d))
            if "index.html" in _files and os.path.normpath(os.path.join(_root, "index.html")) not in WRITTEN]
if len(_retired) > 200:
    # A run that suddenly retires hundreds of pages is a broken build, not a quiet month.
    sys.exit(f"refusing: {len(_retired)} pages would be retired (e.g. {_retired[:3]})")
for _full in _retired:
    os.remove(_full)
    _dir = os.path.dirname(_full)
    while _dir != HERE and os.path.isdir(_dir) and not os.listdir(_dir):
        os.rmdir(_dir); _dir = os.path.dirname(_dir)
_retired = [os.path.relpath(_f, HERE) for _f in _retired]
if _retired:
    print(f"Retired {len(_retired)} page(s) no longer generated: {', '.join(_retired[:5])}")

# ---- sitemap / robots ----
sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
# <lastmod> tells crawlers which pages a monthly refresh actually touched. Data pages carry the
# dataset's date; privacy and support do not change with the data, so they carry none rather
# than a date that would be false.
def _sm_url(u):
    static = u.endswith(("/privacy/", "/support/"))
    return f"<url><loc>{u}</loc>" + ("" if static else f"<lastmod>{D['generated']}</lastmod>") + "</url>\n"
sm += _sm_url(f"{BASE}/") + "".join(_sm_url(u) for u in urls) + "</urlset>\n"
open(os.path.join(HERE, "sitemap.xml"), "w").write(sm)
# /admin/ reads private analytics; it is noindex too, but keep crawlers out of it entirely.
open(os.path.join(HERE, "robots.txt"), "w").write(
    f"User-agent: *\nAllow: /\nDisallow: /admin/\nSitemap: {BASE}/sitemap.xml\n")
# ---- data.js cache-busting: the URL follows the CONTENT ----
# The service worker serves data.js cache-first, keyed on its full URL. The ?v= used to be a
# hand-edited constant ("?v=9", unchanged for months), and this pipeline rewrote the file but
# never the URL -- so returning web visitors kept their first cached copy for good, and the
# monthly refresh only reached them by accident whenever a code change bumped sw.js. A hash of
# the content makes new data a new URL (cache miss, fetch, old entry dropped) while unchanged
# data keeps the same URL, so nobody re-downloads a megabyte for nothing.
import hashlib
_dj = os.path.join(HERE, "data.js")
if os.path.exists(_dj):
    _ver = hashlib.sha256(open(_dj, "rb").read()).hexdigest()[:10]
    _ix = os.path.join(HERE, "index.html")
    _h = open(_ix, encoding="utf-8").read()
    _h2, _n = re.subn(r'src="data\.js\?v=[^"]*"', f'src="data.js?v={_ver}"', _h)
    if _n != 1:
        sys.exit(f"build.py: expected exactly one data.js <script> in index.html, found {_n}")
    if _h2 != _h:
        open(_ix, "w", encoding="utf-8").write(_h2)
    print(f"data.js version {_ver}")
_hw = os.path.join(HERE, "highways.js")
if os.path.exists(_hw):
    _ver3 = hashlib.sha256(open(_hw, "rb").read()).hexdigest()[:10]
    _ix = os.path.join(HERE, "index.html")
    _h = open(_ix, encoding="utf-8").read()
    _h2, _n = re.subn(r"const HWY_URL = 'highways\.js\?v=[^']*';", f"const HWY_URL = 'highways.js?v={_ver3}';", _h)
    if _n != 1:
        sys.exit(f"build.py: expected exactly one HWY_URL constant in index.html, found {_n}")
    if _h2 != _h:
        open(_ix, "w", encoding="utf-8").write(_h2)
    print(f"highways.js version {_ver3}")
# The optional Level 2 layer is loaded by URL from script, so the same content hash goes into
# the one constant that builds that URL.
_l2 = os.path.join(HERE, "level2.js")
if os.path.exists(_l2):
    _ver2 = hashlib.sha256(open(_l2, "rb").read()).hexdigest()[:10]
    _ix = os.path.join(HERE, "index.html")
    _h = open(_ix, encoding="utf-8").read()
    _h2, _n = re.subn(r"const L2_URL = 'level2\.js\?v=[^']*';", f"const L2_URL = 'level2.js?v={_ver2}';", _h)
    if _n != 1:
        sys.exit(f"build.py: expected exactly one L2_URL constant in index.html, found {_n}")
    if _h2 != _h:
        open(_ix, "w", encoding="utf-8").write(_h2)
    print(f"level2.js version {_ver2}")
print(f"Generated {len(urls)} pages + sitemap.xml + robots.txt (base {BASE})")
