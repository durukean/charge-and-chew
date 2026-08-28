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
    raw = open(p).read()
    check(raw.startswith("window.PITSTOP_DATA"), "data.js has the wrong shape")
    try:
        D = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except Exception as e:
        fail.append(f"data.js is not valid JSON: {e}")
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
