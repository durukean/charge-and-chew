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
      and re.search(r"lsPut\(GEO_NS, gk, hit, GEO_CAP\)", _html) is not None,
      "geocoding is no longer cached")
check(re.search(r"lsGet\(RTE_NS, rk, RTE_TTL\)", _html) is not None
      and re.search(r"lsPut\(RTE_NS, rk, trip, RTE_CAP\)", _html) is not None,
      "route geometry is no longer cached — an OSRM outage would kill a route already planned")
# Caching a failure would stick: the lsPut must sit after every validation, so only a
# resolved place is ever stored.
_gi, _gp = _html.find("const gk = q.trim()"), _html.find("lsPut(GEO_NS, gk, hit")
check(_gi > 0 and _gp > _html.find("if (looksLikeChainBrand(", _gi),
      "the geocode cache is written before validation — a bad hit would be cached")
# Route entries are ~50 kB; the namespace has to be bounded.
check(re.search(r"RTE_CAP = \d+", _html) is not None and "if (cap) {" in _html,
      "the route cache is unbounded — 50 kB an entry would fill localStorage")

# ---- sheet title stays a sentence ----
# The fallback activates five chains for one search ("coffee"); listing them all gave a
# title that truncated to mush on a phone. Name the question when the set is the seed's,
# and cap any hand-picked list past three.
check("isSeed ? seedFor.icon + ' ' + seedFor.label" in _html,
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
check(re.search(r"const g = await geocode\(p\.place\);\n\s*if \(myNav !== navGen\) return;", _html) is not None,
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
check("if (!r.ok) throw new Error(busyMsg('Place search', r.status));" in _html
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
check(".oh.n{background:rgba(180,83,9,.14);color:var(--warn)}" in _html,
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
    ("heroTrip", "the hero card no longer offers to plan a drive"),
    ("LA to Las Vegas", "the search suggestions have no road-trip example"),
]:
    check(_needle in _html, _why)
# An arrow has to become "to" BEFORE normalise(), which strips punctuation.
check("' to ')" in _html and "->" in _html,
      "arrow syntax is normalised away before parseTrip sees it")
check("or 'LA to Las Vegas'" in _html, "the search placeholder does not mention trips")
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
check("function keepPopupOnScreen" in _html and _html.count("keepPopupOnScreen();") == 1,
      "the post-fit popup nudge is gone — on a phone the popup's right half falls off screen")
check(_html.count('enterkeyhint=') == 5 and 'autocorrect="off"' in _html,
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
check(".chip.more::before" in _html and "＋ All chains" in _html, "the sticky All-chains chip lost its fade")
check('id="poiRetry"' in _html
      and re.search(r"\$\('poiRetry'\)\.onclick = \(\) => runLivePoi\(intent,", _html) is not None,
      "a failed live lookup is only a 3-second toast again — on a phone that reads as nothing "
      "happened (the retry must also carry the scope, or it re-searches the wrong area)")
check('data-net="${esc(k)}"' in _html and "netPick = netPick === k ? null : k;" in _html,
      "legend rows no longer filter by network — on a phone they look tappable and did nothing")
check(".empty .fball{display:block" in _html and "'The <strong>' + esc(nar[0].label)" in _html,
      "the empty state renders its filter label as a block and its button as plain text again")
check(".chip.more{position:sticky;right:0" in _html,
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

print(f"checked data.js, {len(pages)} pages, sitemap, assets")
for w in warn:
    print(f"  WARN  {w}")
if fail:
    print("\nFAILED:")
    for f in fail:
        print(f"  ✗ {f}")
    sys.exit(1)
print("all checks passed")
