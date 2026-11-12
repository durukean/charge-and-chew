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
        # price is rendered into innerHTML. It is safe only because data/fetch_chargers.py
        # normalises AFDC's free-text pricing to an enum -- a coupling across two files, so
        # pin the enum here as well as escaping at the render site.
        _pv = {s.get("price", "") for s in D["sites"]}
        check(_pv <= {"free", "paid", ""},
              f"site.price holds values outside the enum ('free'|'paid'|''): {sorted(_pv - {'free','paid',''})[:3]}")
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
    # The ?v= must be the hash of the data itself. The service worker serves data.js cache-first
    # by URL, so a stale ?v= means returning visitors never see new data -- which is exactly
    # what happened for months while it was a hand-edited "?v=9" the refresh never touched.
    import hashlib
    _want = hashlib.sha256(open(os.path.join(HERE, "data.js"), "rb").read()).hexdigest()[:10]
    _got = re.search(r'src="data\.js\?v=([^"]*)"', h)
    check(_got is not None and _got.group(1) == _want,
          f"index.html loads data.js?v={_got.group(1) if _got else '?'} but the data hashes to {_want} "
          "— returning visitors would keep a stale cached dataset (run build.py)")
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
    _lm = re.findall(r"<lastmod>(\d{4}-\d{2}-\d{2})</lastmod>", open(sm).read())
    check(len(_lm) >= len(locs) - 2, f"sitemap dates only {len(_lm)} of {len(locs)} URLs")
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

# Structured data is quoted verbatim by search engines and AI tools: plain text only, and
# the network named once. 527 pages showed "Arby&#x27;s"; ~10,000 entries read
# "Tesla Supercharger — Woodburn, OR - Tesla Supercharger".
_ld_bad, _ld_dbl, _no_banner = [], 0, []
for _p in pages + glob.glob(os.path.join(HERE, "trip/**/index.html"), recursive=True):
    _h = open(_p, encoding="utf-8").read()
    if 'name="apple-itunes-app"' not in _h:
        _no_banner.append(os.path.relpath(_p, HERE))
    for _m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', _h, re.S):
        if re.search(r"&#x27;|&#39;|&amp;|&quot;", _m.group(1)):
            _ld_bad.append(os.path.relpath(_p, HERE))
        _ld_dbl += len(re.findall(r'"name": "Tesla Supercharger \u2014 [^"]*Tesla Supercharger', _m.group(1)))
check(not _ld_bad, f"{len(_ld_bad)} pages have HTML escapes inside JSON-LD, e.g. {_ld_bad[:2]}")
check(_ld_dbl == 0, f"{_ld_dbl} JSON-LD place names repeat the network")
check(not _no_banner, f"{len(_no_banner)} generated pages lack the Smart App Banner, e.g. {_no_banner[:2]}")
_bp = open(os.path.join(HERE, "build.py")).read()
check(re.search(r"(?m)^\s*WRITTEN\.add\(os\.path\.normpath\(full\)\)", _bp)
      and re.search(r"(?m)^\s*os\.remove\(_full\)", _bp),
      "build.py no longer retires pages it stopped generating — they live on with stale data")
_priv = open(os.path.join(HERE, "privacy", "index.html"), encoding="utf-8").read()
check("Google Fonts" in _priv and "CARTO" in _priv and "It stays on your device" not in _priv,
      "privacy policy no longer discloses Google Fonts / CARTO, or claims location stays on the device")

# The basemap has a silent-failure mode: CARTO throttles by referrer and serves a
# watermark tile reading "API key required" as a valid HTTP 200 PNG, so no request errors
# and the entire map becomes that message. Guard the probe and its fallback.
_html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
check('name="apple-itunes-app" content="app-id=6809134093"' in _html, "home page lost the Smart App Banner")
check(re.search(r'<meta name="viewport" content="[^"]*user-scalable=no', _html) is None,
      "pinch-zoom is blocked on the website again (WCAG 1.4.4); lock it only inside the app")
check("Find Tesla Superchargers" not in _html, "home page metadata says Tesla-only again")
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
# ---- Overpass: one request at a time ----
# Measured, not assumed: firing five requests at once produced four HTTP 429s and one
# success. The limit is CONCURRENT REQUESTS PER IP, not query size, and a 429 takes ~8 s
# to come back. The app overlaps its own calls easily (a second search while the first
# runs, a chain-row tap during a category lookup, a shared link that rebuilds a route and
# a lookup together), so every call is serialised through one queue.
check("function overpassQueued" in _html, "Overpass calls are no longer serialised — "
      "the app would 429 itself the moment two lookups overlap")
check("return overpassQueued(" in _html, "overpassFetch bypasses the queue")
check("overpassChain = run.then(() => {}, () => {})" in _html,
      "a failed Overpass call would poison the queue and stall every later lookup")
# Answers are cached for a week so a reload, a retry or a shared link costs nothing.
# Check the CALL SITES, not the definitions: renaming the function away left the first
# version of this check passing happily.
check(re.search(r"poiCache\.set\(body, els\); poiStore\(body, els\);", _html) is not None,
      "successful Overpass answers are no longer written to the persistent cache — every "
      "reload would re-ask a free community server")
check(re.search(r"poiCache\.get\(body\) \|\| poiStored\(body\)", _html) is not None,
      "the persistent Overpass cache is never read")
check("POI_TTL" in _html, "cached Overpass answers would never expire")
check("const trimEls" in _html,
      "cached and fresh Overpass answers would have different shapes")
# Retry must back off and honour Retry-After; an instant retry at a 429 always fails again.
check("e.retryAfter = parseInt(r.headers.get('retry-after')" in _html,
      "Overpass Retry-After is ignored — retries would hammer a server that asked us to wait")
check("OVERPASS_DEADLINE" in _html,
      "the Overpass retry loop has no deadline — a user could wait 90 s with no feedback")
# A queue turns one hung request into a permanent stall, which the unqueued code could not
# do: fetchTimeout cannot cancel on a browser with no AbortController. Cap every turn.
check("overpass queue timeout" in _html,
      "a hung Overpass request would deadlock the queue for the life of the page")
# Serialising means a superseded search comes back AFTER the newer one and would paint its
# stale results over what the user is actually looking at.
check("livePoiGen" in _html and _html.count("gen !== livePoiGen") >= 2,
      "a superseded live lookup can overwrite the newer search's results")
# A cache-key collision would serve a different query's answer with total confidence.
check("const poiSig" in _html and "v.s !== poiSig(body)" in _html,
      "cached Overpass answers are not verified against the query that asked for them")
# ---- a long route cannot be one Overpass request ----
# Measured with BOTH slots free, so this is not the concurrency limit: 300 `around:`
# centres in one query returns HTTP 504 after 11 s, while 100 centres returns 200 in 11 s.
# The query itself is too expensive, so route lookups are thinned and chunked.
# Check the CALL, not the definition. The definition-only form of this check passed
# happily with the call removed -- the second time that mistake was made in this file.
check(re.search(r"thinCentres\(inScope, D\.walkM\)", _html) is not None,
      "route lookups no longer dedupe their circles — a clustered corridor would ask "
      "Overpass the same question dozens of times")
check("LIVE_CHUNK" in _html and re.search(r"i \+= LIVE_CHUNK", _html) is not None,
      "route lookups are sent as one giant query again — Overpass answers that with a 504")
_lc = re.search(r"const LIVE_CHUNK = (\d+)", _html)
check(_lc is not None and int(_lc.group(1)) <= 150,
      "the Overpass chunk size is above what the server actually answers (measured: 100 ok, "
      "300 times out)")
# ---- bundled-chain fallback for a failed live lookup ----
# The live lookup leans on a free community server that genuinely refuses sometimes. For
# most categories we are not empty handed: 90 chains ship with the app. Every key in
# CAT_CHAINS must exist in data.js -- a typo would silently match nothing and the fallback
# would appear to work while doing nothing at all.
check("const CAT_CHAINS" in _html, "the bundled-chain fallback is gone — a busy OSM would "
      "again mean a dead-end error panel")
check(re.search(r"const seed = seedChains\(intent\)", _html) is not None,
      "seedChains is never called on the failure path")
# The fallback must prove it has something IN SCOPE before offering itself. "ice cream"
# near downtown LA maps to Dairy Queen, of which there are none for miles, and
# "0 stops near Dairy Queen" reads as a result while being worse than admitting failure.
# A name filter ("blue bottle coffee") means a specific place was wanted: the bundled chains
# must not stand in for it, or a busy OSM answers with Starbucks for Blue Bottle.
check("if (!intent || intent.brandOnly || !intent.tags || intent.name) return [];" in _html,
      "the bundled-chain fallback answers a NAMED search ('blue bottle coffee') with unrelated chains")
check("MATCH[sc.id][k] !== undefined" in _html,
      "the bundled-chain fallback no longer checks it has any stops in scope — it would "
      "answer '0 stops near <chain>' and look like a result")
if "D" in dir() and D:
    _i = _html.find("const CAT_CHAINS = {")
    if _i >= 0:
        _j, _d = _html.index("{", _i), 0
        for _k in range(_j, len(_html)):
            if _html[_k] == "{": _d += 1
            elif _html[_k] == "}":
                _d -= 1
                if _d == 0: break
        _body = _html[_j:_k]
        # names are single- OR double-quoted in the JS (apostrophes force double), and
        # OSM key=value tags share the object -- keep only the values that are names.
        _tok = re.findall(r"'((?:[^'\\\\]|\\\\.)*)'|\"([^\"]*)\"", _body)
        _chains = set()
        for _a, _b in _tok:
            _v = (_a or _b).replace("\\'", "'")
            if _v and "=" not in _v and not _v.strip().startswith(","):
                _chains.add(_v)
        _known = set(D.get("brands", {}))
        _bad = sorted(c for c in _chains if c not in _known)
        check(not _bad, "CAT_CHAINS names chains that are not in data.js (the fallback "
                        "would silently find nothing): %s" % _bad[:5])
        check(len(_chains) > 40, "CAT_CHAINS only maps %d chains — the fallback covers far "
                                 "less than it should" % len(_chains))

check("const seenPoi = new Set()" in _html,
      "chunked route results are not deduped — shops at the chunk seams would be "
      "double-counted in the number shown to the user")
# There is no usable mirror. overpass.osm.ch answers HTTP 200 with an EMPTY element list
# for US queries because it carries a Switzerland-only extract -- as a fallback it would
# report "no ice cream shops on your route" with complete confidence.
check("osm.ch" not in _html.split("const OVERPASS =")[-1][:400] or
      "Switzerland-only" in _html,
      "a region-limited Overpass mirror was added — it returns 200 with zero results for "
      "the US and would silently report 'nothing found'")
check("POI_TAGS" in _html and "detectPoiIntent" in _html, "live POI category mapping gone")
check("clearLivePoi()" in _html, "live POI results would leak across areas")
# /near/<chain>/<state>/ promises a statewide count; a radius around the state centroid
# silently delivered a fraction of it (Texas: 83 promised, 11 shown).
_zm = re.search(r"getPane\('routePane'\)\.style\.zIndex = (\d+)", _html)
check(_zm is not None and int(_zm.group(1)) < 400,
      "the route pane is no longer below the overlay pane (400) that holds the charger "
      "canvas — the line would paint over every dot on the corridor again")
check("getPane('routePane').style.pointerEvents = 'none'" in _html,
      "the route pane accepts pointer events again — taps on chargers under the line would "
      "hit the line instead")
# ---- taps, the stop card, and where a visit starts (2026-10-16) ----
# Dots a few px wide with zero tap tolerance: most taps on a phone hit the map instead.
_tol = re.search(r"L\.canvas\(\{[^}]*tolerance: TOUCH \? (\d+) : (\d+)", _html)
check(_tol is not None and int(_tol.group(1)) >= 10 and int(_tol.group(2)) >= 4,
      "charger dots lost their tap tolerance — taps beside a dot miss it again")
# The card opens short: details stay behind More.
check('<div class="pp-more" hidden>' in _html and "data-more" in _html,
      "the stop card opens with every detail at once again (no collapsed More section)")
# A plain visit opens where you are.
check(re.search(r"(?m)^  startFromLocation\(restored\);", _html) is not None,
      "a plain visit no longer starts from the visitor's location")
# Two marks on the map, not a colour per network: Tesla's T disc and one green for the rest.
check(re.search(r"markOf\(s\) \? new MarkMarker\(", _html) is not None
      and "'Tesla Supercharger': { bg: '#e31937'" in _html and "ctx.fill(mk.p2d" in _html,
      "network marks are gone from the map (Tesla's red T and the other networks' marks)")
# Car mode (the Tesla browser): detected from the user agent, and it switches on the touch and
# reduced-motion rules whatever pointer the car reports.
check(re.search(r"/\\bTesla\\/\|QtCarBrowser/\.test\(navigator\.userAgent\)", _html) is not None
      and "r.media.mediaText = 'all'" in _html,
      "car mode is gone — the Tesla browser gets desktop-sized controls again")
# A typed search drops what the previous search set and this one doesn't name ("chargers in
# sf" after "starbucks" kept Starbucks); anything changed by hand since is kept.
check(re.search(r"if \(!p\.chains\.length && !p\.anyCat && q0\.chains && chainSig\(\) === q0\.chains\) \{ active\.clear\(\);", _html) is not None
      and "lastQuerySet = {" in _html,
      "a new search silently keeps the previous search's chain/plug filters again")
# Route stops lead with their mile marker along the drive, not a list index.
check("const mileAt = new Map();" in _html and 'class="idx mi"' in _html,
      "route rows lost their mile markers")
# A route says where its longest charger gap is (geography, never a charging plan).
# On a drive with a breaks card the gap is a row in it, at its mile (2026-11-10); otherwise a note.
check("$('list').innerHTML = (bc || gapNote()) + head + rows.map(" in _html and "function gapNote()" in _html
      and "const gap = chargerGap();" in _html[_html.index("function breaksCard("):_html.index("function gapNote()")]
      and 'class="brk gap" role="note"' in _html,
      "route lists no longer flag the longest stretch without a fast charger")
# Long routes open with suggested breaks (driver breaks near each ~2 h mark, not a charging plan).
check("const bc = breaksCard(vis);" in _html and "function breakPicks(vis)" in _html,
      "long routes no longer suggest where to break the drive")
# The stop card says which of its places are open, in one cached lookup per stop.
check(re.search(r"(?m)^  if \(el\) fillHours\(el[,)]", _html) is not None and "async function fillHours(el" in _html,
      "the stop card no longer shows whether its places are open")
# The delayed national fit at boot must not override a location that arrived first.
check("setTimeout(() => { if (!center && !route) fitUS(); }, 460)" in _html,
      "the boot-time US fit can override the visitor's location again (map on the whole US, list local)")
# Ice cream is precomputed (instant, no live lookup) and a placeless search looks where you
# are, not at an area restored from an earlier visit ("ice cream" landed in another state).
check(D.get("brands", {}).get("Ice cream shop", {}).get("n", 0) > 5000 if isinstance(D, dict) else True,
      "the precomputed ice cream category is missing or nearly empty in data.js")
check("'ice cream': 'Ice cream shop'" in _html and "'icea cream': 'Ice cream shop'" in _html,
      "searches for ice cream (and its misspellings) no longer resolve to the precomputed category")
check(re.search(r"(?m)^\s*center\.restored = true;", _html) is not None and re.search(r"if \(center && center\.restored\) \{", _html) is not None,
      "a search with no place uses an area restored from a previous visit again (the 'other state' bug)")
check("locate('center', hp ? { thenPoi: hp } : {});" in _html,
      "'<category> near me' forgets the category again")
# The static pages mirror the app's rows: network marks read from index.html (one source).
_ih = open(os.path.join(HERE, "near", "in-n-out", "ca", "index.html"), encoding="utf-8").read() if os.path.exists(os.path.join(HERE, "near", "in-n-out", "ca", "index.html")) else ""
check(not _ih or ('class="nm"' in _ih and 'class="ring"' not in _ih),
      "static chain pages lost the network marks (or brought back the old walk-time ring)")
# Food words resolve to the chains that serve them, before any live lookup ("tacos" was
# every fast-food chain).
check(re.search(r"for \(const \[re, keys\] of FOOD_GROUPS\)", _html) is not None and "'Taco Bell', 'Del Taco', 'Chipotle'" in _html,
      "food words (tacos, pizza, burgers...) no longer map to their chains")
# ---- speed badges in dark mode ----
# The plain dark-theme badge rule (0,4,1) outranked the tier colours (0,3,1): every 250 kW+
# stop showed near-black text on dark grey. Each tier rule must be at least as specific.
_dk = re.search(r':root\[data-theme="dark"\] \.row s\.spd\{', _html)
for _t in ("ultra", "fast", "slow"):
    check(_dk is None or re.search(r"(?m)^:root \.row s\.spd\." + _t + r"\{", _html) is not None,
          f"the .{_t} speed badge rule is less specific than the dark-theme badge rule again — "
          "unreadable badges in dark mode")
# ---- the route card can never be hidden while a route is on screen ----
# Closing the editor used to hide the card, leaving the line on the map with no x to clear it.
check(re.search(r"\$\('routeToggle'\)\.onclick = \(\) => \{[^}]*?if \(route\) \{", _html, re.S) is not None
      and "showRouteSummary();" in _html,
      "closing the route editor can hide the route card again (no way to clear the route)")
# ---- chip counts must describe the CURRENT scope ----
# With a route on screen the chips advertised the national figure: "Any food 10,458" and
# then 210 results. A number the app cannot honour is the same class of bug as a
# confidently wrong destination.
check("function ensureScopeCounts" in _html and "ensureScopeCounts();" in _html,
      "chip counts are no longer rescoped — a route would advertise national totals")
check(re.search(r"\$\{chipCatCount\(c\)", _html) is not None
      and re.search(r"\$\{chipCount\(k\)\}", _html) is not None,
      "renderChips reads the national counts directly again")
# A live POI lookup writes new keys into MATCH without the scope changing, so the memo has
# to be invalidated explicitly or the new chip shows 0.
# Match the live STATEMENT, not the substring: "// matchVer++;" satisfied the first
# version of this check. Third time that mistake has been made in this file — a guard
# that a commented-out line still passes is not a guard.
check(len(re.findall(r"(?m)^\s*matchVer\+\+;", _html)) >= 2,
      "the scoped-count memo is not invalidated when a live lookup changes MATCH — the new "
      "chip would show 0")
# ---- the other two free services on the critical path ----
# Nominatim and OSRM were uncached: every shared trip link re-asked both for an answer that
# cannot have changed, and an outage in either killed route planning outright. Verified by
# blocking both and re-planning the same trip entirely from cache.
check("function lsGet" in _html and "function lsPut" in _html,
      "the geocode/route cache is gone — a shared trip would re-ask two public services")
check(re.search(r"lsGet\(GEO_NS, gk, GEO_TTL\)", _html) is not None
      and re.search(r"lsPut\(GEO_NS, [^;]*\bgk\b[^;]*, hit, GEO_CAP\)", _html) is not None,
      "geocoding is no longer cached")
check(re.search(r"lsGet\(RTE_NS, rk, RTE_TTL\)", _html) is not None
      and re.search(r"lsPut\(RTE_NS, rk, trip, RTE_CAP\)", _html) is not None,
      "route geometry is no longer cached — an OSRM outage would kill a route already planned")
# Caching a failure would stick: the lsPut must sit after every validation, so only a
# resolved place is ever stored.
_gi, _gp = _html.find("const gk = q.trim()"), _html.find("lsPut(GEO_NS, ")
check(_gi > 0 and _gp > _html.find("if (looksLikeChainBrand(", _gi),
      "the geocode cache is written before validation — a bad hit would be cached")
# Route entries are ~50 kB; the namespace has to be bounded.
check(re.search(r"RTE_CAP = \d+", _html) is not None and "if (cap) {" in _html,
      "the route cache is unbounded — 50 kB an entry would fill localStorage")

# ---- sheet title stays a sentence ----
# The fallback activates five chains for one search ("coffee"); listing them all gave a
# title that truncated to mush on a phone. Name the question when the set is the seed's,
# and cap any hand-picked list past three.
check("isSeed ? esc(seedFor.icon + ' ' + seedFor.label)" in _html,
      "the fallback title lists every bundled chain again instead of naming the search")
check("parts.length > 3 ?" in _html, "long chain selections are no longer capped in the title")
# seedFor is read by renderList ~1,400 lines above where the fallback sets it. A `let`
# declared down there and read during boot is a TDZ error that blanks the app.
_sf, _rl = _html.find("let seedFor = null;"), _html.find("function renderList(")
check(0 < _sf < _rl, "seedFor is declared after renderList, which reads it — a TDZ error "
      "at boot would blank the whole app")

# ---- boot and render performance (measured, not assumed) ----
# Boot rendered THREE times: applyTheme() rendered, probeBasemap() called applyTheme() again
# (tearing down the tile layer it had just built and re-fetching tiles), and only then was the
# URL applied and the one render that mattered run. ~800 ms -> 174 ms once fixed.
check("if (!booting) render();" in _html,
      "applyTheme renders during boot again — boot would render three times")
check(re.search(r"(?m)^booting = false;\nrender\(\);", _html) is not None,
      "boot never clears the booting flag before its single render")
_boot = _html[_html.find("/* ───────── boot ───────── */"):][:600]
check(not re.search(r"(?m)^applyTheme\(\);\s*$", _boot),
      "boot calls applyTheme() before probeBasemap() again — it builds a tile layer that is "
      "torn down a moment later and re-downloads its tiles")
# The default sort called bestWalk() -- a haversine per chain -- inside the comparator:
# ~380,000 calls to sort 13,798 stops. 175 ms -> 18 ms; ordering proven identical.
check("function sortByKey" in _html and "sortByKey(out, s => bestWalk(s))" in _html,
      "visibleSites sorts with a computed comparator again (~380k haversines per render)")
_vs = _html[_html.find("function visibleSites()"):][:900]
check("out.sort((a, b) => bestWalk" not in _vs,
      "bestWalk() is back inside a sort comparator")
# Reading a layout property right after the list is rewritten forces a whole-page layout.
check("const chipScroll = $('chiprow').scrollLeft;" in _html and "renderChips(chipScroll)" in _html,
      "render no longer reads the chip scroll before dirtying the DOM — each tap forces a "
      "synchronous whole-page layout again (measured 35 ms)")
check("render(); renderChips();" not in _html,
      "chips are drawn twice again after render() — which already draws them")

# ---- security: untrusted strings reaching the DOM ----
# toast() writes textContent, so its text is inherently safe and must NOT be esc()'d: six
# call sites did, and users read "Searching Barnes &amp; Noble". Both halves are pinned --
# if toast ever became innerHTML, un-escaped callers would make OSM names an XSS vector.
_tb = _html[_html.find("function toast(msg) {"):][:400]
check("t.textContent = msg" in _tb and "innerHTML" not in _tb,
      "toast() no longer uses textContent — its callers pass un-escaped OSM text")
_toasts = []
for _m in re.finditer(r"\btoast\(", _html):
    _i, _d = _m.end(), 1
    _j = _i
    while _j < len(_html) and _d:
        _d += {"(": 1, ")": -1}.get(_html[_j], 0); _j += 1
    if "esc(" in _html[_i:_j]: _toasts.append(_html.count("\n", 0, _m.start()) + 1)
check(not _toasts, "toast() text is esc()'d again — users would see literal &amp; (lines %s)" % _toasts[:5])
# ---- stale answers and leftover state (audit 2026-10-07; each reproduced before the fix) ----
_toastfn = _html[_html.find("function toast(msg) {"):][:900]
check("t.style.pointerEvents = ''; t.onclick = null;" in _toastfn,
      "toast() no longer resets the update prompt's tap handler — an invisible reload button over the list")
check(re.search(r"const g = await geocode\(spName && spTown \? `\$\{spName\}, \$\{spTown\}` : p\.place\);\n\s*if \(myNav !== navGen\) return;", _html) is not None,
      "a slow place search can overwrite a newer one again (Austin answering after Denver)")
_rr = _html[_html.find("async function runRoute(opts)"):_html.find("function applyCorridor(")]
check(_rr.count("if (stale()) return;") >= 2 and "finally { $('goBtn').disabled = false; }" in _rr,
      "a late route can wipe a newer search again, or leave the Go button disabled")
for _fn in ("function setCenter(", "function clearCenter("):
    _b = _html[_html.find(_fn):][:400]
    check("navGen++; livePoiGen++;" in _b, f"{_fn.split('(')[0][9:]} no longer cancels lookups still running for the old area")
check(re.search(r"(?m)^let livePoiGen = 0;", _html) and _html.find("let livePoiGen = 0;") < _html.find("function setCenter("),
      "livePoiGen is declared after setCenter — a boot-time setCenter would hit the TDZ")
check("if (det.isConnected) det.outerHTML = poiDetailHtml(p);" in _html and
      "row.nextElementSibling.outerHTML" not in _html,
      "a late chain-detail answer can overwrite the NEXT chain's row again")
check("e.target.closest('.leaflet-popup, .leaflet-control')" in _html,
      "press-and-hold inside a popup drops a pin again")
_rv = _html[_html.find("async function reverseName("):][:900]
check("center === asked" in _rv and "toFixed(2)" in _rv,
      "reverseName sends exact coordinates again, or names a newer pin with an older answer")
check("throw new Error(busyMsg('Place search', r.status)); }" in _html
      and "if (!r.ok) throw new Error(busyMsg('Route planning', r.status));" in _html,
      "a rate-limited geocode or route shows a raw JSON parse error again")
_te = _html[_html.find("function onTileError()"):][:400]
check("!navigator.onLine" in _te and "setTimeout(" in _te,
      "bad signal can switch the map to watermarked CARTO tiles for the rest of the session again")
# An OSM website= tag is free text anyone can edit; esc() leaves javascript: URLs intact.
# safeUrl is an allow-list (output always starts with http or is empty), which is what makes
# it immune to "java<TAB>script:" -- mutation-tested: removing the whitespace strip does NOT
# reopen it, and that is correct. What must never happen is widening the allowed schemes.
check(len(re.findall(r'href="\$\{esc\(safeUrl\((?:P|p)\.site\)\)\}"', _html)) == 2
      and "href=\"${esc(P.site)}\"" not in _html and "href=\"${esc(p.site)}\"" not in _html,
      "an OSM website= value reaches an href without safeUrl() — javascript: URLs survive esc()")
# Run the REAL function against real payloads, not a re-implementation of it.
import shutil, subprocess
_node = shutil.which("node")
if _node and "function safeUrl(u)" in _html:
    _fn = _html[_html.index("function safeUrl(u)"):_html.index("/* textContent, deliberately")]
    _js = _fn + r"""
const bad=["javascript:alert(1)","JavaScript:alert(1)","  javascript:alert(1)","java\tscript:alert(1)",
 "java\nscript:alert(1)","javascript\r:alert(1)","\u0000javascript:alert(1)",
 "data:text/html,<script>alert(1)</script>","vbscript:msgbox(1)","JaVaScRiPt:alert`1`","//evil.com/x"];
const good=[["https://a.com","https://a.com"],["www.b.com","https://www.b.com"],["c.com/m","https://c.com/m"]];
const f=[];
for(const b of bad){const r=safeUrl(b);if(r&&/^(javascript|data|vbscript):/i.test(r.replace(/\s/g,""))||r.startsWith("//"))f.push("LET THROUGH "+JSON.stringify(b));}
for(const [i,w] of good){if(safeUrl(i)!==w)f.push("BROKE "+i+" -> "+safeUrl(i));}
console.log(f.length?f.join("\n"):"OK");"""
    _r = subprocess.run([_node, "-e", _js], capture_output=True, text=True)
    check(_r.stdout.strip() == "OK", "safeUrl() fails its attack battery:\n  " + (_r.stdout + _r.stderr).strip()[:400])

# The typo-tolerant chain match must never swallow a town we have chargers in. No town in
# today's data is one edit from a brand, so the search suite cannot exercise this guard; run
# the REAL functions against a synthetic town instead.
if _node and "function chainTypo(word)" in _html:
    _a = _html.index("function oneEdit(a, b)")
    _fn = _html[_a:_html.index("\n}\n", _html.index("function chainTypo(word)")) + 3]
    _js = """const normalise=t=>String(t).toLowerCase();
const CHAIN_SQUASH=new Map([["chipotle","Chipotle"],["walmart","Walmart"]]);
let SITES=[{city:"Chipolte"}];
""" + _fn + """
const f=[];
if(chainTypo("chipolte")!==null)f.push("town 'Chipolte' became a chain");
if(chainTypo("walmarts")!=="Walmart")f.push("walmarts -> "+chainTypo("walmarts"));
if(chainTypo("walmrt")!==null)f.push("6-letter word matched");
console.log(f.length?f.join("\\n"):"OK");"""
    _r = subprocess.run([_node, "-e", _js], capture_output=True, text=True)
    check(_r.stdout.strip() == "OK", "chainTypo() fails its battery:\n  " + (_r.stdout + _r.stderr).strip()[:400])

# ---- iOS: the downloaded data overlay must never beat a newer bundle ----
# Every reader (web view, native store, Siri) prefers the overlay unconditionally. Without a
# prune, an app update shipping NEWER data kept losing to a stale download for good, and paired
# the update's new index.html with old-format data.js. Proven on the simulator: stale dropped,
# newer kept, a tie goes to the bundle.
_swf = lambda f: open(os.path.join(HERE, "ios", "ChargeAndChew", f)).read() \
    if os.path.exists(os.path.join(HERE, "ios", "ChargeAndChew", f)) else ""
# Distinct names: `_ai` is already a PATH further up this file.
_ov_ad, _ov_ai = _swf("AppDelegate.swift"), _swf("AppIntents.swift")
_ov_du, _ov_wv = _swf("DataUpdater.swift"), _swf("WebViewController.swift")
# LIVE statements only -- a commented-out "//DataUpdater.pruneStaleOverlay(" still contains the
# name, and a substring check passed against it. Fourth time that mistake was made here.
_LIVE_PRUNE = re.compile(r"(?m)^\s*DataUpdater\.pruneStaleOverlay\(")
_LIVE_RESET = re.compile(r"(?m)^\s*Diag\.reset\(\)")
if _ov_ad:
    check("static func pruneStaleOverlay" in _ov_du and "bundleDate >= overlayDate" in _ov_du,
          "DataUpdater no longer drops an overlay the bundle has caught up with")
    _dfl = _ov_ad[_ov_ad.find("didFinishLaunchingWithOptions"):]
    _p, _q = _LIVE_PRUNE.search(_dfl), _dfl.find("ChargerStore.shared.dataURL")
    check(_p is not None and _p.start() < _q,
          "AppDelegate resolves data.js without first pruning a stale overlay")
    check(_LIVE_PRUNE.search(_ov_ai[_ov_ai.find("func preparedStore"):]) is not None,
          "the Siri intent resolves data.js without pruning — it can run without the app UI launching")
    _vdl = _ov_wv[_ov_wv.find("override func viewDidLoad()"):][:300]
    check(not _LIVE_RESET.search(_vdl),
          "viewDidLoad resets the boot log again — every line logged at launch is wiped")
    check(_LIVE_RESET.search(_dfl[:400]) is not None,
          "the boot log is no longer reset at the start of launch")
    # Release-blocking iOS details from the 2026-10-07 audit.
    _py = open(os.path.join(HERE, "ios", "project.yml")).read()
    _wsec = _py[_py.find("  ChargeAndChewWidget:"):]
    check("CFBundleVersion: $(CURRENT_PROJECT_VERSION)" in _wsec,
          "widget build number is hard-coded again — App Store Connect flags the mismatch (ITMS-90473)")
    check("stays on your device" not in _py, "location prompt claims the location stays on the device again")
    _pm = os.path.join(HERE, "ios", "ChargeAndChew", "PrivacyInfo.xcprivacy")
    check(os.path.exists(_pm) and "<string>CA92.1</string>" in open(_pm).read(),
          "privacy manifest missing, or no longer declares the UserDefaults reason")
    check('appendingPathComponent("widget.tsv")' in _swf("../Widget/ChargeAndChewWidget.swift")
          and "make-widget-index.py" in open(os.path.join(HERE, "ios", "sync-web.sh")).read(),
          "the widget parses the full data.js again (~70 MB peak, over WidgetKit's limit)")
    check(re.search(r"(?m)^\s*guard userTapped else", _ov_wv) is not None
          and 'scheme == "tel" || scheme == "mailto"' in _ov_wv,
          "non-web links can open without a tap again (tel:, sms:, other apps)")
    _ai_src = _swf("AppIntents.swift")
    check('spec.append("one stall")' in _ai_src and "if c.kw > 0" in _ai_src,
          "Siri reads '0 kilowatts' / '1 stalls' aloud again")
    _dg = _swf("Diag.swift")
    check(re.search(r"static func reset\(\) \{\s*#if !DEBUG\s*return", _dg) is not None,
          "release builds create an empty boot log in the user's Documents again")
    # A bare hasSuffix("google.com") also matches "evilgoogle.com".
    check('host.hasSuffix(".google.com")' in _ov_wv and 'host.hasSuffix("google.com")' not in _ov_wv,
          "openExternal matches google.com by bare suffix again — evilgoogle.com would pass")

# ---- bad data can neither ship nor stick (audit 2026-10-07) ----
# A truncated or differently-shaped download used to become the copy every launch read: the
# app opened to an error screen for good. Reproduced on the simulator before the fix, and
# both cases (truncated; complete but fmt 2) recover by themselves after it.
_bd = open(os.path.join(HERE, "data", "build_data.py")).read()
_fmt_page = re.search(r"(?m)^const DATA_FMT = (\d+);", _html)
_fmt_pipe = re.search(r"(?m)^DATA_FMT = (\d+)", _bd)
check(_fmt_page and _fmt_pipe and _fmt_page.group(1) == _fmt_pipe.group(1),
      "DATA_FMT in index.html and data/build_data.py disagree (or one is missing)")
_fmt_data = re.search(r'"fmt":(\d+)', open(os.path.join(HERE, "data.js")).read(300))
check(_fmt_page and (_fmt_data.group(1) if _fmt_data else "1") == _fmt_page.group(1),
      "data.js declares a format index.html does not read")
check(re.search(r"(?m)^\s*if \(dataBad\) \{", _html) and "cmd: 'dataFailed'" in _html,
      "the page no longer reports unreadable data to the iOS shell")
# The shrink guard sliced the raw file and json.loads'd it, which cannot read the escaped
# JSON.parse('...') form; the exception was swallowed and every check silently skipped.
check(re.search(r"(?m)^\s*old = load_data\(out_path\)", _bd) is not None
      and "old = None" not in _bd,
      "build_data.py no longer reads the old data.js with data_reader (shrink guard dead again)")
if _ov_ad:
    _refresh = _ov_du[_ov_du.find("private static func download("):]
    _dec, _wr = _refresh.find("ChargerStore.decodePayload("), _refresh.find("data.write(to: tmp")
    check(0 <= _dec < _wr, "DataUpdater writes a download without decoding it first")
    check(re.search(r"format\(inHead: h\) == wantFmt", _ov_du) is not None,
          "DataUpdater accepts a download in a different data format")
    check(re.search(r'(?m)^\s*case "dataFailed":', _swf("NativeBridge.swift")) is not None
          and re.search(r"(?m)^\s*bridge\.onDataFailed = ", _ov_wv) is not None,
          "the shell no longer falls back to bundled data when the page reports bad data")
_wf = open(os.path.join(HERE, ".github", "workflows", "refresh-data.yml")).read()
check("fetch_pois.py || true" not in _wf and "fetch_highways.py || true" not in _wf,
      "the refresh workflow swallows fetch failures with || true again")
# The stop signals' cache is kept by the weekly refresh (gap-fill), loudly when it fails.
check('python3 data/fetch_amenities.py || echo "::warning::fetch_amenities failed' in _wf
      and _wf.index("fetch_amenities.py") < _wf.index("python3 data/build_data.py")
      and os.path.exists(os.path.join(HERE, "data", "amenities.json")),
      "the refresh workflow no longer fills data/amenities.json before build_data.py (or the cache is gone)")
_fa = open(os.path.join(HERE, "data", "fetch_amenities.py")).read()
check('UA = "chargeandchew-data/' in _fa and '"User-Agent": UA' in _fa and "time.sleep(PAUSE)" in _fa
      and "wait = min(wait * 2, 900)" in _fa and "ThreadPool" not in _fa and "concurrent" not in _fa,
      "fetch_amenities.py is no longer polite to Overpass (named UA, one at a time, pause, backoff)")

# ---- instant category results, merged with the live lookup ----
# The bundled chains answer immediately; the live lookup then ADDS independents. Merge, not
# replace: OSM tags a Dairy Queen as fast_food, so an ice_cream lookup never returns one and a
# replace would silently lose it. Verified with a controlled Overpass response: 86 -> 88 (one
# indie cafe within a walk of two chargers), bundled Starbucks dropped, no duplicates.
_rlp = _html[_html.find("async function runLivePoi"):]
_net = _rlp.find("await overpassFetch(")
check(0 < _rlp.find("applySeed(intent, seed);") < _net,
      "category results are no longer shown before the live lookup — back to a 10-20 s blank wait")
check("const indie = seed.length ? pois.filter(p => !isBundledChain(p, seed)) : pois;" in _html,
      "live results are no longer de-duplicated against the bundled chains already shown")
check("applySeed(intent, matched ? seed.concat(key) : seed);" in _html,
      "a successful lookup REPLACES the bundled chains again — Dairy Queen would vanish from ice cream")
if _node and "function isBundledChain(p, chains)" in _html:
    _fn2 = _html[_html.index("const nameKey = s =>"):_html.index("/* Put the bundled chains for a category on screen.")]
    _js2 = _fn2 + r"""
const C=["Starbucks","Dunkin'","Peet's Coffee","Dutch Bros"];
const t=[[{brand:"Starbucks",name:"Starbucks"},true],[{name:"Starbucks Coffee"},true],[{brand:"Dunkin' Donuts"},true],
 [{name:"Peet's Coffee & Tea"},true],[{name:"Dutch Bros. Coffee"},true],[{name:"Blue Bottle Coffee"},false],
 [{name:"Verve"},false],[{name:""},false],[{},false]];
const f=t.filter(([p,w])=>isBundledChain(p,C)!==w).map(([p,w])=>JSON.stringify(p)+" expected "+w);
console.log(f.length?f.join("\n"):"OK");"""
    _r2 = subprocess.run([_node, "-e", _js2], capture_output=True, text=True)
    check(_r2.stdout.strip() == "OK", "isBundledChain() misclassifies places:\n  " + (_r2.stdout + _r2.stderr).strip()[:300])

# ---- phone map: big enough, and framed for the space it actually has ----
# The sheet opened to 50% of a phone, the fit framed the FULL-height map, then the sheet slid up
# and the map shrank keeping its top edge -- only 33% of LA -> Santa Barbara was on screen.
_sp = re.search(r"phoneLayout \? (0\.\d+) :", _html)
check(_sp is not None and float(_sp.group(1)) <= 0.42,
      "the phone sheet opens taller than 42% again — the map is squeezed to a strip")
check(re.search(r"\$\('sheet'\)\.addEventListener\('transitionend'", _html) is not None
      and "settleFit(lastFit.getBounds, lastFit.padding, lastFit.maxZoom);" in _html,
      "the map is no longer re-framed once the sheet finishes resizing — results end up under it")
check("if (wideLayout() || sheetState === 'full' || !lastFit || userMovedMap) return;" in _html,
      "re-framing ignores the user — the map would snap back after they pan it")
_lf, _ss = _html.find("let lastFit = null, userMovedMap = false;"), _html.find("function setSheet(")
check(0 < _lf < _ss, "lastFit is declared after setSheet, which reads it — a TDZ error at boot")
check(re.search(r"(?m)^map\.on\('dragstart', \(\) => \{ userMovedMap = true; \}\);", _html) is not None,
      "a user drag no longer stops automatic re-framing")
# The button column floats over the map's right edge; the LA pins sat half-covered on the
# route button until the fit measured it.
check("paddingBottomRight: [Math.max(padding[0], ctlW + 6), padding[1]]" in _html
      and "document.querySelector('.mapctl')" in _html,
      "the map fit ignores the button column again — pins at the right edge end up under it")
# Whole-number zooms halved the frame: 266 px for a route that fits 377 at a half step.
check(re.search(r"zoomSnap: 0\.5\b", _html) is not None,
      "the map snaps to whole zoom levels again — a fit that just misses drops a full step and halves")

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
# ---- keyboard and screen-reader access (fix 6, 2026-10-10; each checked with real keys) ----
check('<button type="button" class="rowname"' in _html,
      "result rows have no keyboard handle again — a keyboard user cannot open a charger")
check("t.matches('[role=\"button\"]:not(button):not(a)')" in _html,
      "Enter/Space no longer activate role=button rows (legend, networks, popup chains)")
for _dlg in ("hero", "picker", "filters", "carPicker", "about"):
    check(re.search(r'id="%s"[^>]*role="dialog" aria-modal="true"' % _dlg, _html) is not None,
          f"#{_dlg} is no longer marked up as a modal dialog")
check("if (e.key === 'Escape') { e.preventDefault(); d.close(); return; }" in _html
      and "if (back && back.isConnected && back.focus) back.focus();" in _html,
      "dialogs no longer close on Escape or return focus to where it was")
check("$('placeIn').setAttribute('aria-activedescendant'" in _html,
      "the highlighted search suggestion is not announced to screen readers again")
check(".oh.n{background:var(--warn-bg);color:var(--warn)}" in _html,
      "the 'Closed' hours pill is back to amber-on-amber (1.6:1)")
check("#ccX::after" in _html, "the smallest controls lost their enlarged tap area")

# ---- shared links and the radius buttons (audit 2026-10-07; both checked in a browser) ----
check("F.nodlr ? p.set('nodlr', '1')" in _html and "netPick ? p.set('netpick', netPick)" in _html
      and "if (q.get('nodlr')) F.nodlr = 1;" in _html and "q.get('netpick')" in _html,
      "a shared link drops 'No dealerships' or the exact network again")
check(re.search(r"if \(VIEW_KEYS\.some\(k => q\.has\(k\)\)\) \{ F = Object\.assign\(\{\}, FDEF\);", _html) is not None,
      "a shared view merges the recipient's own saved filters in again — they see fewer stops")
_rad = _html[_html.find("$('ccRad').querySelectorAll('button').forEach(b => b.onclick"):][:900]
check("if (term) runLivePoi(intentFromTerm(term));" in _rad and "sortBy = keepSort;" in _rad,
      "changing the radius throws away a category search or the chosen sort again")

# ---- small behaviour fixes from the audit (each checked in a browser) ----
check("Route planning needs a connection" not in _html and "only routes planned before work without a signal" in _html,
      "route planning refuses offline again, although a planned trip is fully cached")
check("const kind = a.kind === 'me' ? 'pin' : (a.kind || 'place');" in _html,
      "a two-week-old 'my location' is restored with the live you-are-here dot again")
check(" Superchargers within ${corridorMi} mi" not in _html, "the route summary calls every network 'Superchargers' again")
check("btn.style.top = Math.max(14, Math.round(top) + 8) + 'px';" in _html,
      "'Search this area' can cover the search box on a phone again")

# ---- plugs: CCS / Tesla / CHAdeMO filter, per-plug speed, route planning (2026-10-11) ----
check("if (F.plug && !(s.conn & F.plug)) return false;" in _html
      and "if (F.kw && kwFor(s, F.plug) < F.kw) return false;" in _html,
      "the plug filter (or plug-specific speed) no longer applies — routes would mix in unusable plugs")
check('id="routePlugSeg"' in _html and "setPlug(+b.dataset.v)" in _html,
      "the route planner lost its plug picker")
check("p.set('plug'" in _html and "'plug'," in _html[_html.find("const VIEW_KEYS"):][:200]
      and "PLUG_PARAM[(q.get('plug')" in _html,
      "a shared ?plug= link no longer opens with that plug")
check("routeCountText()" in _html, "the route summary counts every plug again while the list is filtered")
if _node and "function kwFor(s, bit)" in _html:
    _k = _html[_html.index("function kwFor(s, bit)"):_html.index("/* Speed bands,")]
    _r4 = subprocess.run([_node, "-e", _k + r"""
const f = [];
const tesla = { kw: 250, conn: 3, pk: [62, 250, 0] }, ccs = { kw: 350, conn: 1 }, nopk = { kw: 150, conn: 5 };
if (kwFor(tesla, 1) !== 62) f.push('CCS at a Tesla site should be 62, got ' + kwFor(tesla, 1));
if (kwFor(tesla, 2) !== 250) f.push('NACS should be 250');
if (kwFor(tesla, 0) !== 250) f.push('no plug -> site max');
if (kwFor(ccs, 1) !== 350) f.push('single-plug site -> its kw');
if (kwFor(nopk, 4) !== 150) f.push('unknown per-plug -> site kw');
console.log(f.length ? f.join('\n') : 'OK');"""], capture_output=True, text=True)
    check(_r4.stdout.strip() == "OK", "kwFor() gives the wrong plug speed:\n  " + (_r4.stdout + _r4.stderr).strip()[:300])
# The pipeline must merge only one network's duplicate listings, and keep their plugs.
_bdsrc = open(os.path.join(HERE, "data", "build_data.py")).read()
check('key = (round(s["lat"], 4), round(s["lon"], 4), s.get("net"))' in _bdsrc,
      "de-duplication keys on coordinates alone again — a Tesla site sharing an EA station's spot vanishes")
_mp = _bdsrc[_bdsrc.index("PLUG_BITS = (1, 2, 4)"):_bdsrc.index("def clean(sites):")]
_ns = {}
exec(_mp, _ns)
_a = {"conn": 2, "kw": 250}; _ns["merge_plugs"](_a, {"conn": 1, "kw": 62})
check(_a["conn"] == 3 and _a.get("pk") == [62, 250, 0] and _a["kw"] == 250,
      f"merge_plugs loses a plug or its speed: {_a}")
_b = {"conn": 1, "kw": 50}; _ns["merge_plugs"](_b, {"conn": 1, "kw": 150})
check(_b["conn"] == 1 and "pk" not in _b and _b["kw"] == 150, f"merge_plugs on one plug type: {_b}")
# Per-plug speeds in the data: [CCS, NACS, CHAdeMO] ints, only on multi-plug sites.
_bad_pk = [x["id"] for x in (D or {}).get("sites", []) if "pk" in x and not (
    isinstance(x["pk"], list) and len(x["pk"]) == 3 and all(isinstance(v, int) and v >= 0 for v in x["pk"])
    and bin(x.get("conn", 0)).count("1") > 1)]
check(not _bad_pk, f"{len(_bad_pk)} sites carry a malformed per-plug speed list, e.g. {_bad_pk[:3]}")

# ---- the optional Level 2 layer (2026-10-11) ----
_l2p = os.path.join(HERE, "level2.js")
check(os.path.exists(_l2p), "level2.js is missing (run data/build_level2.py)")
if os.path.exists(_l2p):
    try:
        _L2 = load_data(_l2p, prefix="window.PITSTOP_L2")
    except Exception as e:
        _L2 = None; fail.append(f"level2.js is not valid: {e}")
    if _L2:
        _l2s = _L2.get("sites", [])
        check(len(_l2s) > 8000, f"level2.js has only {len(_l2s)} sites")
        check(_L2.get("fmt") == 1, "level2.js has an unknown format")
        _dcids = {x["id"] for x in (D or {}).get("sites", [])}
        check(not any(x["id"] in _dcids for x in _l2s), "a Level 2 site duplicates a fast charger id")
        check(all(x.get("conn", 0) & 10 and not x.get("conn", 0) & 5 for x in _l2s),
              "a Level 2 site carries a fast-charging plug, or no Level 2 plug")
        _bk = set((D or {}).get("brands", {}))
        check(all(k in _bk for m in _L2.get("matches", {}).values() for k in m),
              "level2.js matches a chain the app does not know")
    _v2 = hashlib.sha256(open(_l2p, "rb").read()).hexdigest()[:10]
    check(f"const L2_URL = 'level2.js?v={_v2}';" in _html,
          "index.html loads a stale level2.js version (run build.py)")
check("'level2.js'" in open(os.path.join(HERE, "publish.py")).read().replace('"', "'"),
      "level2.js is not in the published allow-list")
check("$ROOT/level2.js" in open(os.path.join(HERE, "ios", "sync-web.sh")).read(),
      "the iOS app does not bundle level2.js")
check("#filters .ftog[data-f]')" in _html and "#filters .ftog')" not in _html,
      "the generic filter toggles capture the Level 2 switch again (its click did nothing)")
check("SITES.length = DC_COUNT; walkCache.length = DC_COUNT;" in _html,
      "switching Level 2 off no longer restores the fast-charger list exactly")
if _node and "function compat(s)" in _html:
    _cf = _html[_html.index("function compat(s)"):_html.index("function chargeMin(s)")]
    _r5 = subprocess.run([_node, "-e", "let CAR; const carInfo = () => CAR;\n" + _cf + r"""
const f = [], t = (car, s, want) => { CAR = car; const got = compat(s); if (got !== want) f.push(JSON.stringify([car[2], s, got, want])); };
t([75, 250, 2], { lvl: 2, conn: 8 }, 'adapter');   // Tesla at J1772: ships with the adapter
t([75, 250, 2], { lvl: 2, conn: 2 }, 'native');    // Tesla at a Tesla destination charger
t([77, 230, 1], { lvl: 2, conn: 8 }, 'native');    // CCS car at J1772
t([77, 230, 1], { lvl: 2, conn: 2 }, 'adapter');
t([40, 50, 4],  { lvl: 2, conn: 8 }, 'native');    // CHAdeMO car (Leaf) charges on J1772
t([77, 230, 1], { conn: 1 }, 'native');            // fast chargers unchanged
t([77, 230, 1], { conn: 4 }, null);
console.log(f.length ? f.join("\n") : "OK");"""], capture_output=True, text=True)
    check(_r5.stdout.strip() == "OK", "compat() is wrong for Level 2 plugs:\n  " + (_r5.stdout + _r5.stderr).strip()[:300])

# Every view parameter the web app reads must survive the iOS deep-link allow-list.
_vk = re.search(r"const VIEW_KEYS = \[([^\]]*)\]", _html)
_wvc = open(os.path.join(HERE, "ios", "ChargeAndChew", "WebViewController.swift")).read()
_al = re.search(r"let allowed = \[([^\]]*)\]", _wvc)
if _vk and _al:
    _missing = set(re.findall(r"'(\w+)'", _vk.group(1))) - set(re.findall(r'"(\w+)"', _al.group(1)))
    check(not _missing, f"iOS deep links drop these view parameters: {sorted(_missing)}")

# ---- UI polish (2026-10-12): layout bugs found by the visual review ----
_flt = _html[_html.find('<div id="filters" class="modal"'):]
check(_flt.find('<div class="pkgrid">') != -1 and _flt.find('<div class="pkgrid">') < _flt.find('<div class="pkfoot">')
      and ".pkgrid{overflow-y:auto;padding:0 16px 16px;flex:1;min-height:0" in _html,
      "the Filters sheet has no scrolling body again — its lower half and Show results are unreachable on a phone")
check("#carGrid{display:grid" in _html, "the car picker lost its grid: options become a ragged staircase")
_pp = _html[_html.find("function popupPad(m)"):][:900]
check("if (wideLayout()) {" in _pp, "desktop popups are clamped to the phone's visible band again (~150 px tall)")
check("-webkit-line-clamp:2" in _html[_html.find(".row .n b,.row .n .rowname{"):][:400],
      "result titles are single-line again — cut to ~12 characters on a phone")
check("lower48.length >= v.length * 0.95" in _html, "fitToResults frames Alaska/Hawaii again, squeezing the US into a strip")

check("if (filtered && (!passesNet(s) || !passesSpec(s)" in _html,
      "chip counts ignore the active filters again ('Starbucks 17' beside an empty list)")
check("el.focus({ preventScroll: true })" in _html,
      "opening a dialog can scroll it again (the welcome card lost its top on short phones)")
check("color-scheme:dark;" in _html and "color-scheme:light;" in _html,
      "native scrollbars and controls no longer follow the theme")
check(".ftog::after{" in _html, "filter toggles lost their on/off switch")
check("function centerStyle(kind)" in _html and "'#ffb020'" not in _html,
      "the area centre pin is amber again — the same colour as ChargePoint stops")

check(re.search(r"let opened = false;[\s\S]{0,600}?userMovedMap = true;", _html) is not None
      and "userMovedMap = true;          // an open stop" in _html,
      "opening a stop no longer stops the sheet's re-fit — on an iPhone the popup header lands under the search bar")

check("if (scoped && !inScope(s)) continue;" in _html[_html.find("function renderLegend()"):][:1200],
      "network counts are national again while viewing an area ('Tesla 3,280' beside 37 stops)")

# ---- first load (2026-10-12): throttled phone, map paint 2.2 s -> 0.73 s, layout shift 0.162 -> 0.015 ----
_early = _html.find("window.__ccMap = m;")
check(0 < _early < _html.find('<script src="data.js?v='),
      "the map no longer starts before data.js — its first paint waits for the 1 MB dataset again")
check("const map = window.__ccMap || L.map(" in _html, "the app creates a second map instead of adopting the early one")
check("const BASEMAPS = window.CC_BASEMAPS;" in _html and _html.count("World_Light_Gray_Base") == 1,
      "tile URLs are defined twice again (early script and app) and can drift apart")
check("if (window.__ccEarlyTiles) { window.__ccEarlyTiles.forEach(l => map.removeLayer(l));" in _html,
      "the early tile layers are never removed — two base layers stack")
check(re.search(r"@media \(max-width:759px\)\{#sheet\{height:40vh", _html) is not None
      and "let sheetState = 'mid';" in _html,
      "the phone sheet starts collapsed and jumps open again (a 0.16 layout shift on every load)")

# Weekly refresh: a footer with the exact date would rewrite every page every week.
check(re.search(r"Updated [A-Z][a-z]+ \d{4} ·", open(os.path.join(HERE, "near", "ihop", "index.html")).read()) is not None,
      "generated pages print the exact data date again — every weekly refresh would rewrite all of them")
check("'17 9 * * 1'" in open(os.path.join(HERE, ".github", "workflows", "refresh-data.yml")).read(),
      "the data refresh is no longer weekly")
# Filters holds plug, speed, Level 2 and networks: it must lead the chip row, not hide off-screen.
_cr = _html[_html.find('<div class="chiprow" id="chiprow">'):]
check(_cr.find('id="filtBtn"') < _cr.find('id="catchips"'), "the Filters chip is no longer first in the chip row")

# ---- interstates as corridors (2026-10-14) ----
_hwp = os.path.join(HERE, "highways.js")
check(os.path.exists(_hwp), "highways.js is missing (build.py writes it)")
if os.path.exists(_hwp):
    _hwraw = open(_hwp).read()
    _hw = json.loads(_hwraw[_hwraw.index("{"):_hwraw.rindex("}") + 1])
    check(len(_hw) >= 20, f"highways.js has only {len(_hw)} interstates")
    # Ordered along the road, not by latitude: the drawn length must be close to the real one.
    import math as _m
    def _km(a, b):
        p = _m.pi / 180
        x = _m.sin((b[0] - a[0]) * p / 2) ** 2 + _m.cos(a[0] * p) * _m.cos(b[0] * p) * _m.sin((b[1] - a[1]) * p / 2) ** 2
        return 12742 * _m.asin(_m.sqrt(x))
    for _ref, _real in (("I-95", 3069), ("I-5", 2223), ("I-75", 2856)):
        if _ref in _hw:
            _len = sum(_km(_hw[_ref][i - 1], _hw[_ref][i]) for i in range(1, len(_hw[_ref])))
            check(0.85 * _real < _len < 1.15 * _real,
                  f"{_ref} draws {_len:.0f} km against a real {_real} km — the points are out of road order")
    _v3 = hashlib.sha256(open(_hwp, "rb").read()).hexdigest()[:10]
    check(f"const HWY_URL = 'highways.js?v={_v3}';" in _html, "index.html loads a stale highways.js (run build.py)")
check("highways.js" in open(os.path.join(HERE, "publish.py")).read(), "highways.js is not published")
check('href="../../?hwy=I-75"' in open(os.path.join(HERE, "along", "i-75", "index.html")).read(),
      "the /along/ pages no longer open their interstate in the map")
check(re.search(r"const blk|  if \(p\.hwy && !trip\) \{", _html) is not None
      and _html.find("if (p.hwy && !trip) {") > _html.find("if (p.kw && F.kw !== p.kw) {"),
      "the highway search runs before the query's chain/filters are applied (the chain is dropped)")

# ---- tap speed (fix 6, 2026-10-10) ----
# Tap-to-paint on a 4x-throttled phone profile: chain chip ~200 -> ~85 ms, "Any food"
# ~375-510 -> ~225 ms, with the rendered 300-row list verified identical in nine scenarios.
check(re.search(r"const d = walkTo\(s, keys\[i\], m\[keys\[i\]\]\)", _html) is not None,
      "bestWalk recomputes every walk on every tap again instead of using the walk cache")
check("if (!BUNDLED_KEYS.has(k)) return mDist(s, v);" in _html,
      "the walk cache would also cache live-lookup keys, which change at runtime")
check("requestAnimationFrame(() => {\n      queued = false;" in _html,
      "the chip-row edge check forces a synchronous layout after every render again")
check("content-visibility:auto" in _html[_html.find(".row{"):_html.find(".row{") + 120],
      "result rows below the fold are laid out on every tap again")
if _node and "function sortByKey(arr, key)" in _html:
    _a = _html.index("const LIST_MAX = 300;")
    _fn3 = _html[_a:_html.index("\n}\n", _html.index("function sortByKey(arr, key)")) + 3]
    _js3 = _fn3 + r"""
// The partial sort must give exactly the first LIST_MAX of a stable full sort.
let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const f = [];
for (const n of [0, 1, 5, 299, 300, 601, 1000, 14000]) {
  for (const ties of [false, true]) {
    const arr = Array.from({length: n}, (_, i) => ({ i, v: ties ? Math.floor(rnd() * 20) : (rnd() < 0.02 ? undefined : rnd()) }));
    const key = o => o.v === undefined ? NaN : o.v;
    const ref = arr.slice().sort((a, b) => { const x = key(a), y = key(b);
      const xa = x === x ? x : Infinity, ya = y === y ? y : Infinity; return (xa - ya) || (a.i - b.i); });
    const got = sortByKey(arr.slice(), key);
    const want = ref.slice(0, LIST_MAX).map(o => o.i).join(), have = got.slice(0, LIST_MAX).map(o => o.i).join();
    if (want !== have) f.push(`n=${n} ties=${ties}: first ${LIST_MAX} differ`);
    if (got.length !== n || new Set(got).size !== n) f.push(`n=${n}: items lost or duplicated`);
  }
}
console.log(f.length ? f.join("\n") : "OK");"""
    _r3 = subprocess.run([_node, "-e", _js3], capture_output=True, text=True)
    check(_r3.stdout.strip() == "OK", "sortByKey no longer matches a stable sort:\n  " + (_r3.stdout + _r3.stderr).strip()[:400])
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
    check(len(_dirs) == len(_tj),
          f"{len(_dirs)} trip pages for {len(_tj)} cached routes: drop thin drives from tools/add_trips.py PAIRS")
    _sm = open(os.path.join(HERE, "sitemap.xml"), encoding="utf-8").read()
    check(_sm.count("/trip/") >= len(_dirs), "trip pages are missing from the sitemap")
    _lv = os.path.join(HERE, "trip", "los-angeles-to-las-vegas", "index.html")
    check(os.path.exists(_lv), "the LA to Las Vegas trip page is gone")
    if os.path.exists(_lv):
        _t = open(_lv, encoding="utf-8").read()
        # The CTA is the whole point of the page: it opens the app on this drive, leaving at
        # 8:00 am, so the app's plan is the plan on the page.
        check('<a class="cta" href="../../?from=Los%20Angeles%2C%20CA&amp;to=Las%20Vegas%2C%20NV&amp;c=5&amp;leave=0800">Open this drive in the app' in _t,
              "the trip CTA no longer opens the app on that drive leaving at 8:00 am")
    # The 8 am plan on every trip page (2026-11-11): planner.py's port of the app's breaks
    # card. tools/trip_plan_check.mjs compares it with the app itself; this checks that every
    # page carries one, that it is what planner.py says NOW (a page left stale after a change
    # to the plan's code or to index.html's meal rules fails here), and that it is sane.
    import planner as _pl
    from html import unescape as _un
    _txt = lambda h: _un(re.sub(r"<[^>]+>", "", h)).strip()
    _sites = {x["id"]: x for x in D["sites"]} if D else {}
    _bad_plan, _bad_faq, _bad_ld, _stale = [], [], [], []
    for _tk, _tt in _tj.items():
        _sl = "-to-".join(re.sub(r"[^a-z0-9]+", "-", x.split(",")[0].lower()).strip("-") for x in (_tt["a"], _tt["b"]))
        _f = os.path.join(HERE, "trip", _sl, "index.html")
        if not os.path.exists(_f):
            continue
        _h = open(_f, encoding="utf-8").read()
        _tb = re.search(r'<table class="trip plan">.*?<tbody>(.*?)</tbody>', _h, re.S)
        if not _tb:
            _bad_plan.append(f"{_sl}: no plan"); continue
        _rows = re.findall(r"<tr[^>]*>(.*?)</tr>", _tb.group(1), re.S)
        if not (_rows and "<b>8:00 am</b>" in _rows[0] and "Leave " in _rows[0] and "Arrive in " in _rows[-1]):
            _bad_plan.append(f"{_sl}: no leave/arrive rows")
        _got = []
        for _r in _rows[1:-1]:
            if "No fast charger for" in _r:
                _got.append(("gap", _txt(re.search(r"<td><b>([^<]*)</b>", _r).group(1)), int(re.search(r"for (\d+) mi", _r).group(1))))
                continue
            _lab = re.search(r'<i class="ml[^"]*">([^<]*)</i> &middot; mile (\d+)', _r)
            _sid = re.search(r"leave=0800&amp;stop=(\d+)", _r)
            _k = re.search(r'<td>(?:<span class="nw">)?[^<]*<b>(.*?)</b> (\d+) min', _r.split("</td>")[3] + "</td>") if _r.count("</td>") >= 4 else None
            # Each "🌮 Taco Bell 1 min" is one nowrap unit: phones broke it as "Denny's 3 / min,".
            _fc = _r.split("</td>")[3] if _r.count("</td>") >= 4 else ""
            if re.sub(r'<span class="nw">(?:(?!</?span)[^<]|<b>|</b>|<span class="nw">[^<]*</span>)*? \d+ min(?:<small class="xh"[^>]*>across hwy</small>)?</span>', "", _fc).count(" min"):
                _bad_plan.append(f"{_sl}: a 'name N min' in the plan's food cell can break across lines")
            if not (_lab and _sid and int(_sid.group(1)) in _sites):
                _bad_plan.append(f"{_sl}: a stop row without a label, a mile or a real stop link"); continue
            _kk = _txt(_k.group(1)) if _k else ""
            if _lab.group(1) in ("Lunch", "Dinner") and _kk in _pl.NOT_A_MEAL or _lab.group(1) == "Breakfast" and _kk in _pl.NO_BREAKFAST:
                _bad_plan.append(f"{_sl}: {_lab.group(1)} at {_kk}")
            _got.append(("stop", _txt(re.search(r"<td><b>([^<]*)</b>", _r).group(1)), _lab.group(1), int(_lab.group(2)), int(_sid.group(1)), _kk))
        _P = _pl.Plan(D["sites"], {int(k): v for k, v in D["matches"].items()}, D["brands"], _tt["pts"],
                      _tt["mi"] * _pl.MI / _pl.MI, _tt["hr"] * 3600 / 3600, __import__("datetime").date.fromisoformat(D["generated"]), 480, 5)
        _want = [("gap", r["clock"], r["gap"]["len"]) if r["kind"] == "gap" else
                 ("stop", r["clock"], r["label"], r["mi"], r["s"]["id"], r["k"] or "") for r in _P.rows()]
        if _got != _want or f"<b>~{_P.arrive()[0]}</b>" not in _rows[-1]:
            _stale.append(_sl)
        # The charger count is the app's (every DC fast charger in the plan's corridor): the page
        # once said 228 (its own narrower grid, 50 kW and up) where the app said 236.
        _lead = re.search(r"sit <b>about ([\d,]+) DC fast chargers</b> within 5 miles", _h)
        if not _lead or int(_lead.group(1).replace(",", "")) != len(_P.order):
            _bad_plan.append(f"{_sl}: the lead's charger count is not the app's ({len(_P.order)})")
        _stops = [g for g in _got if g[0] == "stop"]
        if _stops and _stops[0][3] * _tt["hr"] * 60 / _tt["mi"] < 55:
            _bad_plan.append(f"{_sl}: first stop at mile {_stops[0][3]}, under an hour out")
        if _tt["hr"] * 60 <= 150 and _stops:
            _bad_plan.append(f"{_sl}: a stop on a drive of 2.5 hours or less leaving at 8 am")
        # The FAQPage markup is the visible questions and answers, word for word.
        _vis = [(_txt(q), _txt(a)) for q, a in re.findall(r"<details><summary>(.*?)</summary><p>(.*?)</p></details>",
                                                           (re.search(r'<h2>Questions about this drive</h2><div class="faq">(.*?)</div>', _h, re.S) or re.match("()", "")).group(1), re.S)]
        _lds = []
        for _m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', _h, re.S):
            try:
                _lds.append(json.loads(_m.group(1).replace("<\\/", "</")))
            except ValueError:
                _bad_ld.append(_sl)
        _fq = [x for x in _lds if x.get("@type") == "FAQPage"]
        _ldq = [(e["name"], e["acceptedAnswer"]["text"]) for e in _fq[0]["mainEntity"]] if len(_fq) == 1 else None
        if not _vis or len(_vis) < 5 or _ldq != _vis:
            _bad_faq.append(_sl)
    # ~150 drives (2026-11-11): each page links its related drives (not all of them) and the
    # index; the index lists every drive once, by region; the chain pages link the drives that
    # pass them, and no placeholder is left behind.
    _onpages = sorted(d for d in _dirs if os.path.isfile(os.path.join(HERE, "trip", d, "index.html")))
    check(len(_onpages) >= 140, f"only {len(_onpages)} trip pages (expected ~150)")
    _ix = open(os.path.join(HERE, "trip", "index.html"), encoding="utf-8").read()
    _ixl = re.findall(r'<a href="([a-z0-9-]+)/">', _ix)
    check(sorted(_ixl) == _onpages, "the trips index does not list every trip page exactly once")
    check(_ix.count("<h2>The ") >= 4, "the trips index lost its regions")
    _rel_bad = []
    for _d in _onpages:
        _h = open(os.path.join(HERE, "trip", _d, "index.html"), encoding="utf-8").read()
        _m = re.search(r'<h2>More road trips</h2><div class="chips">(.*?)</div>', _h, re.S)
        _l = re.findall(r'href="\.\./([a-z0-9-]+)/"', _m.group(1)) if _m else []
        if not (_m and 5 <= len(_l) <= 10 and _d not in _l and set(_l) <= set(_onpages) and 'href="../"><b>All road trips' in _m.group(1)):
            _rel_bad.append(_d)
    check(not _rel_bad, f"trip pages without a related-drives list: {_rel_bad[:3]}")
    _near_all = glob.glob(os.path.join(HERE, "near", "*", "index.html")) + glob.glob(os.path.join(HERE, "near", "*", "*", "index.html"))
    _left = [p_ for p_ in _near_all if "<!--trips-->" in open(p_, encoding="utf-8").read()]
    check(not _left, f"{len(_left)} chain pages kept the road-trip placeholder, e.g. {_left[:2]}")
    _inn = os.path.join(HERE, "near", "in-n-out", "ca", "index.html")
    check(os.path.exists(_inn) and re.search(r'<h2>Road trips with <span class="nw">In-N-Out</span> on the way</h2>.*?'
                                              r'href="\.\./\.\./\.\./trip/[a-z-]+/"', open(_inn, encoding="utf-8").read(), re.S),
          "near/in-n-out/ca no longer links the road trips that pass In-N-Out in California")
    _wt = sum(1 for p_ in _near_all if "/trip/" in open(p_, encoding="utf-8").read())
    check(_wt > 1000, f"only {_wt} chain pages link a road trip")
    check(not _bad_plan, f"trip-page 8 am plans are wrong: {_bad_plan[:3]}")
    check(not _stale, f"{len(_stale)} trip pages' plans differ from planner.py (run build.py): {_stale[:3]}")
    check(not _bad_faq, f"{len(_bad_faq)} trip pages' FAQPage markup is missing or differs from the visible Q&A: {_bad_faq[:3]}")
    check(not _bad_ld, f"JSON-LD does not parse on {_bad_ld[:3]}")
check("trip/los-angeles-to-las-vegas/" in _html, "the app no longer links to any trip page")

# ---- Siri / Shortcuts ----
# The strongest native capability that needs no entitlement, and a real answer to Guideline
# 4.2. The answer-building is deliberately separate from the intent shell because Shortcuts
# cannot run an app intent in the Simulator -- StopAnswer.build is what can be verified.
_ai = os.path.join(HERE, "ios", "ChargeAndChew", "AppIntents.swift")
if os.path.exists(_ai):
    _a = open(_ai, encoding="utf-8").read()
    for _needle, _why in [
        ("struct NearestStopIntent: AppIntent", "the Siri intent is gone"),
        ("enum StopAnswer", "the intent's logic is back inside the intent shell and cannot be tested"),
        ("AppShortcutsProvider", "the app no longer offers Siri phrases"),
        ("openAppWhenRun: Bool = false", "the intent opens the app instead of answering, which defeats asking Siri"),
    ]:
        check(_needle in _a, _why)
    check("$(.applicationName)" not in _a and ".applicationName" in _a,
          "Siri phrases must interpolate .applicationName or the system rejects them")

# ---- touch targets ----
# Apple's minimum is 44x44. The hero's close button was 26x26 (the hardest thing on the
# screen to hit) and the chip row 36px tall; the chips keep their look and gain the
# difference through a transparent overlay, since nothing sits directly above or below them.
check("width:44px;height:44px" in _html, "the hero close button is back under the 44px minimum")
# Chips are sized for touch in the coarse-pointer block, not with an overlay; a second
# mechanism would stack on top of the 44px they already get.
check(".chip{height:44px" in _html, "chips are no longer 44px tall on touch devices")

# ---- corridor pages must carry structured data and fit Google's title budget ----
# /along/ and /trip/ shipped none for a long time while every /near/ page had three schemas,
# and they are the pages the site most wants to win. Titles were ~90 chars; Google truncates
# near 60 and the " | Charge & Chew" suffix costs 16 of them.
import json as _json
_noldd, _longt, _badjson = [], [], []
for _p in _glob.glob(os.path.join(HERE, "trip", "*", "index.html")) + \
          _glob.glob(os.path.join(HERE, "along", "*", "index.html")):
    _h = open(_p, encoding="utf-8").read()
    _blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', _h, re.S)
    if not _blocks:
        _noldd.append(os.path.relpath(_p, HERE))
    for _b in _blocks:
        try:
            _json.loads(_b)
        except Exception:
            _badjson.append(os.path.relpath(_p, HERE))
    _t = re.search(r"<title>(.*?)</title>", _h, re.S)
    if _t and len(_t.group(1)) > 66:
        _longt.append((len(_t.group(1)), os.path.relpath(_p, HERE)))
check(not _noldd, f"corridor pages with no structured data: {_noldd[:3]}")
check(not _badjson, f"corridor pages with unparseable JSON-LD: {_badjson[:3]}")
check(len(_longt) <= 4, f"corridor titles over 66 chars: {sorted(_longt, reverse=True)[:3]}")

# ---- native parity: the Swift side must decode match offsets the same way the web does ----
# A match value is [dLat, dLon] as integer DEGREE deltas x1e4. Reading them as metres made
# 89% of the widget's and CarPlay's walk times wrong, and always too short (an 8-minute walk
# showed as 1 minute). Both readers must agree with mDist().
check("v[0] / 1e4" in _html and "v[1] / 1e4" in _html,
      "the web decoder for match offsets changed shape — re-check the Swift one in lockstep")
_store = os.path.join(HERE, "ios", "ChargeAndChew", "ChargerStore.swift")
if os.path.exists(_store):
    _sw = open(_store, encoding="utf-8").read()
    check("dLat / 1e4" in _sw and "dLon / 1e4" in _sw,
          "ChargerStore no longer converts match offsets from degrees — widget/CarPlay walk times will be wrong")
    check("(dx * dx + dy * dy).squareRoot()" not in _sw,
          "ChargerStore treats match offsets as metres again (the 89%-wrong bug)")
# Same speed AND rounding as the web's walkMin(), or a stop reads 4 min on the phone and 5
# in the car. Every native surface computes it itself.
for _f in ("ios/ChargeAndChew/CarPlaySceneDelegate.swift", "ios/Widget/ChargeAndChewWidget.swift",
           "ios/ChargeAndChew/AppIntents.swift"):
    _p = os.path.join(HERE, _f)
    if os.path.exists(_p):
        check("/ 80).rounded())" in open(_p, encoding="utf-8").read(),
              f"{_f} no longer uses the web's 80 m/min + round() for walk minutes")
# App Store Connect needs both URLs to resolve; the app links them from its about panel.
for _pg in ("privacy", "support"):
    check(os.path.exists(os.path.join(HERE, _pg, "index.html")), f"/{_pg}/ page is missing")
    check(f"/{_pg}/" in _sm if "_sm" in dir() else True, f"/{_pg}/ is not in the sitemap")
check('href="privacy/"' in _html and 'href="support/"' in _html, "the about panel lost its privacy/support links")
# ---- typing a trip into the search bar ----
# The route planner is one unlabelled icon, fourth in a stack of four map buttons, so the
# search bar and the hero card are the doors people actually use.
for _needle, _why in [
    ("function parseTrip", "typing a trip into the search bar no longer works"),
    ("window.__parseTrip", "parseTrip is not exported — the search suite cannot test it"),
    ("TRIP_REJECT", "the trip false-positive guard is gone"),
    ("CITY_ALIAS", "city abbreviations (LA, NYC, SF) no longer expand"),
    ("runRoute(tripPoi ? { poi: tripPoi } : {});",
     "a parsed trip is never handed to the router"),
    # ---- a category wanted ALONG the drive ----
    # "LA to las vegas near ice cream shop" used to put the whole tail into the
    # destination and route to a town called "Las Vegas Ice Cream Shop" -- silently
    # wrong, which is worse than refusing. These are the four pieces that fix it.
    ("function splitDest", "the trip destination no longer stops at a qualifier"),
    ("function knownPlace", "there is no way to tell where a destination ends"),
    ("const POI_PHRASES", "two-word categories ('ice cream') are gone"),
    ("'ice cream': ['amenity=ice_cream', 'shop=ice_cream']",
     "ice cream is not a searchable category"),
    ("await runLivePoi(opts.poi, 'route')",
     "a category named with a trip is never looked up along the route"),
    ("if (route) { runLivePoi(poi, 'route'); return; }",
     "searching a category with a route on screen no longer searches the route"),
    ("const onRoute = scope === 'route'",
     "runLivePoi cannot be scoped to a route"),
    # ---- the route must not sit on top of the chargers ----
    # circleMarkers render into a canvas in the overlayPane; a polyline's SVG lands in the
    # SAME pane and is added later, so an 8px route line painted over every dot on the
    # corridor AND swallowed the taps -- the stops you had just searched for could not be
    # opened. Both halves are load-bearing: a lower pane still captures pointer events.
    ("map.createPane('routePane')", "the route no longer has its own pane and covers the chargers"),
    ("pane: 'routePane', renderer: routeRenderer, interactive: false",
     "the route line is interactive again — it would swallow taps meant for the chargers"),
    ("window.__detectPoiIntent",
     "detectPoiIntent is not exported — the search suite cannot test it"),
    ("$('heroForm').onsubmit = e => { e.preventDefault(); heroPlan(", "the welcome card no longer plans a drive"),
    ("LA to Las Vegas", "the search suggestions have no road-trip example"),
]:
    check(_needle in _html, _why)
# An arrow has to become "to" BEFORE normalise(), which strips punctuation.
check("' to ')" in _html and "->" in _html,
      "arrow syntax is normalised away before parseTrip sees it")
check(re.search(r'id="placeIn" placeholder="[^"]*\'LA to (Las )?Vegas\'', _html) is not None,
      "the search placeholder does not mention trips")
check("#routeToggle{color:var(--accent)" in _html,
      "the route button reads as a fourth grey utility icon again")

# ---- place typeahead ----
# Suggestions come from SITES, not a geocoder: no request, no extra payload, works offline,
# and it can only ever suggest somewhere we actually have chargers.
for _needle, _why in [
    ("const PLACES =", "the local place index is gone"),
    ("function snapPlace", '"lasvegas" no longer resolves to a real city'),
    ("function placeMatches", "place typeahead matching gone"),
    ("function liveSugg", "the search dropdown no longer reacts to typing"),
    ("data-hold", "the half-typed-trip row would run as a query instead of waiting"),
]:
    check(_needle in _html, _why)
check("function offlineTown(q)" in _html and _html.count("const t = offlineTown(q); if (t) return t;") == 2,
      "with the place lookup down (busy, no signal) a town search fails again instead of using the chargers' own towns")
check("ranked = ranked.filter(h => !NOT_A_PLACE.test(h.type || ''));" in _html,
      "a geocoder hit on a footpath counts as a place again ('n out' flew to a trail in Colorado)")
check("""k === 'cuisine' ? `["cuisine"~"(^|;) *(${v}) *($|;)",i]`""" in _html and "const CU = c =>" in _html,
      "a cuisine search ('sushi', 'bbq') no longer asks OSM for that cuisine: it lists every restaurant again")
check("if (p.road && !trip && !p.place) {" in _html and "We can't follow ${p.road} yet" in _html,
      "'us 101' / 'pch' vanish without a word again (only interstates have lines)")
check("if (!wantState && /^\\d+\\s/.test(q.trim())) {" in _html,
      "an address's town is no longer pinned to its state: '123 main st boise' goes to Oklahoma")
check("const snap = snapPlace(q);" in _html,
      "geocode() no longer re-spaces run-together names — every caller funnels through it")
check("$('placeIn').addEventListener('input', showSugg);" in _html,
      "typing hides the suggestions again instead of filtering them")
# "toledo" must not parse as "to" + "ledo": the tail group is optional and $-anchored
# precisely so \\s* cannot be used here.
check(r"/^(.*?\b(?:to|->|→))(?:\s+(.*))?$/i" in _html,
      "the trip-tail regex changed shape — 'toledo' can parse as a trip head")
# A substring search over city+state matched "det" inside "clydetx".
check("p.ckey.includes(k)" in _html,
      "substring matching runs across the comma again — 'det' would match 'Clyde, TX'")
check("STATE_NAME[st.toUpperCase()] ? ', ' + st.toUpperCase() : all" in _html,
      "a picked suggestion renders as 'Las Vegas Nv' — the state code is not restored")
# The hero card is taller than a phone viewport. Centring it puts the title and the close
# button off-screen with no way to scroll them back.
check("function keepPopupOnScreen" in _html and re.search(r"animate: false \}\);\s*keepPopupOnScreen\(\);", _html) is not None,
      "the post-fit popup nudge is gone — on a phone the popup's right half falls off screen")
check(_html.count('enterkeyhint=') == 7 and 'autocorrect="off"' in _html,
      "phone-keyboard attributes are missing — Return keys say the wrong thing and autocorrect mangles place names")
check("$('toIn').blur(); $('goBtn').click();" in _html,
      "Return in the Destination field no longer runs the route")
check("classList.toggle('sheet-full', s === 'full')" in _html and "#app.sheet-full .mapctl" in _html,
      "map controls are no longer hidden when the sheet is full — they pile onto the search bar on a phone")
check("Date.now() - sheetChangedAt < 900" in _html,
      "'Search this area' fires on sheet resizes again")
check("$('fromIn').value = a.label" in _html and "$('toIn').value = b.label" in _html,
      "the route fields no longer show the geocoded place names — the summary reads 'la -> vegas'")
check('id="rClose"' in _html and "$('rClose').onclick = () => $('routeToggle').click();" in _html,
      "the route panel has no close control — with the FABs hidden on a phone it cannot be dismissed")
check("#app:has(#routePanel.show:not(.collapsed)) .mapctl" in _html,
      "the FAB stack overlaps the route panel again while editing a route on a phone")
# Two FABs on phones, not four: theme is in Filters, pin-drop is press-and-hold.
check("#themeBtn,#pinBtn{display:none}" in _html, "the phone FAB stack is four high again")
# Phone layout: the sheet is the control surface. relayout() moves the car bar, chip row and
# area card into the sheet on narrow screens and back on wide ones.
check("function relayout()" in _html and "document.querySelector('.sheethead').after($('centerCard'), $('chiprow'))" in _html,
      "the phone relayout is gone — controls float over the map again")
check("$('chiprow').prepend($('carBar'))" in _html, "the car bar no longer joins the chip row on phones")
check('id="filtNetList"' in _html and "$('filtNetList').innerHTML = rows" in _html,
      "Networks are not in Filters — phones have no legend button")
check("#app.phone #carBar .cartag{flex:0 0 auto" in _html,
      "the car chip collapses to a lone emoji in the chip row again")
check("phoneLayout ? 150 +" in _html, "the phone peek height no longer shows the chips")
check('id="appearanceSeg"' in _html and "function syncAppearanceSeg" in _html, "the Appearance control left Filters")
check("'#filters .seg.wide[data-f] button'" in _html and "'#filters .seg.wide[data-f]'" in _html,
      "the filter wiring grabs every segment in the sheet again and overwrites the Appearance handlers")
check("track('longpress-pin')" in _html, "press-and-hold to drop a pin is gone — phones have no pin button")
check(".moreend::before{" in _html and "＋ All chains" in _html, "the sticky All-chains chip lost its fade")
check('id="poiRetry"' in _html
      and re.search(r"\$\('poiRetry'\)\.onclick = \(\) => runLivePoi\(intent,", _html) is not None,
      "a failed live lookup is only a 3-second toast again — on a phone that reads as nothing "
      "happened (the retry must also carry the scope, or it re-searches the wrong area)")
check('data-net="${esc(k)}"' in _html and "netPick = netPick === k ? null : k;" in _html,
      "legend rows no longer filter by network — on a phone they look tappable and did nothing")
check(".empty .fball{display:block" in _html and "'The <strong>' + esc(nar[0].label)" in _html,
      "the empty state renders its filter label as a block and its button as plain text again")
check(".moreend{position:sticky;right:0" in _html,
      "the All-chains chip is no longer sticky — it takes four flings to reach on a phone")
check("if (chainQuery() || cat === 'fav') fitToResults(); else fitUS();" in _html,
      "clearing the area no longer refits the map — an empty map under a list from another state")
check("paddingTopLeft: [padding[0], padding[1] + ovH]" in _html,
      "map fits are symmetric again — on a phone the top of the framed area hides under the chips")
check("#hero{position:fixed;" in _html and "height:100dvh" in _html,
      "the hero is absolute or uses inset:0 again — in Mobile Safari with viewport-fit=cover its last button hides under the toolbar")
check("align-items:flex-start;justify-content:center;overflow-y:auto" in _html,
      "the hero card centres again — on a phone its top is unreachable")
check(".herocard{width:100%;max-width:460px;margin:auto" in _html,
      "the hero card lost margin:auto, so it no longer centres when it does fit")
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

# An area search frames its stops, not the empty ring around them (2026-10-19).
_sc = _html[_html.index("function setCenter("):_html.index("function updateCenterSub(")]
check(re.search(r"^\s*settleFit\(areaBounds\b", _sc, re.M) is not None,
      "setCenter() no longer frames the stops it found (areaBounds): pins pile up in a 25-mile ring")

# A fit that gave up while the map had no size is finished on the next resize (2026-10-19).
check(re.search(r"^\s*if \(lastFit && !lastFit\.done && !userMovedMap\) settleFit\(", _html, re.M) is not None
      and "lastFit.done = true" in _html,
      "a fit made while the map had no size is never finished: the page stays on the whole-US view")

# The search x only drops the area for the search being shown, not for half-typed text.
_pc = _html[_html.index("$('placeClr').onclick"):][:600]
check(re.search(r"^\s*if \(!shown\) \{[^}]*return; \}", _pc, re.M) is not None
      and re.search(r"^\s*lastSearchText = raw;", _html, re.M) is not None,
      "the search box's x drops the area for any typed text (one stray letter lost Los Angeles)")
_pc2 = _html[_html.index("$('placeClr').onclick"):][:1400]
check("let searchFrom = null;" in _html and "setCenter(back.lat, back.lon, back.label, back.kind)" in _pc2,
      "the search box's x no longer undoes the search: 'in n out' then x listed every In-N-Out in the country")
# Charge times say min / h: "~115m" read as metres next to "0.4 mi away".
check("~${chargeLabel(cm)}" in _html and "~${cm}m<" not in _html,
      "the row's charge-time badge is back to a bare 'm' (reads as metres)")

# Durations: whole minutes first ("2h 60m" was possible), minutes alone under the hour.
if _node and "function hmLabel(min)" in _html:
    _hm = _html[_html.index("function hmLabel(min)"):]
    _hm = _hm[:_hm.index("\n}\n") + 3]
    _r6 = subprocess.run([_node, "-e", _hm + r"""
const want = [[179.7, '3h'], [61, '1h 01m'], [24, '24 min'], [59.6, '1h'], [115, '1h 55m']];
const bad = want.filter(([m, w]) => hmLabel(m) !== w).map(([m, w]) => m + ' -> ' + hmLabel(m) + ' (want ' + w + ')');
console.log(bad.length ? bad.join('; ') : 'OK');"""], capture_output=True, text=True)
    check(_r6.stdout.strip() == "OK", "hmLabel() formats durations wrong: " + (_r6.stdout + _r6.stderr).strip()[:300])
check("% 1) * 60" not in _html, "a duration is built from (h % 1) * 60 again, which can print '2h 60m'")

# The stop card's "Set your car" brings the card back with its answer (2026-10-20).
_cg = _html[_html.index("function drawCarGrid()"):_html.index("$('carBtn').onclick")]
check(re.search(r"^\s*backToStop\(\);", _cg, re.M) is not None
      and re.search(r"openCarPicker\(\); carReturnTo = ", _html) is not None,
      "setting a car from a stop card no longer reopens that card")
# The charge advice suggests what you searched for first, when it fits.
_dw = _html[_html.index("function dwellAdvice("):][:2500]
check(re.search(r"\.sort\(\(a, b\) => \(\(b\.k === lead\) - \(a\.k === lead\)\) \|\| \(wanted\(b\.k\) - wanted\(a\.k\)\)", _dw) is not None,
      "dwellAdvice ignores the searched chain (Starbucks search suggested Walmart)")

# Filters / chain picker buttons say how many stops you will get.
_rn = _html[_html.index("function render() {"):][:1500]
check(re.search(r"^\s*\$\('filtDone'\)\.textContent = showN;", _rn, re.M) is not None,
      "the Filters button no longer says how many stops the filters leave")

# Widening out clears the search text it undid (area x, "Show all saved stops").
check(re.search(r"\$\('ccX'\)\.onclick = \(\) => \{\s*clearCenter\(\); dropShownSearchText\(\);", _html) is not None
      and "dropShownSearchText(); fitToResults();" in _html,
      "widening out leaves the old search in the box ('chargers in austin' over a list that is not Austin)")

# Station names: network-internal tags stripped, real names left alone (2026-10-22).
sys.path.insert(0, os.path.join(HERE, "data"))
from build_data import pretty_name as _pn, unshout as _us
for _raw, _want in [("LARAMIE", "Laramie"), ("9000 NE HIGHWAY 99", "9000 NE Highway 99"),
                    ("123 W 1ST ST", "123 W 1st St"), ("2800 S I-35", "2800 S I-35"),
                    ("McKinney", "McKinney")]:
    check(_us(_raw) == _want, f"unshout({_raw!r}) = {_us(_raw)!r}, want {_want!r}")
for _raw, _want in [("Bucees Calhoun MB.HPC", "Buc-ee's Calhoun"), ("Gvec DC", "Gvec"),
                    ("BOA Kent WA5-119 (Kent, WA)", "Bank of America Kent (Kent, WA)"),
                    ("Union Station Washington DC", "Union Station Washington DC"), ("UNION STATION WASHINGTON DC", "Union Station Washington DC"),
                    ("PGE - Electric Avenue - DCFC", "PGE - Electric Avenue"), ("Motley DC Fast Charger", "Motley"), ("PENDLETON DCFC 2", "Pendleton"), ("Castle Charging Fast Charge 1", "Castle Charging"),
                    ("Love's Travel #285 (Santa Rosa, NM)", "Love's Travel #285 (Santa Rosa, NM)")]:
    check(_pn(_raw) == _want, f"pretty_name({_raw!r}) = {_pn(_raw)!r}, want {_want!r}")

# The breaks card only claims a cadence when no stretch runs long.
_bc = _html[_html.index("function breaksCard("):_html.index("function chargerGap(")]
check("longest * perMi * 60 <= BREAK_MIN * 1.25" in _bc and "longest leg ~" in _bc,
      "the breaks card claims 'about every N h' even when a stretch has no stop")
# ...and does not name a "longest leg" beside the charger-gap row: two different "longest"s read
# as one (Denver -> Salt Lake City).
check(": gap ? '' : `longest leg ~${hmLabel(longest * perMi * 60)}`;" in _bc,
      "the breaks card names a 'longest leg' next to the charger-gap row again")
# Breaks card polish (2026-11-10): the meal as a 12px amber pill (it was 10.5px), the mile under
# the clock (it was the truncated end of the food line), a chevron, and the day change marked once.
check(".brk.meal .bm i{align-self:flex-start;color:var(--chew);background:var(--chew-bg)" in _html
      and ".brk .bm i{font:500 12px/1.35 var(--sans)" in _html
      and "<span class=\"bm\">${c}<i>${meal || 'Break'}</i><small>mile ${mi}</small></span>" in _bc
      and '<svg class="chev"' in _bc and "const mark = n > day ? `<div class=\"bday\">" in _bc,
      "the breaks card rows lost their polish (meal pill, mile under the clock, chevron, one day mark)")
# A break opens a card that leads with the chain it promised (Wendy's was hidden in "+14").
check("popupLead = b.dataset.k ? { id: s.id, k: b.dataset.k } : null;" in _html
      and ".sort((a, b) => (pri(b[0]) - pri(a[0])) || (acrossHwy(s, a[0]) - acrossHwy(s, b[0])) || mDist(s, a[1]) - mDist(s, b[1]));" in _html
      and "<a class=\"pp-nb${pri(k) ? ' on' : ''}\"" in _html,
      "a suggested break's stop card no longer leads with the promised chain")
# Meal-timed breaks (2026-11): meals by LOCAL time at each stop, a real meal (no coffee for
# lunch, no Popeyes for breakfast), a leaving time that re-plans the card.
_bp = _html[_html.index("function breakPicks("):_html.index("function breaksCard(")]
check("const ms = t0 + (into + extra) * 60000, at = localAt(ms, tzOf(s));" in _bp and "nearestOf(s, mealKeys(m, meal.name), m)" in _bp,
      "meal stops are no longer timed by local time at each stop (with the time at earlier stops)")
# Time at stops (2026-11-10): "Dinner 6:00 pm" on LA -> Denver was pure driving time, ~2 h early.
# Every pick adds its dwell to the clocks after it, the arrival counts them, and the stop card's
# open/closed check uses the same plan, not "now + drive". tools/breaks_check.mjs checks the clocks.
check("if (!next) break;\n      had.add(next.key); picks.push(next); last = next.mi; extra += DWELL_MEAL;" in _bp
      and "else if (next) { had.add(next.key); picks.push(next); last = next.mi; extra += DWELL_MEAL; }" in _bp
      and "if (pick) { picks.push(pick); last = pick.mi; extra += DWELL_BREAK; }" in _bp,
      "suggested breaks no longer count the time spent at earlier stops")
# Night breaks go somewhere likely open: Starbucks at 2:35 am on LA -> New York leaving at 9 pm.
check("const sc = [off, shut, -Math.min(s.kw || 0, 350)" in _bp and "keys.filter(x => LATE.has(x))" in _bp
      and "if (lk) { k = lk; w = lw; } else shut = s.h24 ? 1 : 2;" in _bp,
      "breaks between 10 pm and 6 am no longer prefer late-night chains or 24-hour sites")
check("const arrive = t0 + route.hr * 3600000 + picks.reduce((a, p) => a + dwellOf(p), 0) * 60000;" in _html,
      "the breaks card's arrival ignores the time at stops again")
_fh = _html[_html.index("async function fillHours("):_html.index("function poiDetailHtml(")]
check("const planned = stop ? arriveMs(stop) : null;" in _fh and "hoursNow(p.hours, when || undefined, tz)" in _fh
      and "lastPlan = { route, t0, perMin: perMi * 60, picks, first, last };" in _html,
      "the stop card checks opening hours at now + drive time again, not the breaks card's leaving time")
# Opening hours on the place's own clock (2026-11-10): a New York diner said "Open until 23:00" at
# 12:25 am there, judged on a California phone. verify_hours.py runs the zone cases.
check("const lz = tz ? localAt(+now, tz) : null;" in _html and "hoursNow(P.hours, null, tzOf(s))" in _html
      and "hoursNow(p.hours, null, near ? tzOf(near) : null)" in _html,
      "opening hours are judged on the phone's clock again, not the stop's time zone")
check("if (ls) ls.onchange = () => {\n    leavePick = " in _html and 'id="leaveSel"' in _html,
      "the breaks card lost its leaving-time picker")
check("const n = $('leaveSel'); if (n) n.focus({ preventScroll: true });" in _html,
      "changing the leaving time drops keyboard/VoiceOver focus again (the list re-render recreates the select)")
check(".bleave select{font-size:16px;min-height:44px" in _html,
      "the leaving-time picker is under 16px on touch again (iOS zooms the page into it)")

# Multi-day drives count days (2026-11-10): LA -> New York arrived "next day" after 50 hours.
_bc2 = _html[_html.index("function breaksCard("):][:4000]
check("const home = localAt(t0, tzOf(first)).dn;" in _bc2
      and "n === 1 ? 'next day' : n > 1 ? 'day ' + (n + 1) : ''" in _bc2,
      "the breaks card says 'next day' for day 3 again (day labels must count from the day you leave)")
# The corridor is measured cell by cell (2026-11-10): every stop against every point of the line
# froze a phone for 2.4-3.7 s on LA -> New York at each corridor tap.
_ac = _html[_html.index("function applyCorridor("):_html.index("function applyCorridor(") + 4500]
check("const b = bucket.get(cell(ci + di, cj + dj));" in _ac and "cells.add(cell(ci + di, cj + dj))" in _ac
      and "+ ',' +" not in _ac and "for (let i = 0; i < verts.length; i += step) {\n      const d = hav(" not in _ac,
      "applyCorridor measures each stop against every route point again (seconds-long freeze on long routes)")
# Time zones at stops (2026-11-10): Ontario OR, West Wendover NV and western Kansas keep Mountain time.
if _node and "const ST_TZ = " in _html:
    _tz = _html[_html.index("const ST_TZ = "):_html.index("const TZ_FMT")]
    _r6 = subprocess.run([_node, "-e", _tz + r"""
const f = [], t = (st, lat, lon, want) => { const got = tzOf({ st, lat, lon }); if (got !== 'America/' + want) f.push(`${st} ${lat},${lon}: ${got}`); };
t('OR', 44.03, -116.96, 'Denver');      // Ontario, I-84
t('OR', 45.52, -122.68, 'Los_Angeles'); // Portland
t('OR', 44.77, -117.83, 'Los_Angeles'); // Baker City
t('NV', 40.73, -114.07, 'Denver');      // West Wendover, I-80
t('NV', 36.17, -115.14, 'Los_Angeles'); // Las Vegas
t('NV', 40.83, -115.76, 'Los_Angeles'); // Elko
t('KS', 39.35, -101.71, 'Denver');      // Goodland, I-70
t('KS', 37.98, -101.75, 'Denver');      // Syracuse, US-50
t('KS', 39.39, -101.05, 'Chicago');     // Colby
t('KS', 37.69, -97.34, 'Chicago');      // Wichita
console.log(f.length ? f.join("\n") : "OK");"""], capture_output=True, text=True)
    check(_r6.stdout.strip() == "OK", "tzOf() puts a stop in the wrong time zone:\n  " + (_r6.stdout + _r6.stderr).strip()[:300])

# The leaving time is part of a shared drive (2026-11-10): the recipient got "now" and other meals.
check("route && !route.hwy && typeof leavePick === 'number' ? p.set('leave', hhmm(leavePick))" in _html
      and re.search(r"(?m)^if \(leaveQ\) leavePick = \+leaveQ\[1\] \* 60 \+ \+leaveQ\[2\];", _html) is not None
      and "track('break-leave', ls.value || 'now'); render(); syncUrl();" in _html
      and "const hours = Array.from({ length: 24 }, (_, i) => i * 60);" in _html
      and "'leave'" in _html[_html.index("const VIEW_KEYS = ["):_html.index("const VIEW_KEYS = [") + 300],
      "the leaving time is not written to / read from the link again, or the picker lost hours")

# A break opens its stop even when the stop has no list row (only LIST_MAX render): LA -> New
# York had 17 of 23 break buttons doing nothing. tools/breaks_check.mjs taps every one.
_bk = _html[_html.index("querySelectorAll('[data-brk]').forEach("):][:520]
check("track('break-pick'); flyToStop(s, e.detail === 0);" in _bk and ".row[data-id" not in _bk,
      "a suggested break looks its stop up by list row again (dead buttons past the first 300 rows)")

# Dealership lots list after the public stations, under their own heading (not on a route).
_vs = _html[_html.index("function visibleSites()"):][:2000]
check("if (pub.length && dlr.length) return pub.concat(dlr);" in _vs and "if (!route && center) {" in _vs and 'class="lsep"' in _html,
      "dealership lots lead the list again ('tacos in phoenix' opened on two Nissan lots)")

# A chain with none in the area on screen does not leave an empty map there (2026-10-24):
# "in n out" with New York showing searched New York and stopped.
check("if (p.chains.length && !visibleSites().length)" in _html
      and "onFail: () => nearestFrom(was, what)" in _html
      and "else if (chainQuery() && !route && !visibleSites().length) nearestFrom(center" in _html,
      "a chain search that finds nothing in the current area no longer looks near you / nearest")
check('id="nearestX"' in _html and "function anyNear()" in _html,
      "the empty state lost 'Show the nearest' for a chain with nothing within 50 miles")

# Search audit 2026-10-24 (tools/search_audit.mjs):
# - a chain typed with a route on screen filters the route instead of locating and dropping it
_sq = _html[_html.index("  if (!p.place) {"):][:900]
check(re.search(r"^\s*if \(route && !p\.here\) \{", _sq, re.M) is not None,
      "a chain search with a route on screen drops the route again")
# - "<town> <ST>" is held to that state ("jackson ms" landed on a Houston middle school)
_gc = _html[_html.index("async function geocode(q)"):][:3200]
check("ranked = ranked.filter(h => (h.address && h.address.state) === wantState)" in _gc,
      "geocode no longer holds '<town> <ST>' to that state")
# - "dc" alone is Washington, not charger talk
check("if (t.trim() === 'dc' || t.trim() === 'd c') t = ' washington dc ';" in _html,
      "'dc' alone no longer means Washington, DC")

# Same-named towns: the one near you (or the area on screen), cached per region.
check("if (bias && !wantState && twins.length > 1)" in _html and "lsGet(GEO_NS, gk + cell, GEO_TTL)" in _html,
      "geocode no longer prefers the nearby one of several same-named towns")
# "from here to X" is a trip from your location.
check("/^(here|me|my location|current location|where i am|home|my house)$/.test(a.trim())" in _html,
      "'from here to X' is no longer a trip from your location")

# "<kind of place> in <town>" searches the town ("gym in miami" searched near the user).
check("const pw = poi && !p.here && !route && poi.name ? parseQuery(poi.name).place : '';" in _html
      and "const poiWhere = pw && (!nameFirst || knownPlace(poi.name) || knownPlace(pw)) ? pw : '';" in _html,
      "a category with a town ('pharmacy in denver') ignores the town again")
# ...and a name in front of the kind is not a town ("memorial hospital" went to Texas).
check("&& !rw.slice(ni, ki).some(w => /^(in|near|around|at)$/.test(w));" in _html,
      "'memorial hospital' / 'outlet mall' read the name as a town again")
# Named landmarks with a kind word in them ("central park" went to Central, Ohio).
check("async function findLandmark(phrase, near) {" in _html and "const lm = await findLandmark(phrase);" in _html,
      "'central park' / 'mall of america' are kinds of place again, not the landmark")
# A town whose name holds filler or charger talk, asked for with words around it (BUG-07/08/09):
# "great falls" did nothing, "college station tx" searched colleges in Texas.
check("const town = knownTown(t);\n  if (town) place = town;" in _html,
      "towns like 'great falls' / 'college station tx' lose their words to stripping again")
check("(w === 'great' && pw[i + 1]" in _html, "'great bend' goes to Bend, Oregon again")
# A station is a landmark (BUG-10): "union station" went to Union County, IL; "penn station la"
# to New Orleans. In a named town only when the town is named.
check("? stationAsked(raw, p.place) : null;" in _html and "at = await findLandmark(stn.name, near) || near;" in _html,
      "'union station' is read as the town 'union' again")
check("if (near && !(mi < 40)) continue;" in _html, "'penn station la' can land in New York again")
# A chain's own descriptor after its name ("starbucks reserve" went to Reserve, NM).
check("CHAIN_TAIL + '(\\\\s|$)'" in _html, "chain descriptors ('pilot travel center') are towns again")
# Brand names with punctuation: "pf changs" is P.F. Chang's (it flew to Boston).
check("const brandRe = n => '^(the )?'" in _html and ".replace(/^\\s*the\\s+/, '').replace(/[^a-z0-9]+/g, '')" in _html,
      "brand names with punctuation (P.F. Chang's, 7-Eleven) no longer match")
# A neighbourhood is labelled by its own name ("brooklyn" said "New York, NY", "east los
# angeles" said "Compton, CA").
check("/^(suburb|neighbourhood|quarter|borough|city_district)$/.test(j.addresstype || '')" in _html,
      "neighbourhoods are labelled with their city again (Brooklyn -> New York, NY)")
# Misspelled towns snap to a town we have ("pheonix" was a brand search, "sacremento" a farm road).
check("function placeTypo(q, minC = 5) {" in _html and "placeTypo(p.place, 15)" in _html,
      "misspelled towns ('pheonix', 'sacremento') are no longer corrected")
# Hits that echo nothing are dropped before choosing ("frisco" said Couldn't find).
check("ranked = ranked.filter(echoes);" in _html, "'frisco' (led by San Francisco in OSM) can't be found again")
# A bare name is the town, not the county ("pittsburg" went to Pittsburg County, OK).
check("if (isCounty(ranked[0]) && " in _html, "a bare town name goes to the county of that name again")
# Many shops of a name beat a hamlet of it ("marshalls" went to Marshalls, NY).
check("if (same.filter(isBusinessHit).length >= 3" in _html, "'marshalls' flies to a hamlet in New York again")
check("if (/\\b(national|state) (park|forest|monument|recreation area)\\b/.test(normalise(raw))) return null;" in _html,
      "'zion national park' is read as 'find parks' again")
check("!isState(h)" in _html, "a state counts as a same-named town again ('washington' -> middle of WA)")

# A category search's chains (pharmacy -> Walgreens, CVS) do not leak into the next search.
check("if (seedFor && !p.chains.length && !p.anyCat && !detectPoiIntent(raw)" in _html,
      "a category search's chains leak into the next search again ('lax' after 'pharmacy')")

# Tile seams at a half zoom step (UI-07): half a pixel of overlap, with normal blending so the
# overlap does not add up into a brighter line.
check(".leaflet-container img.leaflet-tile{mix-blend-mode:normal;width:256.5px!important;height:256.5px!important}" in _html,
      "map tiles show hairline seams at fractional zoom again")

# Brand names never break at their hyphen ("In-N-" / "Out" at 375 px, UI-05): in the app,
# and in the generated pages (regenerated by build.py).
check("const bname = s => /-/.test(s) ? `<span class=\"nw\">${esc(s)}</span>` : esc(s);" in _html
      and "...[...active].map(k => bemo(k) + ' ' + bname(k))];" in _html
      and "<span class=\"nm\">${bname(k)}</span>" in _html,
      "brand names in the app can break at their hyphen again ('In-N-' / 'Out')")
# ...and the name's own span is not styled as a chip of its own inside a row's chip.
check(".row .ch>span{background:var(--chew-bg)" in _html and ".brk .bt>span{" in _html,
      "a row's chain chip pads the brand name's .nw span as a second chip again")
_inno = os.path.join(HERE, "near/in-n-out/index.html")
check(not os.path.exists(_inno) or 'with an <span class="nw">In-N-Out</span> within' in open(_inno).read(),
      "near/ pages break 'In-N-Out' at its hyphen again (build.py bn())")

# The chain picker's count sits under the name (UI-06): beside it, it clipped "McDonald'".
check(".pkitem{display:grid;grid-template-columns:auto 1fr;grid-template-rows:auto auto;" in _html
      and ".pkitem .e{font-size:17px;grid-row:1/3;align-self:center}" in _html,
      "the chain picker clips names again (count beside the name instead of under it)")

# Accessibility (A11Y-01, UI-11): the breaks are a heading; the whole sheet header drags;
# Reduce Motion jumps instead of flying and turns off the zoom animations (both maps).
check('<h2 class="bh">${picks.length ? \'Suggested breaks\' : \'Your drive\'}' in _html,
      "'Suggested breaks' is no longer a heading")
check("for (const el of [$('handle'), document.querySelector('.sheethead')]) {" in _html,
      "only the 18 px handle drags the sheet again")
check("if (REDUCED_MOTION) map.setView([s.lat, s.lon], Math.max(map.getZoom(), 13), { animate: false });" in _html
      and "zoomAnimation: !REDUCED_MOTION, fadeAnimation: !REDUCED_MOTION," in _html
      and "zoomAnimation: !calm, fadeAnimation: !calm, markerZoomAnimation: !calm" in _html,
      "the map ignores Reduce Motion again")
check("$('handle').setAttribute('aria-expanded', s === 'peek' ? 'false' : 'true');" in _html,
      "the sheet handle no longer says whether the list is open")

# Your own location never goes into the address bar (BUG-06): a reload after moving pinned the
# map to the old spot. "near=1" instead; a link you send still carries the spot.
check("if (center && center.kind === 'me') { p.delete('at'); p.set('near', '1'); p.set('r', radiusMi); }" in _html,
      "syncUrl writes your own location into the URL again (a reload pins you to the old spot)")
check("if (center && center.kind === 'me' && u.searchParams.get('near') === '1') {" in _html,
      "a shared 'near me' link no longer carries where you were looking")
check("else if ((active.size || anyCat) && q.get('near') !== '1') { setSheet('mid'); fitToResults(); }" in _html,
      "reloading 'starbucks near me' shows the whole country instead of finding you again")

# ---- Robustness (BUG-15..19): every guard below matches a LIVE statement at its call site ----
def _live(stmt, n=1):
    return len(re.findall(r"(?m)^[ \t]*" + re.escape(stmt), _html)) == n

# A full quota (or a read-only private mode) must not throw out of a plain setItem (BUG-17):
# the shim swallows write failures; the two caches that make room on a quota error must still
# SEE it, so they write with setOrThrow (or their eviction is dead code).
check(_live("setItem: (k, v) => { try { s.setItem(k, v); return true; } catch (e) { return false; } },")
      and _live("return { getItem: k => { try { return s.getItem(k); } catch (e) { return null; } },"),
      "localStorage writes can throw again (a full quota breaks the star and the filters)")
check(_live("try { localStorage.setOrThrow(poiKey(body), s); }")
      and _live("localStorage.setOrThrow(poiKey(body), s);")
      and _live("const put = () => localStorage.setOrThrow(ns + fnv(key, 2166136261), body);"),
      "the Overpass / place / route caches no longer see a quota error, so they never make room")
# Saved filters and link values are pinned to what the controls offer (BUG-18/19).
check(_live("let F = cleanFilters(Object.assign({}, FDEF, readJSON('cc_filters', {}, isPlainObj)));")
      and _live("F = cleanFilters(F);")
      and "const FALLOW = { kw: [0, 50, 150, 250, 350], stalls: [0, 2, 4, 8], plug: [0, 1, 2, 4] };" in _html,
      "saved filters are used unchecked again ('x+ kW', '205 undefined chargers')")
check(_live("corridorMi = corridorFrom(q.get('c'));")
      and _live("if (q.get('c')) corridorMi = corridorFrom(q.get('c'));")
      and "const corridorFrom = v => [2, 5, 10].includes(+v) ? +v : 5;" in _html
      and not re.search(r"corridorMi = \+q\.get\('c'\)", _html),
      "c= in a link is used unchecked again ('0 chargers within -5 mi')")
# r= is pinned the same way, from a link and from a saved area.
check(_live("radiusMi = radiusFrom(q.get('r'));")
      and _live("if (a.r) { radiusMi = radiusFrom(a.r); $('ccRad').querySelectorAll('button')")
      and "const radiusFrom = v => [10, 25, 50].includes(+v) ? +v : 25;" in _html
      and not re.search(r"radiusMi = \+q\.get\('r'\)", _html),
      "r= in a link is used unchecked again (a search within -5 miles, no radius button lit)")
# Offline is said as offline, not "OpenStreetMap is busy" with pointless retries (BUG-16).
check(_live("if (isOffline()) { const e = new Error(OFFLINE_MSG); e.offline = true; throw e; }")
      and _live("if (isOffline()) { e.offline = true; throw e; }")
      and _live("const off = e.offline || isOffline();")
      and _live("throw new Error(isOffline() ? OFFLINE_MSG : e && e.name === 'AbortError'"),
      "offline lookups say 'busy' / 'network problem' again instead of 'You're offline'")
# The x on a route goes back to the area before it (BUG-15).
check(_live("noteRouteFrom(); clearCenter();", 2)
      and _live("if (back) setCenter(back.lat, back.lon, back.label, back.kind);")
      and _live("const back = goBack ? routeFrom : null;")
      and "$('rClear').onclick = e => { e.stopPropagation(); dropRoute(true);" in _html,
      "clearing a route drops you on the national view again instead of the area before it")

# Map tiles are requested with CORS on the web (BUG-21): without it every tile is opaque and the
# service worker, which must not cache what it cannot measure, never stored one. Both providers'
# options carry it, and every tile layer (early map and app) is built from those options.
check(_html.count("crossOrigin: window.CC_TILE_CORS },") == 2
      and _live("window.CC_TILE_CORS = /^https?:$/.test(location.protocol);")
      and _html.count("{ ...bm.opts, alt: '' }") == 2 and _html.count("Object.assign({}, bm.opts, { alt: '' })") == 2,
      "map tiles are requested without CORS again, so the service worker can never cache one")

# ---- Sheet rhythm (UI-08..12/14/15/16) ----
# One 16 px gutter: title, area line, chips, breaks card and rows all start on it (they were at
# 12/14/15/18/24 px). Rows carry no side padding of their own, on phone and desktop.
check("--gutter:16px;" in _html
      and ".sheethead{display:flex;align-items:center;gap:9px;padding:0 var(--gutter) 10px;flex-shrink:0}" in _html
      and "#list{overflow-y:auto;overscroll-behavior:contain;padding:0 var(--gutter) calc(16px + env(safe-area-inset-bottom));flex:1}" in _html
      and "#app.phone #sheet .chiprow{padding:2px var(--gutter) 7px;" in _html
      and "#app.phone #sheet #centerCard.show{margin:-2px var(--gutter) 6px;padding:0;" in _html
      and "display:flex;gap:12px;padding:15px 0;border-radius:0;" in _html
      and "  .row{padding:15px 0}" in _html and "  .row{padding:14px 0}" in _html
      and ".breaks{margin:0 0 6px;padding:10px 0 6px;" in _html
      and ".brk{display:flex;align-items:center;gap:12px;width:100%;text-align:left;padding:9px 0;" in _html,
      "the sheet's left edges are off the 16 px gutter again (UI-08)")
# The fade beside "+ All chains" is wide enough to hide a chip's icon (UI-09), and it is one
# smooth gradient in the row's own colour with no edges: the chip sits in a sticky .moreend
# whose backing runs under the whole chip and past the row's top and bottom (clipped by the
# row). A fade 4 px taller than the chip, beside it only, drew a box, and chips showed past
# the chip's round corners (light and dark, 375 px).
check(re.search(r"\+ `<span class=\"moreend\"><button class=\"chip more\" id=\"moreChip\">＋ All chains</button></span>`;", _html) is not None
      and ".moreend::before{content:'';position:absolute;z-index:-1;top:-40px;bottom:-40px;left:-48px;right:0;" in _html
      and "background:linear-gradient(to right,transparent,var(--surface) 40px)}" in _html
      and ".chip.more{border-style:dashed;color:var(--txt);background:var(--surface);" in _html
      and "#app.phone #sheet .chiprow .moreend::before{right:calc(-1 * var(--gutter) - 1px)}" in _html,
      "the fade beside '+ All chains' has hard edges again, or chips show past the chip's corners (UI-09)")
# Phone chips are 44 px to tap (UI-11): the phone rule used to beat the coarse 44 px one with 40.
check("#app.phone #sheet .chiprow .chip{height:44px;" in _html and "#app.phone #sheet .chiprow .chip{height:40px" not in _html,
      "phone chips are under 44 px tall again (UI-11)")
# Every :hover rule sits inside @media(hover:hover): on touch a tapped row stayed highlighted (UI-12).
_hov = [l.strip()[:60] for l in _html.splitlines() if ":hover" in l and "@media(hover:hover)" not in l]
check(not _hov, f"a :hover rule applies on touch screens again (sticky highlight, UI-12): {_hov[:2]}")
# One badge vocabulary (UI-14): status tags are one outline style, "1 stall" is plain text.
check(".tag{display:inline-block;margin-left:6px;padding:0 6px;border-radius:6px;font-size:10.5px;font-weight:700;line-height:1.6;\n  background:transparent;color:var(--dim);box-shadow:inset 0 0 0 1px var(--line2)}" in _html
      and ".tag.free{color:var(--good)}" in _html and ".tag.iso{" not in _html and ".tag.dlr{" not in _html
      and ".tag.one{box-shadow:none;padding:0;" in _html,
      "row badges are back to several different treatments (UI-14)")
# The radius says its unit on a phone (UI-10).
check('<button data-mi="50" aria-label="50 miles">50</button><span class="u" aria-hidden="true">mi</span>' in _html,
      "the area radius control has no unit again (UI-10)")
# An off switch is a quiet track, not mid grey that reads as lit in dark (UI-15).
check("rgba(0,0,0,.22) 7px,transparent 8px),var(--line2);transition:background .15s}" in _html
      and "transparent 7px),var(--dim2);transition" not in _html,
      "an off switch looks lit in dark mode again (UI-15)")
# About's chain and trip chips are ink, not charging green (UI-16).
check(_live("#about .chainlinks a{color:var(--txt)}"),
      "About's chain chips are green again (green means charging, UI-16)")

# Planned at night, the drive leaves at 8 am the coming morning (2026-11-11): "now" at 10 pm made
# "12:10 am Break, next day" the first plan. tools/breaks_check.mjs plays it in the app with a
# moved clock; this pins the rule and that the planner, the picker and the link all use it.
_lv = _html[_html.index("const NIGHT_FROM = "):_html.index("function leaveOf(")]
if _node:
    _r7 = subprocess.run([_node, "-e", _lv.split("\nconst startMin")[0] + r"""
const f = [], t = (h, m, drive, want) => { if (nightPlan(h * 60 + m, drive) !== want) f.push(`${h}:${m} drive ${drive} min: ${!want}`); };
t(22, 30, 240, true); t(1, 30, 240, true); t(4, 59, 600, true); t(20, 0, 300, true);
t(20, 30, 120, false);   // over by 11 pm: tonight's
t(5, 0, 240, false); t(14, 0, 240, false); t(19, 59, 600, false);
console.log(f.length ? f.join("\n") : "OK");"""], capture_output=True, text=True)
    check(_r7.stdout.strip() == "OK", "the night departure rule is wrong:\n  " + (_r7.stdout + _r7.stderr).strip()[:300])
check("return nightNow(first) ? morningOf(first) : null;" in _html
      and "const now = Date.now(), L = first ? leaveOf(first) : null;" in _html
      and "(night || leavePick === 'm' ? `<option value=\"m\"${morning ? ' selected' : ''}>${morningLabel(first)}</option>` : '') +" in _html
      and _live("else if (q.get('leave') === 'now') leavePick = 'now';   // a link's leaving time beats the night default"),
      "a drive planned at night leaves 'now' again (the default must be 8 am the coming morning, now one tap away)")

# Port-split listings of one site are one stop (2026-11-11): a route through Los Angeles opened on
# four "City_Of_Vernon 1850 E25Th-..." rows. build_data.merge_ports() merges them (stalls add up);
# no two listings in data.js may still match its rule.
check(re.search(r"(?m)^\s*deduped, stats\[\"ports\"\] = merge_ports\(deduped\)", _bd) is not None,
      "build_data.py no longer merges port-split listings of one site")
if D:
    sys.path.insert(0, os.path.join(HERE, "data"))
    from build_data import _same_site
    _grid = {}
    for _s in D["sites"]:
        _grid.setdefault((int(_s["lat"] * 200), int(_s["lon"] * 200)), []).append(_s)
    _split = []
    for _s in D["sites"]:
        _c = (int(_s["lat"] * 200), int(_s["lon"] * 200))
        for _di in (-1, 0, 1):
            for _dj in (-1, 0, 1):
                _split += [(_s["name"], _t["name"]) for _t in _grid.get((_c[0] + _di, _c[1] + _dj), ())
                           if _t["id"] > _s["id"] and _same_site(_s, _t)]
    check(not _split, f"{len(_split)} port-split listings of one site are separate stops again, e.g. {_split[:2]}")
# A route lists the best stop per ~30-minute stretch, with "Show all N stops" below (2026-11-11).
# tools/breaks_check.mjs plays it (short list, one per stretch, show all, back, break taps).
check(_live("const full = route && routeAllFor === route, col = full ? null : bestPerStretch(vis);")
      and _live("const rows = col ? col.rows : vis.slice(0, LIST_MAX);")
      and "<button type=\"button\" class=\"listmore\" id=\"routeAll\">Show all ${vis.length.toLocaleString()} stops</button>" in _html
      and _live("routeAllFor = route; track('route-all'); render();"),
      "the route list is every stop again (it should be the best per stretch, with Show all below)")
# Share on a drive sends the plan as text with the /trip/ guide (or the app) marked ref=share
# (2026-11-11). tools/breaks_check.mjs checks the text and links; this pins the wiring, and that
# the guide list build.py writes into index.html is exactly the trip pages that exist.
_tp = re.search(r"const TRIP_PAGES = '([^']*)';", _html)
_trips_on_disk = sorted(d for d in os.listdir(os.path.join(HERE, "trip")) if os.path.isfile(os.path.join(HERE, "trip", d, "index.html")))
check(_tp is not None and _tp.group(1).split() == _trips_on_disk,
      "index.html's TRIP_PAGES does not list the /trip/ guides that exist (run build.py)")
check(_live("const plan = sharePlan();") and "url = `https://chargeandchew.com/trip/${sl}/?ref=share`;" in _html
      and _live("u.searchParams.set('ref', 'share');")
      and "native('share', plan ? { url, title: 'Charge & Chew', text: plan.text } : { url, title: 'Charge & Chew' });" in _html
      and "navigator.share(plan ? { title: 'Charge & Chew', text: plan.text, url }" in _html
      and _live("if (plan) track('share-plan');"),
      "sharing a drive sends a bare link again (it should send the plan as text, with the trip guide)")
check("const TRIP_PAGES = '" in open(os.path.join(HERE, "build.py")).read(),
      "build.py no longer writes the trip-guide list into index.html")
# The rating ask (2026-11-11): after a planned drive and a Directions tap, at most once per app
# version, when the app is back from Maps -- not "5 stop cards on 2 days", which never fired.
# tools/breaks_check.mjs plays the page half with the shell stubbed.
_wvc2 = open(os.path.join(HERE, "ios", "ChargeAndChew", "WebViewController.swift")).read()
_nb2 = open(os.path.join(HERE, "ios", "ChargeAndChew", "NativeBridge.swift")).read()
check(_live("if (dir) dir.addEventListener('click', askReview);")
      and _live("if (!NATIVE || !route || route.hwy) return;")
      and "function noteUse" not in _html and "cc_opens" not in _html,
      "the rating ask is not tied to Directions on a planned drive again")
check(re.search(r'<span class="app-only"> ·\s*<a href="https://apps\.apple\.com/app/id6809134093\?action=write-review"', _html) is not None
      and "html:not(.native) .app-only{display:none}" in _html,
      "About lost 'Rate the app' in the iOS app (or shows it on the web)")
check("bridge.onReview = { [weak self] in self?.reviewAfterDirections() }" in _wvc2
      and re.search(r"guard UserDefaults\.standard\.string\(forKey: Self\.reviewVersionKey\) != appVersion else", _wvc2) is not None
      and re.search(r"UserDefaults\.standard\.set\(appVersion, forKey: Self\.reviewVersionKey\)\s*\n\s*Diag\.log\(\"review: requested", _wvc2) is not None
      and "AppStore.requestReview(in: scene)" in _wvc2
      and "selector: #selector(appBecameActive)" in _wvc2,
      "the iOS shell asks for a rating more than once per version, or not after the return from Maps")
check('if host == "apps.apple.com" { UIApplication.shared.open(url); return }' in _wvc2,
      "'Rate the app' opens a web page in a Safari sheet instead of the App Store")
check('onShare?(url, opts["title"] as? String ?? "Charge & Chew", opts["text"] as? String)' in _nb2
      and "if let plan { items.append(PlanText(text: plan, url: url)) }" in _wvc2,
      "the iOS share sheet drops the plan text again (link only)")
# Copy put text and link on the pasteboard as two items, and a paste takes the first: the plan
# arrived without its link (seen on the simulator: pbpaste had the text only). For Copy the
# text carries the link and the link item steps aside.
check('t == .copyToPasteboard ? text + "\\n" + url.absoluteString : text' in _wvc2
      and "inText && t == .copyToPasteboard ? nil : url" in _wvc2
      and "items.append(ShareItem(url: url, title: title, inText: plan != nil))" in _wvc2,
      "iOS Copy on a shared plan puts the link on the pasteboard as a second item (a paste drops it)")
# Dialogs take focus themselves on open (2026-11-11). Focusing the first control drew the
# keyboard ring on the welcome card's x before any key was pressed: a square sticking out past
# the card's round corner. The x's own ring is drawn inside it, rounded.
check(_live("if (!el.contains(document.activeElement)) { el.tabIndex = -1; el.focus({ preventScroll: true }); }")
      and "const f = focusables(el)[0]; if (f) f.focus(" not in _html
      and "[role=dialog]:focus{outline:none}" in _html
      and re.search(r"\.herocard \.x:focus-visible\{outline-offset:-[4-9]px;border-radius:\d+px\}", _html) is not None
      and "(e.shiftKey && document.activeElement === $(d.id) ? last : first).focus();" in _html,
      "a dialog focuses its first control on open again (the welcome card's x shows a square ring)")
# A /trip/ page's stop link (?from&to&leave&stop=) opens the stop once the drive is planned,
# leading with the chain the plan promised, as a tap (2026-11-11). tools/trip_plan_check.mjs
# opens every such link; this pins the wiring.
check(_live("Promise.resolve(first ? first() : null).then(() => setTimeout(() => {")
      and _live("if (pick && pick.k) popupLead = { id: sid, k: pick.k };")
      and _live("if (row) return row.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 1 }));"),
      "?stop= opens the stop before the drive is planned again, or as a key press (focus ring)")
# The welcome card's example drives are two by two at every width (verify pass, 2026-11-11):
# four in a row ("LA → Vegas ... Dallas → Houston") ran 29 px past the card's padding from
# 441 px up, out past the card's edge, and 84 px at 441 px.
check(".heroex{display:grid;grid-template-columns:1fr 1fr;" in _html
      and not re.search(r"\.heroex\{[^}]*grid-template-columns:repeat\(4", _html),
      "the welcome card's example drives sit four in a row again (they run past the card above 440 px)")
# ...and on the generated pages too (verify pass, 2026-11-11): ".card .c span" also styled the
# name's own .nw span inside a chip, so "Chick-fil-A" and "In-N-Out" were a chip within a chip
# (9 px of extra padding each side) on every /near/ and /trip/ card that names them.
_pcss, _bpy = open(os.path.join(HERE, "assets/pages.css")).read(), open(os.path.join(HERE, "build.py")).read()
check(all(".card .c>span{background:var(--chew-bg)" in t and ".card .c span{" not in t for t in (_pcss, _bpy)),
      "a /near/ or /trip/ chip pads the brand name's .nw span as a chip of its own again")
# A drive from "Your location" is from=me in the address bar, not its coordinates: a reload
# after moving showed "Dropped pin" at the old spot. A reload locates again; a sent link carries
# the spot. Behaviour is checked by tools/breaks_check.mjs (the "me -> Bakersfield" case).
check(re.search(r"(?m)^\s*else if \(route\) \{ p\.delete\('hwy'\); p\.set\('from', routeFromMe && LATLON\.test\(\$\('fromIn'\)\.value\.trim\(\)\) \? 'me' :", _html) is not None,
      "syncUrl writes the device location into from= again (a reload shows a Dropped pin there)")
check(re.search(r"(?m)^\s*if \(u\.searchParams\.get\('from'\) === 'me' && routeFromMe\) u\.searchParams\.set\('from', \$\('fromIn'\)\.value\.trim\(\)\);", _html) is not None,
      "a shared drive from 'Your location' sends from=me, which starts at the RECIPIENT's location")
check(re.search(r"(?m)^\s*boot = fromMe \? \(\) => locate\('route', \{ thenRoute:", _html) is not None,
      "reopening a from=me drive no longer locates you (it would plan from a place called 'me')")

# The update toast is for a page older than its worker only (the first visit after a deploy
# is already the new page: network-first). The page compares its SW_VER with the worker's
# VERSION, so the two must move together.
_swv = re.search(r"const VERSION = '([^']+)';", open(os.path.join(HERE, "sw.js")).read())
_pgv = re.search(r"(?m)^const SW_VER = '([^']+)';", _html)
check(_swv and _pgv and _swv.group(1) == _pgv.group(1),
      f"index.html SW_VER ({_pgv and _pgv.group(1)}) is not sw.js VERSION ({_swv and _swv.group(1)}): bump both together")
check(re.search(r"(?m)^\s*ch\.port1\.onmessage = e => \{ if \(e\.data !== SW_VER\) offerUpdate\(w\); \};\n\s*w\.postMessage\('version', \[ch\.port2\]\);", _html) is not None,
      "the update toast no longer asks the new worker its version (the new page offers itself a reload)")

# About: the x sits in a header that stays put on the sheet's own background. A lone sticky x
# floated over the body text, which ran under and around it while scrolling (web and iOS).
check(re.search(r'<div class="abhead"><h2>.*?</h2>\s*<a class="xclose"[^>]*>.*?</a></div>', _html, re.S) is not None,
      "About's close button is not inside its header (it floated over the text again)")
_abh = re.search(r"#about \.abhead\{([^}]*)\}", _html)
check(_abh and "position:sticky" in _abh.group(1) and "background:var(--surface)" in _abh.group(1) and "top:-24px" in _abh.group(1),
      "About's header is not a sticky, opaque bar at the top edge (text shows under the x)")
check(not re.search(r"#about \.xclose\{[^}]*position:sticky", _html), "About's x is sticky on its own again")
check(re.search(r"(?m)^\s*\$\('about'\)\.querySelector\('\.abhead'\)\.classList\.toggle\('scrolled', e\.target\.scrollTop > 2\)", _html) is not None,
      "About's header no longer draws its hairline when text scrolls under it")

# A stop card opened from a break leads with the chain the plan promised; its tip ("23 min
# here — time for ...") follows it, or says it is tight for it. Behaviour: breaks_check.
_dw = _html[_html.index("function dwellAdvice("):_html.index("function dwellAdvice(") + 2500]
check(re.search(r"(?m)^\s*const lead = leadAt\(s\);", _dw) and "((b.k === lead) - (a.k === lead)) ||" in _dw
      and re.search(r"(?m)^\s*if \(lead && m\[lead\] !== undefined && \(!opts\.length \|\| opts\[0\]\.k !== lead\)\) \{", _dw),
      "the stop card's tip no longer follows the chain the plan promised there")

# ---- the Road Food Index (2026-11-11): every number reproducible from the data ----
# tools/road_food_index.py is run again here, independently of build.py, and the page and its
# CSVs must say exactly what it says. A press page with a stale or hand-edited number is worse
# than none: journalists quote it.
_rfi_page = os.path.join(HERE, "road-food-index", "index.html")
check(os.path.exists(_rfi_page), "the Road Food Index page is missing (run build.py)")
if os.path.exists(_rfi_page):
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import road_food_index as _rfi
    from html import unescape as _unesc
    _R = _rfi.compute(HERE)
    _rh = open(_rfi_page, encoding="utf-8").read()
    _rtext = _unesc(re.sub(r"<[^>]+>", "", _rh))
    for _name in _rfi.TABLES:
        _cf = os.path.join(HERE, "road-food-index", f"{_name}.csv")
        check(os.path.exists(_cf) and open(_cf, encoding="utf-8").read() == _rfi.csv_text(_R, _name),
              f"road-food-index/{_name}.csv differs from what tools/road_food_index.py computes (run build.py)")
        check(f'href="{_name}.csv"' in _rh, f"the Road Food Index does not link its {_name}.csv")
    _hl = _rfi.headlines(_R)
    _miss = [x for x in _hl if x not in _rtext]
    check(len(_hl) >= 3 and not _miss, f"Road Food Index findings differ from the data: {_miss[:1]}")
    # every table row the page shows carries the computed numbers
    for _c in _R["chains"][:25]:
        check(f'{_c["sites"]:,}</td><td class="n">{_c["share"]}%' in _rh, f"chain row for {_c['chain']} differs from the data")
    for _x in _R["interstates"]:
        check(f'>{_x["interstate"]}</a></td><td class="n opt">{_x["miles"]:,}</td><td class="n opt">{_x["chargers"]:,}</td><td class="n">{_x["food_share"]}%' in _rh,
              f"interstate row for {_x['interstate']} differs from the data")
    for _s in [s for s in _R["states"] if s.get("rank")]:
        check(f'<td class="">{_s["state"]}</td><td class="n opt">{_s["sites"]:,}</td><td class="n">{_s["food_share"]}%' in _rh,
              f"state row for {_s['state']} differs from the data")
    # One definition each: the interstate counts are the /along/ pages' own, and each drive's gap
    # is the one its /trip/ page states.
    for _x in _R["interstates"]:
        _ap = os.path.join(HERE, "along", _x["slug"], "index.html")
        _am = re.search(r"<b>([\d,]+) DC fast chargers</b> sit within", open(_ap, encoding="utf-8").read()) if os.path.exists(_ap) else None
        check(_am is not None and int(_am.group(1).replace(",", "")) == _x["chargers"],
              f"Road Food Index counts {_x['chargers']} chargers on {_x['interstate']}, its /along/ page {_am.group(1) if _am else 'nothing'}")
    _tbad = []
    for _d in _R["drives"]:
        _tp = os.path.join(HERE, "trip", _d["slug"], "index.html")
        _th = open(_tp, encoding="utf-8").read() if os.path.exists(_tp) else ""
        _want = (f"the longest stretch without one is <b>{_d['gap']} miles</b>" if _d["gap"] >= 60
                 else f"one at least every <b>{max(_d['gap'], 1)} miles</b>")
        if _want not in _th:
            _tbad.append(_d["slug"])
    check(not _tbad, f"{len(_tbad)} drives' gaps on the Road Food Index differ from their /trip/ pages: {_tbad[:3]}")
    # Dataset markup that matches the page
    _ds = [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', _rh, re.S)]
    _ds = [x for x in _ds if x.get("@type") == "Dataset"]
    check(len(_ds) == 1, "the Road Food Index has no Dataset structured data")
    if _ds:
        _d0 = _ds[0]
        _h1 = re.search(r"<h1>(.*?)</h1>", _rh, re.S)
        _md = re.search(r'<meta name="description" content="([^"]*)"', _rh)
        check(_h1 and _unesc(_h1.group(1)) == _d0.get("name"), "Dataset name is not the page's h1")
        check(_md and _unesc(_md.group(1)) == _d0.get("description"), "Dataset description is not the page's description")
        check(_d0.get("dateModified") == D.get("generated"), "Dataset dateModified is not the data's date")
        _dl = _d0.get("distribution", [])
        check(len(_dl) == len(_rfi.TABLES) and all(
            os.path.exists(os.path.join(HERE, x["contentUrl"].split("chargeandchew.com/", 1)[-1])) for x in _dl),
            "Dataset distribution does not list the CSVs that exist")
        check(all(x in _rtext for x in ("AFDC", "OpenStreetMap", "How to cite")), "the Road Food Index lost its sources or citation line")
    # llms.txt (for AI answer engines): this week's numbers, the same findings, links that resolve
    _lt = os.path.join(HERE, "llms.txt")
    check(os.path.exists(_lt), "llms.txt is missing (run build.py)")
    if os.path.exists(_lt):
        _ll = open(_lt, encoding="utf-8").read()
        check(f"{_R['n_sites']:,} DC fast-charger sites, {_R['n_food']:,} of them" in _ll,
              "llms.txt's charger counts differ from the data")
        check(all(x in _ll for x in _hl), "llms.txt's findings differ from the Road Food Index's")
        _lbad = [u for u in re.findall(r"\(https://chargeandchew\.com/([^)]*)\)", _ll)
                 if not os.path.exists(os.path.join(HERE, u, "index.html") if u.endswith("/") or not u else os.path.join(HERE, u))]
        check(len(re.findall(r"\(https://chargeandchew\.com/", _ll)) >= 5 and not _lbad, f"llms.txt links pages that do not exist: {_lbad[:3]}")
        check('"llms.txt"' in open(os.path.join(HERE, "publish.py"), encoding="utf-8").read(), "publish.py does not publish llms.txt")
    check("/road-food-index/" in open(os.path.join(HERE, "sitemap.xml"), encoding="utf-8").read(),
          "the Road Food Index is not in the sitemap")
    check('"road-food-index"' in open(os.path.join(HERE, "publish.py"), encoding="utf-8").read(),
          "publish.py does not publish road-food-index/")

# ---- city pages /in/<city>/ (2026-11-11) ----
# Recounted here from data/metros.json the way the app's area view counts (planner.hav within
# 25 * planner.MI): a page that says "79 DC fast chargers" must open the map on 79.
_mj = os.path.join(HERE, "data", "metros.json")
_cidx = os.path.join(HERE, "in", "index.html")
check(os.path.exists(_mj) and os.path.exists(_cidx), "the city pages or data/metros.json are missing (run build.py)")
if os.path.exists(_mj) and os.path.exists(_cidx):
    import planner as _pl
    from html import unescape as _unesc2
    _bp2 = open(os.path.join(HERE, "build.py"), encoding="utf-8").read()
    _cmi = int(re.search(r"(?m)^CITY_MI = (\d+)", _bp2).group(1))
    _cmin = re.search(r"(?m)^CITY_INDEX_MIN = (\w+)", _bp2).group(1)
    _cmin = int(re.search(rf"(?m)^{_cmin} = (\d+)", _bp2).group(1)) if not _cmin.isdigit() else int(_cmin)
    _food_k = {k for k, v in D["brands"].items() if v.get("cat") == "food"}
    _kept, _skip = [], []
    for _m in json.load(open(_mj))["metros"]:
        _sl = re.sub(r"[^a-z0-9]+", "-", _m["name"].lower()).strip("-") + "-" + _m["st"].lower()
        if any(_pl.hav(_m["lat"], _m["lon"], o["lat"], o["lon"]) <= _cmi * _pl.MI for o in _kept + [x for x in _skip if x.get("thin")]):
            _skip.append(dict(_m, sl=_sl)); continue
        _in = [s for s in D["sites"] if abs(s["lat"] - _m["lat"]) < 0.5 and _pl.hav(_m["lat"], _m["lon"], s["lat"], s["lon"]) <= _cmi * _pl.MI]
        _fd = [s for s in _in if _food_k & set(D["matches"].get(str(s["id"]), {}))]
        if len(_fd) < _cmin:
            _skip.append(dict(_m, sl=_sl, thin=True)); continue
        _kept.append(dict(_m, sl=_sl, n=len(_in), f=len(_fd), kw=max((s.get("kw") or 0) for s in _fd)))
    _ci = open(_cidx, encoding="utf-8").read()
    _smx = open(os.path.join(HERE, "sitemap.xml"), encoding="utf-8").read()
    check(len(_kept) >= 80, f"only {len(_kept)} city pages")
    _cbad = []
    for _c in _kept:
        _f = os.path.join(HERE, "in", _c["sl"], "index.html")
        if not os.path.exists(_f):
            _cbad.append(f"{_c['sl']}: no page"); continue
        _h = open(_f, encoding="utf-8").read()
        if f"<b>{_c['n']:,} DC fast chargers</b> sit within {_cmi} miles" not in _h or f"<b>{_c['f']:,}</b> of them have somewhere to eat" not in _h:
            _cbad.append(f"{_c['sl']}: counts"); continue
        if f'?at={_c["lat"]:.4f},{_c["lon"]:.4f}&amp;r={_cmi}"' not in _h:
            _cbad.append(f"{_c['sl']}: map link"); continue
        _k1 = re.search(r'<s class="spd[^"]*">(\d+) kW</s>', _h)
        if not _k1 or int(_k1.group(1)) != _c["kw"]:
            _cbad.append(f"{_c['sl']}: first stop is not the fastest"); continue
        if f'href="{_c["sl"]}/"' not in _ci or f"/in/{_c['sl']}/</loc><lastmod>" not in _smx or "noindex" in _h:
            _cbad.append(f"{_c['sl']}: not in the index or sitemap, or noindexed"); continue
        # the FAQ markup says exactly what the page shows
        _vis = [(_unesc2(re.sub(r"<[^>]+>", "", q)), _unesc2(re.sub(r"<[^>]+>", "", a)))
                for q, a in re.findall(r"<details><summary>(.*?)</summary><p>(.*?)</p></details>", _h, re.S)]
        _faq = next((json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', _h, re.S)
                     if '"FAQPage"' in x), None)
        if not _faq or len(_vis) < 4 or [(e["name"], e["acceptedAnswer"]["text"]) for e in _faq["mainEntity"]] != _vis:
            _cbad.append(f"{_c['sl']}: FAQ markup differs from the visible FAQ"); continue
    check(not _cbad, f"{len(_cbad)} city pages are wrong: {_cbad[:3]}")
    _pub = [x["sl"] for x in _skip if os.path.exists(os.path.join(HERE, "in", x["sl"], "index.html"))]
    check(not _pub, f"skipped (thin or overlapping) cities still have pages: {_pub[:3]}")
    _nin = len(re.findall(r"<loc>https://chargeandchew\.com/in/", _smx))
    check(_nin == len(_kept) + 1, f"sitemap lists {_nin} /in/ URLs for {len(_kept)} cities + the index")
    # linked from where a reader already is
    _ihx = os.path.join(HERE, "near", "ihop", "tx", "index.html")
    check(not os.path.exists(_ihx) or '../../../in/austin-tx/' in open(_ihx, encoding="utf-8").read(),
          "a chain's state page no longer links that state's city pages")
    _tda = os.path.join(HERE, "trip", "dallas-to-austin", "index.html")
    check(not os.path.exists(_tda) or '../../in/austin-tx/' in open(_tda, encoding="utf-8").read(),
          "a trip page no longer links the city pages it starts and ends in")
    check("<!--cities-->" not in open(_tda, encoding="utf-8").read() if os.path.exists(_tda) else True,
          "the cities placeholder was left in a trip page")

# ---- discoverability (2026-11-11): the Road Food Index and the city pages are linked from
# every generated page's footer, the app's About, the section indexes and each interstate page.
_gen = (glob.glob(os.path.join(HERE, "near/**/index.html"), recursive=True) +
        glob.glob(os.path.join(HERE, "along/**/index.html"), recursive=True) +
        glob.glob(os.path.join(HERE, "trip/**/index.html"), recursive=True) +
        glob.glob(os.path.join(HERE, "in/**/index.html"), recursive=True))
_nofoot = [os.path.relpath(p_, HERE) for p_ in _gen
           if not re.search(r'<footer>[^<]*(?:<a[^>]*>[^<]*</a>[^<]*)*<a href="(?:\.\./)*road-food-index/">Road Food Index</a> · <a href="(?:\.\./)*in/">Cities</a>',
                            open(p_, encoding="utf-8").read())]
check(len(_gen) > 2000 and not _nofoot, f"{len(_nofoot)} generated pages lack the Road Food Index / Cities footer links: {_nofoot[:2]}")
_ab = _html[_html.find('<div id="about"'):_html.find('<div id="offlineBar"')]
check('<a href="road-food-index/">' in _ab and '<a href="in/">' in _ab, "About no longer links the Road Food Index and the city pages")
# (the footer links these too, so match the index's own links, not any href)
for _ix, _want in (("trip/index.html", ('<a href="../road-food-index/">the Road Food Index', '<a href="../in/">Fast chargers near food')),
                   ("along/index.html", ('<a href="../road-food-index/#interstates">Road Food Index</a> ranks every',)),
                   ("near/index.html", ('<a class="cta sec" href="../in/">',))):
    _t = open(os.path.join(HERE, _ix), encoding="utf-8").read()
    check(all(w in _t for w in _want), f"{_ix} lost its link to {_want}")
if os.path.exists(_rfi_page):
    _ordn = lambda n: f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
    _abad = []
    for _x in _R["interstates"]:
        _t = open(os.path.join(HERE, "along", _x["slug"], "index.html"), encoding="utf-8").read()
        if (f"{_x['interstate']} ranks <b>{_ordn(_x['rank'])}</b> of {len(_R['interstates'])} interstates for food: "
                f"<b>{_x['food_share']}%</b>") not in _t or "<!--rfi-->" in _t:
            _abad.append(_x["slug"])
    check(not _abad, f"{len(_abad)} interstate pages state a Road Food Index rank that differs from the data: {_abad[:3]}")

# ---- Stop signals (batch 8) ----
# Each signal is shown where it is computed: the guards match the live call sites, and a node run
# of the real block checks what each one says (and that it says nothing it cannot back).
_sg0, _sg1 = _html.find("const LATE = new Set(["), _html.find("function breakPicks(vis) {")
check(_sg0 > 0 and _sg1 > _sg0, "the stop-signal block (LATE ... breakPicks) is missing")
_SIG = _html[_sg0:_sg1] if _sg0 > 0 and _sg1 > _sg0 else ""
_pp = _html[_html.index("function popupHtml(s) {"):_html.index("function popupHtml(s) {") + 12000]
check(re.search(r"\n    \$\{cardSigs\(s\)\}\n    <div class=\"pp-links\">", _pp) is not None,
      "the stop card no longer shows its signal line (cardSigs)")
check(re.search(r"<span class=\"tag iso\">isolated</span>' : ''\}\$\{rowSigs\(s\)\}</div>", _html) is not None,
      "list rows no longer carry their signal tags (rowSigs)")
check("' min' + (acrossHwy(s, k) ? ' · across hwy' : '') : ''}</span>${brkSigs(s, k, ms)}</span>" in _html,
      "a planned break no longer says what is likely open at its clock (brkSigs)")
check(re.search(r"(?m)^  if \(stop\) lateByHours\(el, stop, todo, tz\);$", _html) is not None,
      "the stop card's late-food line is no longer put right by OpenStreetMap hours (lateByHours)")
check("const r = lateKeysByHours(b ? (b.dataset.keys || '').split('|').filter(Boolean) : []," in _html
      and "window.__lateKeysByHours = lateKeysByHours;" in _html,
      "lateByHours no longer asks lateKeysByHours (the rule verify_hours.py tests)")
if _node and _SIG:
    _rsig = subprocess.run([_node, "-e", r"""
let MIN = 0; const BRANDS = {}, MATCH = {}, F = { kids: 0 };
for (const [k, c] of [["Taco Bell", "food"], ["Chipotle", "food"], ["Wawa", "store"], ["Walmart", "store"], ["IHOP", "food"]]) BRANDS[k] = { cat: c, e: '' };
const BUNDLED_KEYS = new Set(Object.keys(BRANDS));
const walkTo = (s, k, v) => v[0] * 10; const arriveMs = s => s.plan == null ? null : s.plan;
const localAt = () => ({ min: MIN }); const tzOf = () => 'America/Los_Angeles';
const clockLabel = m => Math.floor(m / 60) + ':' + String(m % 60).padStart(2, '0');
const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const document = { addEventListener() {} };
""" + _SIG + r"""
const f = [], t = (c, msg) => { if (!c) f.push(msg); };
MATCH[1] = { "Chipotle": [10, 0], "Taco Bell": [20, 0] };     // a late chain at 200 m
MATCH[2] = { "Chipotle": [10, 0] };                          // food, none late
MATCH[3] = { "Wawa": [5, 0] };                               // a 24-hour travel stop
MATCH[4] = { "Walmart": [5, 0] };                            // no food at all
const S = id => ({ id, st: 'CA', lat: 34, lon: -118 });
MIN = 23 * 60;
t(/late food/.test(rowSigs(S(1))), 'a row at 11 pm with Taco Bell has no "late food" tag');
t(/Taco Bell is usually open late/.test(rowSigs(S(1))), 'the late tag does not say which place, and "usually"');
t(rowSigs(S(2)) === '', 'a row at night with no late chain still gets a tag');
t(/late food/.test(rowSigs(S(3))), 'a 24-hour travel stop (Wawa) does not count as late food');
const c2 = lateSig(S(2)); t(c2 && c2.closed && /may be closed/.test(c2.label), 'at night, food with no late chain is not "may be closed"');
t(lateSig(S(4)) === null, 'a stop with no food at all says something about late food');
t(/Likely open now: Taco Bell/.test(cardSigs(S(1))), 'the stop card at night does not say what is likely open now');
const p = S(1); p.plan = 5; t(/Likely open ~23:00: Taco Bell/.test(cardSigs(p)), 'on a plan, the card does not use the arrival time');
t(/may be closed then/.test(brkSigs(S(2), 'Chipotle', 0)) && /open late/.test(brkSigs(S(1), 'Taco Bell', 0)), 'a night break does not say open late / may be closed');
MIN = 13 * 60; nowAt.clear();
t(rowSigs(S(1)) === '', 'a row by day carries a late-food tag (every McDonald\'s would)');
t(/Open late: Taco Bell/.test(cardSigs(S(1))), 'the stop card by day does not say what is open late');
t(brkSigs(S(1), 'Taco Bell', 0) === '', 'a daytime break carries a night signal');
t(/open late by the hours OpenStreetMap lists/.test(lateSig(S(1), null, ['Chipotle'], true).why), 'an hours-backed item does not say so');
t(rowSigs(Object.assign(S(1), { lvl: 2 })) === '', 'a Level 2 row carries signals');
console.log(f.length ? f.join("\n") : "OK");"""], capture_output=True, text=True)
    check(_rsig.stdout.strip() == "OK", "stop signals say the wrong thing:\n  " + (_rsig.stdout + _rsig.stderr).strip()[:600])

# ---- Stop signals: the data (batch 8) [B8-D] ----
# The data build: what lands in data.js. A synthetic amenities.json: a motorway running north-
# south 100 m east of charger 7; charger 8 is 160 m east (across it). Toilets 80 m east (this side
# for 7, across for 8) and 290 m east (8's side); a playground 250 m west; a rest area around 7;
# Taco Bell 200 m east (across for 7), Subway 200 m west.
import tempfile as _tf
sys.path.insert(0, os.path.join(HERE, "data"))
import build_data as _bd
_k = 1 / (111320 * __import__("math").cos(__import__("math").radians(40)))
_am = {"v": 1, "toilets": [[40.0, -100 + 80 * _k], [40.0, -100 + 290 * _k]], "playground": [[40.0, -100 - 250 * _k]],
       "mall": [], "rest": [[39.999, -100.001, 40.001, -99.999]],
       "hwy": [[[39.99, -100 + 100 * _k], [40.01, -100 + 100 * _k]]]}
with _tf.NamedTemporaryFile("w", suffix=".json", delete=False) as _f:
    json.dump(_am, _f)
_sg = _bd.amenity_signals([{"id": 7, "lat": 40.0, "lon": -100.0}, {"id": 8, "lat": 40.0, "lon": -100 + 160 * _k}],
                          {7: {"Taco Bell": [0, round(200 * _k * 1e4)], "Subway": [0, -round(200 * _k * 1e4)]}}, _f.name)
os.remove(_f.name)
check(_sg.get(7) == {"wc": 8, "ra": 1, "pg": 25, "xh": ["Taco Bell"]},
      f"build_data.amenity_signals is wrong for the test charger: {_sg.get(7)} (want wc 8, ra, pg 25, xh Taco Bell only)")
check(_sg.get(8) == {"wc": 13},
      f"build_data.amenity_signals counts toilets across the motorway (or a far playground / rest area): {_sg.get(8)} (want wc 13)")
# The cache: complete (no half-done fill), covering the cells of nearly every charger (a failed
# weekly gap-fill may leave a few new ones out), and readable in its compact form.
import fetch_amenities as _fam
import amenities_from_pbf as _afp
_AM = _fam.load()
_ch_all = json.load(open(os.path.join(HERE, "data", "chargers.json")))
_cells = _fam.cells_of(_AM)
_unc = sum(1 for _c in _ch_all if _fam.cell_of(_c["lat"], _c["lon"]) not in _cells)
check("partial" not in _AM and all(k in _AM for k in _fam.KINDS) and _unc <= len(_ch_all) * 0.01,
      f"data/amenities.json is incomplete: partial={'partial' in _AM}, {_unc} chargers outside its cells")
_g = [[40.12345, -100.54321], [40.12399, -100.5], [40.2, -100.49999]]
check(_fam.decode_line(_fam.encode_line(_g)) == _g, "amenities.json highway encoding does not round-trip")
# Clipping keeps a long straight motorway segment that crosses a covered cell with no node in
# it, and merging continued lines keeps every segment.
_cl = _fam.clip("hwy", [[[39.0, -100.01], [41.0, -100.01]]], {(2000, -5001)})
check(_cl == [[[39.0, -100.01], [41.0, -100.01]]] and _fam.clip("hwy", [[[39.0, -100.01], [39.5, -100.01]]], {(2000, -5001)}) == [],
      f"fetch_amenities.clip drops a segment that crosses a covered cell, or keeps one that does not: {_cl}")
_ml = _fam.merge_lines([[[1.0, 1.0], [1.0, 1.001]], [[1.0, 1.001], [1.0, 1.002]], [[2.0, 2.0], [2.0, 2.001]]])
check(sorted(_ml) == [[[1.0, 1.0], [1.0, 1.001], [1.0, 1.002]], [[2.0, 2.0], [2.0, 2.001]]],
      f"fetch_amenities.merge_lines changes the segments: {_ml}")
# The extract path keeps exactly what the Overpass selectors keep.
check(_afp.kinds_of({"amenity": "toilets"}) == ["toilets"] and _afp.kinds_of({"amenity": "toilets", "access": "private"}) == []
      and _afp.kinds_of({"leisure": "playground", "access": "no"}) == [] and _afp.kinds_of({"highway": "services"}) == ["rest"]
      and _afp.is_hwy({"highway": "motorway"}, "w") and not _afp.is_hwy({"highway": "motorway", "bridge": "yes"}, "w")
      and not _afp.is_hwy({"highway": "trunk"}, "w") and _afp.is_hwy({"highway": "trunk", "oneway": "yes"}, "w")
      and not _afp.is_hwy({"highway": "motorway", "tunnel": "yes"}, "w") and not _afp.is_hwy({"highway": "motorway"}, "r"),
      "amenities_from_pbf keeps different things from the Overpass selectors")
for _sel, _want in (('"access"!~"^(private|no)$"', _afp.PRIVATE == {"private", "no"}),
                    ('"bridge"!~"^(yes|viaduct|cantilever|covered)$"', _afp.BRIDGE == {"yes", "viaduct", "cantilever", "covered"}),
                    ('"tunnel"!~"^(yes|building_passage|culvert)$"', _afp.TUNNEL == {"yes", "building_passage", "culvert"})):
    check(_sel in open(os.path.join(HERE, "data", "fetch_amenities.py")).read() and _want,
          f"fetch_amenities.py and amenities_from_pbf.py disagree on {_sel}")
# data.js stores xh as positions in the site's matches; the app turns them into names at boot.
check(re.search(r"(?m)^for \(const s of SITES\) if \(s\.xh\) \{ const ks = Object\.keys\(MATCH\[s\.id\] \|\| \{\}\); s\.xh = s\.xh\.map\(i => ks\[i\]\)\.filter\(Boolean\); \}$", _html) is not None,
      "the app no longer turns data.js xh positions into chain names at boot")
# Coverage floors (measured 2026-11-12 from the US extract: wc 643, ra 780, ml 460, pg 1485, xh 3556; ~70% of each): a broken fetch or fold shows up here.
_cov = {k: sum(1 for s in D["sites"] if k in s) for k in ("wc", "ra", "ml", "pg", "xh")}
_floor = {"wc": 450, "ra": 545, "ml": 320, "pg": 1040, "xh": 2490}
check(all(_cov[k] >= _floor[k] for k in _floor), f"stop-signal coverage fell below its floor: {_cov} (floors {_floor})")
check(all(isinstance(s.get("xh", []), list) and all(k in D["brands"] and k in D["matches"].get(str(s["id"]), {}) for k in s.get("xh", []))
          for s in D["sites"]), "a site's xh names a chain that is not matched at it")

# ---- Restroom likely (batch 8) [B8-R] ----
_SIG_HEAD = r"""let MIN = 13 * 60; const BRANDS = {}, MATCH = {}; const F = { kids: 0 };
for (const k of ["Buc-ee's", 'Waffle House', 'Walmart', 'Taco Bell', 'Chipotle', "Love's"]) BRANDS[k] = { cat: 'food', e: '' };
const BUNDLED_KEYS = new Set(Object.keys(BRANDS));
const walkTo = (s, k, v) => v[0] * 10; const arriveMs = () => null;
const localAt = () => ({ min: MIN }); const tzOf = () => 'America/Chicago';
const walkMin = m => Math.max(1, Math.round(m / 80));
const clockLabel = m => String(m); const esc = t => String(t).replace(/"/g, '&quot;');
const document = { addEventListener() {} };
"""
check("restroomSig(s, w)" in _SIG[_SIG.index("function cardSigs(s) {"):_SIG.index("function brkSigs(")]
      and "out.push(tag(restroomSig(s, w)));" in _SIG
      and "if (restroomSig(s, { min, ms, planned: true })) bits.push('restroom likely');" in _SIG,
      "the restroom signal is gone from the stop card, the rows or the breaks")
if _node and _SIG:
    _rr = subprocess.run([_node, "-e", _SIG_HEAD + _SIG + r"""
const f = [], t = (c, msg) => { if (!c) f.push(msg); };
const S = (id, o) => Object.assign({ id, st: 'TX', lat: 30, lon: -97 }, o || {});
const R = s => { nowAt.clear(); return restroomSig(s); };
MATCH[1] = { "Buc-ee's": [12, 0] };                                         // 120 m
t(R(S(1)) && /Buc-ee's next door/.test(R(S(1)).why), "a travel stop next door is no restroom");
t(R(S(1, { xh: ["Buc-ee's"] })) === null, 'a travel stop across the highway still counts as a restroom');
MATCH[2] = { "Buc-ee's": [30, 0] };                                         // 300 m: too far
t(R(S(2)) === null, 'a travel stop 300 m away counts as a restroom');
t(R(S(3, { ra: 1 })) && /rest area/.test(R(S(3, { ra: 1 })).why), 'a charger at a rest area is no restroom');
t(R(S(4, { wc: 8 })) && /80 m away/.test(R(S(4, { wc: 8 })).why), 'mapped toilets are no restroom');
MATCH[5] = { 'Waffle House': [10, 0] }; MATCH[6] = { 'Waffle House': [20, 0] };
t(R(S(5)) && R(S(6)) === null, 'a 24-hour restaurant counts beyond next door, or not next door');
MATCH[7] = { 'Walmart': [15, 0] };
t(R(S(7)) && /store hours/.test(R(S(7)).why), 'a store next door by day is no restroom');
MIN = 23 * 60; t(R(S(7)) === null, 'a store counts as a restroom at 11 pm');
t(R(S(8, { ml: 1 })) === null, 'a mall counts as a restroom at 11 pm');
MIN = 13 * 60; t(R(S(8, { ml: 1 })) !== null, 'a mall is no restroom by day');
MATCH[9] = { 'Chipotle': [5, 0] }; t(R(S(9)) === null, 'any restaurant counts as a restroom');
t(R(S(1)).label === 'Restroom likely' && / Likely, not certain\.$/.test(R(S(1)).why), 'the restroom signal is not labelled "likely"');
t(R(S(1, { lvl: 2 })) === null, 'a Level 2 site carries a restroom signal');
t(/restroom likely/.test(brkSigs(S(1), "Buc-ee's", 0)) && !/restroom/.test(brkSigs(S(9), 'Chipotle', 0)), 'a planned break does not say "restroom likely" where the rule does');
nowAt.clear(); t(/restroom likely/.test(rowSigs(S(1))) && !/restroom/.test(rowSigs(S(9))), 'a row does not carry "restroom likely" where the rule does');
MIN = 23 * 60; nowAt.clear(); MATCH[12] = { "Love's": [12, 0], 'Taco Bell': [5, 0] };
t((rowSigs(S(12, { pg: 24 })).match(/class="tag sig"/g) || []).length === 2, 'a row carries more than two signals');
console.log(f.length ? f.join("\n") : "OK");"""], capture_output=True, text=True)
    check(_rr.stdout.strip() == "OK", "the restroom signal says the wrong thing:\n  " + (_rr.stdout + _rr.stderr).strip()[:700])

# ---- Good for kids (batch 8) [B8-K] ----
check(re.search(r"(?m)^  if \(F\.kids && !s\.pg\) return false;", _html[_html.index("function passesSpec(s) {"):_html.index("function passesChain(s) {")]) is not None,
      "the Good for kids filter no longer narrows the list (passesSpec)")
check("kids: 0 };" in _html[_html.index("const FDEF = {"):_html.index("const FDEF = {") + 120]
      and "F.kids ? p.set('kids', '1') : p.delete('kids');" in _html
      and re.search(r"(?m)^if \(q\.get\('kids'\)\) F\.kids = 1;$", _html) is not None
      and '<button class="ftog" data-f="kids">' in _html and "kids: () => 'Good for kids'" in _html,
      "Good for kids is not a saved filter, a toggle in Filters and a link parameter (FDEF, ftog, kids=1)")
check("const w = stopWhen(s), items = [restroomSig(s, w), lateSig(s, w), kidsSig(s)].filter(Boolean);" in _SIG
      and "const K = kidsSig(s); if (K) bits.push(K.tag);" in _SIG,
      "the playground is gone from the stop card or the breaks")
if _node and _SIG:
    _kd = subprocess.run([_node, "-e", _SIG_HEAD + _SIG + r"""
const f = [], t = (c, msg) => { if (!c) f.push(msg); };
const S = (id, o) => Object.assign({ id, st: 'TX', lat: 30, lon: -97 }, o || {});
t(kidsSig(S(10, { pg: 24 })).tag === 'playground 3 min' && kidsSig(S(11)) === null, 'the playground tag is wrong');
t(kidsSig(S(10, { pg: 24, lvl: 2 })) === null, 'a Level 2 site carries a playground signal');
MATCH[1] = { "Buc-ee's": [12, 0] }; nowAt.clear();
t(/playground 3 min/.test(rowSigs(S(1, { pg: 24 }))) && /restroom likely/.test(rowSigs(S(1, { pg: 24 }))), 'a row does not carry restroom and playground');
t(/Playground 3 min/.test(cardSigs(S(1, { pg: 24 }))), 'the stop card does not show the playground');
t(/playground 3 min/.test(brkSigs(S(1, { pg: 24 }), "Buc-ee's", 0)), 'a planned break does not show the playground');
MIN = 23 * 60; nowAt.clear(); MATCH[12] = { "Love's": [12, 0], 'Taco Bell': [5, 0] };
const r12 = rowSigs(S(12, { pg: 24 }));
t((r12.match(/class="tag sig"/g) || []).length === 2 && !/playground/.test(r12), 'a row carries more than two signals, or the wrong two at night');
F.kids = 1; t(/^<span class="tag sig"[^>]*><svg[^]*?<\/svg>playground/.test(rowSigs(S(12, { pg: 24 }))), 'with Good for kids on, the playground does not lead');
console.log(f.length ? f.join("\n") : "OK");"""], capture_output=True, text=True)
    check(_kd.stdout.strip() == "OK", "the playground signal says the wrong thing:\n  " + (_kd.stdout + _kd.stderr).strip()[:700])

# ---- Across the highway (batch 8) [B8-H] ----
check(re.search(r"const sc = \[off > 75 \? 2 : off > 45 \? 1 : 0, farWalk\(s, k, w\) \? 1 : 0,", _html) is not None
      and "const sc = [off, shut, -Math.min(s.kw || 0, 350), farWalk(s, k, w) ? 1 : 0," in _html
      and "const sc = [s.lvl === 2 ? 1 : 0, k ? 0 : 1, kw < 100 ? 1 : 0, farWalk(s, k, w) ? 1 : 0," in _html,
      "meals, breaks or the route list rank a walk across a highway as a short one again (farWalk)")
check("<i>${walkMin(walkTo(s, k, v))} min</i>${xhMark(s, k)}</span>" in _html
      and "<b>${walkMin(d)} min</b>${xhMark(s, k)}" in _html
      and "${acrossHwy(s, k) ? ' · across the highway' : ''}</span>" in _html
      and "' min' + (acrossHwy(s, k) ? ' · across hwy' : '')" in _html,
      "a walk across a highway is no longer marked on rows, the stop card or the breaks (xhMark)")
check("(acrossHwy(s, a[0]) - acrossHwy(s, b[0])) || walkTo(s, a[0], a[1]) - walkTo(s, b[0], b[1])" in _html
      and "(acrossHwy(s, a[0]) - acrossHwy(s, b[0])) || mDist(s, a[1]) - mDist(s, b[1])" in _html,
      "places across a highway are listed first again (rows / stop card)")
if _node and _SIG:
    _nf = _html[_html.index("function nearestOf(s, keys, m) {"):_html.index("const foodKeys = ")]
    _hw = subprocess.run([_node, "-e", _SIG_HEAD + _SIG + _nf + r"""
const f = [], t = (c, msg) => { if (!c) f.push(msg); };
const S = (id, o) => Object.assign({ id, st: 'TX', lat: 30, lon: -97 }, o || {});
const m13 = { 'Taco Bell': [5, 0], 'Chipotle': [30, 0] };
t(nearestOf(S(13, { xh: ['Taco Bell'] }), ['Taco Bell', 'Chipotle'], m13)[0] === 'Chipotle', 'nearestOf picks a place across the highway over one on this side');
t(nearestOf(S(13, { xh: ['Taco Bell', 'Chipotle'] }), ['Taco Bell', 'Chipotle'], m13)[0] === 'Taco Bell', 'nearestOf, all across: not the nearest');
t(nearestOf(S(13), ['Taco Bell', 'Chipotle'], m13)[0] === 'Taco Bell', 'nearestOf without highways: not the nearest');
t(farWalk(S(13, { xh: ['Taco Bell'] }), 'Taco Bell', 50) && !farWalk(S(13), 'Taco Bell', 50) && farWalk(S(13), 'Taco Bell', 401), 'farWalk is wrong');
t(/across hwy/.test(xhMark(S(13, { xh: ['Taco Bell'] }), 'Taco Bell')) && xhMark(S(13), 'Taco Bell') === '', 'xhMark is wrong');
MATCH[14] = { 'Taco Bell': [5, 0], 'Waffle House': [8, 0], 'Chipotle': [3, 0] };
t(lateFoods(S(14, { xh: ['Taco Bell'] })).map(x => x[0]).join() === 'Waffle House,Taco Bell', 'lateFoods does not put this side of the highway first');
console.log(f.length ? f.join("\n") : "OK");"""], capture_output=True, text=True)
    check(_hw.stdout.strip() == "OK", "the across-the-highway rules say the wrong thing:\n  " + (_hw.stdout + _hw.stderr).strip()[:700])
# planner.py ranks like the app: same side of the highway first, and a walk across one is not short.
import planner as _plmod
_pp0 = _plmod.Plan.__new__(_plmod.Plan)
_s13 = {"id": 1, "lat": 30.0, "lon": -97.0, "xh": ["Taco Bell"]}
check(_pp0._nearest(_s13, ["Taco Bell", "Chipotle"], {"Taco Bell": [5, 0], "Chipotle": [30, 0]})[0] == "Chipotle"
      and _plmod.Plan._far(_s13, "Taco Bell", 50) and not _plmod.Plan._far(_s13, "Chipotle", 50),
      "planner.py ranks a walk across a highway like the app no longer (_nearest / _far)")
# Static pages say it too: the generator's chips and the trip plan's food cells.
_bpy = open(os.path.join(HERE, "build.py")).read()
check("<i>{mins(d)} min</i>{xh_mark(s, k)}</span>" in _bpy and "{r['walk']} min{xh_mark(s, k)}</span>" in _bpy
      and "{mins(d)} min{xh_mark(s, x)}</span>" in _bpy and "key=lambda x: (x[0] != focus, x[0] in xh, x[1])" in _bpy,
      "build.py no longer marks walks across a highway on the pages (xh_mark)")
_xh_bad, _xh_seen = [], 0
_by = {s["id"]: s for s in D["sites"]}
for _p in glob.glob(os.path.join(HERE, "trip", "*", "index.html")):
    _t = open(_p).read()
    for _row in re.findall(r'<tr><td>.*?</tr>', _t, re.S):
        _m = re.search(r'stop=(\d+)"', _row)
        _f = re.search(r'<td><span class="nw">\S+ <b>(.*?)</b> \d+ min(<small class="xh")?', _row)
        if not _m or not _f:
            continue
        _k = re.sub(r"<[^>]+>", "", _f.group(1)).replace("&#x27;", "'").replace("&amp;", "&")
        _want = _k in (_by.get(int(_m.group(1)), {}).get("xh") or [])
        _xh_seen += _want
        if _want != bool(_f.group(2)):
            _xh_bad.append(os.path.basename(os.path.dirname(_p)) + ": " + _k)
check(not _xh_bad, f"trip plan rows mark 'across hwy' where the data does not, or miss it: {_xh_bad[:4]}")
_near_xh = sum(open(_p).read().count('class="xh"') for _p in glob.glob(os.path.join(HERE, "near", "*", "*", "index.html"))[:400])
check(_near_xh > 0 or not any("xh" in s for s in D["sites"]), "no /near/ page marks a walk across a highway")

# A stray "}" in pages.css once made browsers drop the next rule (table.trip{...}) unnoticed:
# every stylesheet the site ships must have balanced braces, never closing more than it opened.
def _css_balanced(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r'"(?:\\.|[^"\\])*"', '""', css)
    d = 0
    for ch in css:
        d += (ch == "{") - (ch == "}")
        if d < 0:
            return False
    return d == 0
_css_bad = [f for f in ["assets/pages.css"] if not _css_balanced(open(os.path.join(HERE, f)).read())]
_css_bad += [f"index.html <style> #{i}" for i, c in enumerate(re.findall(r"<style[^>]*>(.*?)</style>", open(os.path.join(HERE, "index.html")).read(), re.S)) if not _css_balanced(c)]
check(not _css_bad, f"unbalanced CSS braces (a rule after them is silently dropped): {_css_bad}")

print(f"checked data.js, {len(pages)} pages, sitemap, assets")
for w in warn:
    print(f"  WARN  {w}")
if fail:
    print("\nFAILED:")
    for f in fail:
        print(f"  ✗ {f}")
    sys.exit(1)
print("all checks passed")

