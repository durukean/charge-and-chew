#!/usr/bin/env python3
"""Smoke-test the built site before it ships.

Run after build.py. Exits non-zero with a specific reason if anything is wrong, so the
monthly refresh workflow fails loudly instead of pushing a broken site.

    python3 verify.py
"""
import json, os, re, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
fail = []
warn = []


def check(cond, msg):
    if not cond:
        fail.append(msg)


def soft(cond, msg):
    if not cond:
        warn.append(msg)


# ---- data.js ----
p = os.path.join(HERE, "data.js")
check(os.path.exists(p), "data.js is missing")
if os.path.exists(p):
    try:
        from data_reader import load_data
        D = load_data(p)
    except Exception as e:
        fail.append(f"data.js is not valid: {e}")
        D = None
    if D:
        check(len(D.get("sites", [])) > 9000, f"only {len(D.get('sites', []))} chargers")
        check(len(D.get("brands", {})) > 60, f"only {len(D.get('brands', {}))} chains")
        check(len(D.get("matches", {})) > 6000, f"only {len(D.get('matches', {}))} matched chargers")
        check(len(D.get("cars", {})) > 20, "car database looks short")
        s0 = (D.get("sites") or [{}])[0]
        for k in ("id", "lat", "lon", "net", "kw", "conn"):
            check(k in s0, f"charger records are missing '{k}'")
        # matches must be [dLat,dLon] deltas, not the old plain metres
        mv = next(iter(next(iter(D["matches"].values())).values()), None)
        check(isinstance(mv, list) and len(mv) == 2, "match values are not [dLat,dLon] deltas")
        # coordinates inside the US
        bad = [s for s in D["sites"] if not (18 < s["lat"] < 72 and -180 < s["lon"] < -64)]
        check(not bad, f"{len(bad)} chargers have coordinates outside the US")

# ---- required files ----
for f in ["index.html", "sw.js", "manifest.json", "robots.txt", "sitemap.xml",
          "favicon.svg", "icon-192.png", "icon-512.png",
          "vendor/leaflet.js", "vendor/leaflet.css", "assets/pages.css"]:
    check(os.path.exists(os.path.join(HERE, f)), f"missing {f}")

# ---- index.html invariants that have broken before ----
if os.path.exists(os.path.join(HERE, "index.html")):
    h = open(os.path.join(HERE, "index.html")).read()
    check("unpkg.com" not in h, "index.html still loads something from unpkg (CDN dependency)")
    check(not re.search(r"[\w\)\]\s]\?\?[\s\w\(]", h),
          "index.html uses nullish ?? — blanks the app on older in-car browsers")
    # Match real optional chaining (obj?.prop / arr?.[i] / fn?.()) and not a "?." that merely
    # appears inside a regex character class like [-\\/\\\\^$*+?.()|[\\]{}].
    check(not re.search(r"[\w\)\]]\?\.[\w\(\[]", h),
          "index.html uses optional chaining ?. — blanks the app on older in-car browsers")
    check('src="data.js?v=' in h, "data.js is not cache-busted")
    check("goatcounter" in h, "analytics snippet is missing")
    for token in ["#map", "sheetTitle", "filtBtn", "themeBtn"]:
        check(token in h, f"index.html lost '{token}'")

# ---- generated pages ----
pages = glob.glob(os.path.join(HERE, "near/**/index.html"), recursive=True) + \
        glob.glob(os.path.join(HERE, "along/**/index.html"), recursive=True)
check(len(pages) > 500, f"only {len(pages)} generated pages")

sm = os.path.join(HERE, "sitemap.xml")
if os.path.exists(sm):
    locs = re.findall(r"<loc>([^<]+)</loc>", open(sm).read())
    check(len(locs) > 50, f"sitemap has only {len(locs)} URLs")
    soft(len(locs) < 2600, f"sitemap has {len(locs)} URLs — above the level real traffic has validated")
    # every sitemap URL must exist on disk and must NOT be noindex
    missing, noindexed = [], []
    for u in locs:
        rel = u.split("chargeandchew.com/", 1)[-1]
        f = os.path.join(HERE, rel, "index.html") if not rel.endswith((".xml", "/")) else \
            os.path.join(HERE, rel, "index.html")
        if rel in ("", "/"):
            f = os.path.join(HERE, "index.html")
        if not os.path.exists(f):
            missing.append(rel)
        elif "noindex" in open(f).read():
            noindexed.append(rel)
    check(not missing, f"{len(missing)} sitemap URLs have no page: {missing[:3]}")
    check(not noindexed, f"{len(noindexed)} sitemap URLs are noindexed: {noindexed[:3]}")

# ---- a sample page renders the things that matter ----
sample = os.path.join(HERE, "near", "ihop", "index.html")
if os.path.exists(sample):
    h = open(sample).read()
    check('rel="stylesheet"' in h, "generated pages lost the stylesheet link")
    check("application/ld+json" in h, "generated pages lost structured data")
    check("<h1>" in h, "generated pages lost their h1")
    check(" a IHOP" not in h, "grammar regression: 'a IHOP'")

# The basemap has a silent-failure mode: CARTO throttles by referrer and serves a
# watermark tile reading "API key required" as a valid HTTP 200 PNG, so no request errors
# and the entire map becomes that message. Guard the probe and its fallback.
_html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
# match the actual call site at boot, not just the identifier — a commented-out call
# still contains the name, which an earlier version of this check happily accepted
# "supercharger near chase bank" flew the map to Dallas: every hit was a different Chase
# branch and the Dallas one won only because OSM tagged that building class=place, which
# scoreHit rewards. Guard the detector that stops a brand being treated as a place.
# match the CALL, not the identifier: the definition alone would satisfy a name check
# even with the call removed (the same trap the basemap guard fell into first time)
check(re.search(r"if \(looksLikeChainBrand\(", _html) is not None,
      "chain-brand detector is never called — an untracked brand would again anchor the "
      "map on an arbitrary branch")
check("unsupportedChain" in _html, "unsupported-brand error path gone")
# Live POI search: arbitrary categories/brands are queried from OSM scoped to the current
# area, because precomputing them would add ~1.6 MB for +400 brands.
check(re.search(r"runLivePoi\(", _html) is not None, "live POI search is never called")
check("POI_TAGS" in _html and "detectPoiIntent" in _html, "live POI category mapping gone")
check("clearLivePoi()" in _html, "live POI results would leak across areas")
# /near/<chain>/<state>/ promises a statewide count; a radius around the state centroid
# silently delivered a fraction of it (Texas: 83 promised, 11 shown).
check("stateScope" in _html, "state scope gone — /near/<chain>/<state>/ links would under-deliver")
# The install offer must stay gated: never on the first visit, never after a dismissal,
# never when already installed. An ungated prompt is worse than no prompt.
check("visits < 2" in _html, "install prompt is no longer gated to returning visitors")
check("installSnoozed" in _html, "install dismissal is no longer remembered")
check("deliveredValue" in _html, "install prompt no longer waits until the app is useful")
# The live lookup is the app's most distinctive feature and is invisible without examples.
check("SUGGESTIONS" in _html, "search examples gone — live lookup becomes undiscoverable again")
# Dwell advice must stay chain-aware: the generic version claimed "sit-down meal" when the
# only thing within a walk was a coffee shop.
check("dwellAdvice" in _html and "CHAIN_DWELL" in _html, "chain-aware dwell advice gone")
check("DWELL_MIN[o.kind] + o.walk * 2" in _html,
      "dwell advice no longer counts the walk BOTH ways — it would recommend unreachable stops")
# Chain rows carry the POI's own coordinates, so walking directions need no lookup.
check("chainDetail" in _html, "tap-a-chain lookup gone")
check("travelmode=walking" in _html, "per-chain walking directions gone")
# The place-card URL form must survive: ?api=1&query= lands on a results list instead.
# /maps/place/ renders an empty panel and ?api=1&query= resolves by text to the wrong
# city; only the viewport-scoped search form lands on the right branch.
check("/maps/search/" in _html and "/@" in _html,
      "Google place links are not the viewport-scoped form — they will resolve to the wrong branch")
# match the URL being BUILT, not the word appearing in a comment explaining why not to
check("google.com/maps/place/" not in _html,
      "reverted to the /maps/place/ URL, which renders an empty panel")
# Per-chain social cards: a page may reference og/<slug>.png only if it was rendered,
# otherwise every share of that page shows a broken image.
import glob as _glob
_miss = set()
for _p in _glob.glob(os.path.join(HERE, "near", "**", "index.html"), recursive=True):
    _m = re.search(r'og:image" content="[^"]*/og/([^"]+)\.png"', open(_p, encoding="utf-8").read())
    if _m and not os.path.exists(os.path.join(HERE, "og", _m.group(1) + ".png")):
        _miss.add(_m.group(1))
check(not _miss, f"pages reference social cards that do not exist: {sorted(_miss)[:5]}")

# ---- "Any food" / "Any store" category filter ----
# One predicate feeds passesChain, bestWalk and countWithoutNarrowing. If they drift apart,
# a stop can pass the filter but sort as if it had no match, or the empty state can blame
# the wrong thing.
for _needle, _why in [
    ("let anyCat = null", "the any-category filter state is gone"),
    ("const chainQuery = ()", "chainQuery helper gone — the three filter paths would drift"),
    ("const chainKeysOn =", "chainKeysOn helper gone"),
    ('data-cat="${c}"', "the Any food / Any store chips are gone"),
    ("CAT_LABEL", "category chip labels gone"),
]:
    check(_needle in _html, _why)
check(_html.count("if (!chainQuery()) return true;") == 1
      and "return chainKeysOn(m).length > 0;" in _html,
      "passesChain no longer routes through the shared chain predicate")
check("const keys = chainQuery() ? chainKeysOn(m) : Object.keys(m);" in _html,
      "bestWalk ignores the category filter — sorting would use an unmatched chain's distance")
check("anyCat ? p.set('any', anyCat)" in _html and "q.get('any')" in _html,
      "the category filter is not shareable — a ?any= link would open unfiltered")
# The trigger words must be stripped from the place text. "hungry in denver" geocoding
# "hungry denver" is the exact bug class that used to teleport the map to another state.
# Category and brand replace each other. Without this, tapping a brand while a category was
# on OR-ed them and the result count went UP -- a tap that reads as narrowing must not widen.
check(_html.count("if (active.has(k)) { anyCat = null; track('chain', k); }") == 2,
      "picking a chain no longer clears the category filter — the count would grow on a narrowing tap")
check("if (anyCat) { active.clear(); track('anycat', anyCat); }" in _html,
      "picking a category no longer clears the chain selection")
for _w in ("'meal'", "'hungry'", "'shopping'"):
    check(_w in _html, f"category trigger word {_w} is not in NON_PLACE — it would be geocoded")

# ---- trip pages ----
_trips = os.path.join(HERE, "data", "trips.json")
check(os.path.exists(_trips), "data/trips.json is missing — make_trips.py has not been run")
if os.path.exists(_trips):
    _tj = json.load(open(_trips))
    _dirs = [d for d in os.listdir(os.path.join(HERE, "trip"))
             if os.path.isdir(os.path.join(HERE, "trip", d))] if os.path.isdir(os.path.join(HERE, "trip")) else []
    check(len(_dirs) >= len(_tj) - 2,
          f"only {len(_dirs)} trip pages for {len(_tj)} cached routes")
    _sm = open(os.path.join(HERE, "sitemap.xml"), encoding="utf-8").read()
    check(_sm.count("/trip/") >= len(_dirs), "trip pages are missing from the sitemap")
    _lv = os.path.join(HERE, "trip", "los-angeles-to-las-vegas", "index.html")
    check(os.path.exists(_lv), "the LA to Las Vegas trip page is gone")
    if os.path.exists(_lv):
        _t = open(_lv, encoding="utf-8").read()
        # The CTA is the whole point of the page: it must land on the app already routed
        # and already filtered to food, or the page is just a list.
        check("any=food" in _t and "from=Los%20Angeles" in _t and "to=Las%20Vegas" in _t,
              "the trip CTA no longer opens the map on that route with food selected")
        check("mile " in _t, "the break-the-drive table lost its route mileage")
        # Distance, not point index. OSRM emits geometry far denser in cities, and indexing
        # by point put the first suggested stop 30 miles into a 270-mile drive.
        _m = [int(x) for x in re.findall(r"<b>mile (\d+)</b>", _t)]
        check(_m and _m[0] > 45,
              f"first suggested stop is at mile {_m[0] if _m else '?'} — sampling is skewed to the origin city")
    for _short in ("orlando-to-tampa", "denver-to-colorado-springs"):
        _f = os.path.join(HERE, "trip", _short, "index.html")
        if os.path.exists(_f):
            check("Good places to break" not in open(_f, encoding="utf-8").read(),
                  f"{_short} is under 130 miles and should not suggest a mid-drive charging stop")
check("trip/los-angeles-to-las-vegas/" in _html, "the app no longer links to any trip page")
check("tire shop" in _html, "the live-category example is gone from the suggestions")
check("if (stateScope) return s.st === stateScope;" in _html, "state scope is not applied in inScope")
check(re.search(r"^\s*probeBasemap\(\)\s*;", _html, re.M) is not None,
      "basemap selection is never called — the map would have no tile layer")
# CARTO stamps "API KEY REQUIRED" into a normal, full-size tile, so it cannot be detected
# by status code or byte length. Esri must stay the default for the unauthenticated site.
check("basePref === 'auto' ? 'esri'" in _html,
      "default basemap is no longer Esri — CARTO watermarks every tile without an API key")
for _needle, _why in [
    ("function probeBasemap", "basemap selection gone"),
    ("BASEMAPS", "basemap table gone"),
    ("maxNativeZoom", "Esri fallback would go blank past z16 without maxNativeZoom"),
    ("World_Light_Gray_Reference", "Esri fallback lost its label layer"),
]:
    check(_needle in _html, _why)

print(f"checked data.js, {len(pages)} pages, sitemap, assets")
for w in warn:
    print(f"  WARN  {w}")
if fail:
    print("\nFAILED:")
    for f in fail:
        print(f"  ✗ {f}")
    sys.exit(1)
print("all checks passed")
