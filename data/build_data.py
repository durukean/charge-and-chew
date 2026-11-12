#!/usr/bin/env python3
"""Match chain POIs to all-network DC-fast chargers and emit ../data.js.

Inputs:  data/chargers.json  (from fetch_chargers.py)
         data/pois.json      (from fetch_pois.py; brand -> [{lat,lon}])
Output:  ../data.js          window.PITSTOP_DATA = {sites, brands, matches, cars}
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
WALK_M = 800

# brand -> (emoji, category) — mirror of fetch_pois.BRANDS (kept in sync manually)
from fetch_pois import BRANDS as RAW_BRANDS  # (emoji, cat, regex)
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data_reader import load_data

# Shape version of data.js. The web page (DATA_FMT in index.html) and the iOS app refuse a
# data.js whose fmt differs from what they were built for. BUMP IT for any change a reader
# would misread -- and note that iOS builds up to 1.0.4 predate the check: they download
# https://chargeandchew.com/data.js unconditionally, so a new shape must not replace that
# URL until those versions are gone (serve it under a new name instead).
DATA_FMT = 1

# ── car database: model -> [battery kWh usable, max DC kW, connector bit] ──
# connector: 1=CCS1, 2=NACS  (all can use the other via adapter; native listed)
CARS = {
    "Tesla Model 3 RWD":    [60, 170, 2],
    "Tesla Model 3 Long Range": [79, 250, 2],
    "Tesla Model Y":        [75, 250, 2],
    "Tesla Model S":        [95, 250, 2],
    "Tesla Model X":        [95, 250, 2],
    "Tesla Cybertruck":     [123, 325, 2],
    "Ford Mustang Mach-E":  [88, 150, 1],
    "Ford F-150 Lightning": [131, 155, 1],
    "Chevy Bolt EV":        [65, 55, 1],
    "Chevy Equinox EV":     [85, 150, 1],
    "Chevy Blazer EV":      [102, 190, 1],
    "Chevy Silverado EV":   [205, 350, 1],
    "Hyundai Ioniq 5":      [77, 235, 1],
    "Hyundai Ioniq 6":      [77, 235, 1],
    "Hyundai Kona Electric":[64, 77, 1],
    "Kia EV6":              [77, 235, 1],
    "Kia EV9":              [99, 210, 1],
    "Kia Niro EV":          [64, 85, 1],
    "Rivian R1T":           [135, 220, 1],
    "Rivian R1S":           [135, 220, 1],
    "VW ID.4":              [82, 175, 1],
    "Nissan Ariya":         [87, 130, 1],
    "Nissan Leaf":          [60, 50, 4],
    "BMW i4":               [81, 205, 1],
    "BMW iX":               [105, 195, 1],
    "Audi Q4 e-tron":       [77, 175, 1],
    "Audi e-tron / Q8":     [106, 170, 1],
    "Polestar 2":           [79, 205, 1],
    "Mercedes EQB":         [67, 100, 1],
    "Mercedes EQE / EQS":   [90, 170, 1],
    "Lucid Air":            [112, 300, 1],
    "Subaru Solterra":      [72, 100, 1],
    "Toyota bZ4X":          [72, 100, 1],
    "Honda Prologue":       [85, 155, 1],
    "Cadillac Lyriq":       [102, 190, 1],
    "Genesis GV60":         [77, 235, 1],
    "Volvo EX30":           [64, 153, 1],
    "Volvo EX90":           [107, 250, 1],
    "Fisker Ocean":         [106, 190, 1],
    "Other CCS EV":         [75, 150, 1],
    "Other Tesla/NACS EV":  [75, 250, 2],
}


# ── data cleaning (applies on every rebuild, incl. the monthly refresh) ──
import re as _re

DEALER_RE = _re.compile(r'\b(nissan|bmw|mini of|mercedes|chevrolet|chevy|ford of|toyota|honda|kia|'
                        r'hyundai|audi|volkswagen|vw of|subaru|lexus|cadillac|buick|gmc|dodge|chrysler|'
                        r'jeep|ram|volvo|porsche|mazda|dealer|auto group|automotive)\b', _re.I)
# AFDC sometimes ships records whose own name says they are not usable. "NOT A PUBLIC SITE -
# IONNA Customer Experience Center" (Adak, AK) sat on the map for months because the pattern
# only matched "not for public".
PRIVATE_RE = _re.compile(r'not (for|a) public|private|employees? only|staff only|'
                         r'test (evse|site)|for testing|do not use|decommission', _re.I)
TRUCK_NETS = {"Watt Ev"}          # WattEV = heavy-truck megawatt depots, not for cars
MIN_KW = 24                        # below this it is not DC fast (AFDC miscategorisation)

_CODE_TAIL = _re.compile(r'\s+(?:DCFC|DC\s?FAST|EVSE|STATION|CHARGER|PORT)?\s*'
                         r'[A-Z]{0,5}\d{1,6}[A-Z0-9]{0,4}$', _re.I)

def pretty_name(name, host=""):
    """Machine names like 'PIE AE HEB E51ST DCFC1' are what the user reads. Tidy them."""
    n = (name or "").strip()
    n = _re.sub(r'\s+', ' ', n)
    # Network-internal tags that mean nothing to a driver (2026-10-22): Mercedes-Benz's
    # "MB.HPC" (78 sites) and Electrify America's Bank of America site codes "BOA Kent
    # WA5-119" (64); a trailing "DC" (164) goes in the loop below. The network is shown
    # beside the name.
    n = _re.sub(r'\s+MB\.HPC\b', '', n)
    n = _re.sub(r'\s+[A-Z]{2}\d{1,2}-\d{2,4}\b', '', n)
    n = _re.sub(r'^BOA\b', 'Bank of America', n)
    n = _re.sub(r'\bBucees\b', "Buc-ee's", n)
    prev = None
    while prev != n:                       # strip repeated trailing unit codes
        prev = n
        n = _CODE_TAIL.sub('', n).strip(' -–—·,')
        # "Pine City DCFC", "Motley DC Fast Charger", "Pendleton DCFC 2" (309 sites): every
        # station here is a DC fast charger, so the tail says nothing. In the loop, because a
        # unit number after it ("... DCFC 1") only comes off on the pass above.
        n = _re.sub(r'[\s\-–—]+(?:DCFC|DC Fast(?: Charg\w*)?|Fast Charg\w*)$', '', n, flags=_re.I)
        n = _re.sub(r'(?<!Washington)\s+DC$', '', n, flags=_re.I)
    if not n or n.upper() == "DC":         # the whole name was "DC Fast Charger"
        n = host or name or "Charging station"
    # Some networks put the site name in the station name too: "KEY CENTER KEY CENTER",
    # "Kinsale EV Kinsale EV" (41 fast and 213 Level 2 sites). Keep one copy.
    w = n.split()
    if len(w) % 2 == 0 and len(w) >= 2 and [x.lower() for x in w[:len(w) // 2]] == [x.lower() for x in w[len(w) // 2:]]:
        n = " ".join(w[:len(w) // 2])
    letters = [c for c in n if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.85 and len(n) > 6:
        n = n.title()                       # ALL CAPS -> Title Case
        n = _re.sub(r'\b(Ev|Dc|Ac|Hq|Us|Ii|Iii|Iv)\b', lambda m: m.group(0).upper(), n)
    return n[:60]

_KEEP_UPPER = {"N", "S", "E", "W", "NE", "NW", "SE", "SW", "US", "SR", "FM", "CR", "PO", "II", "III", "IV"}

def unshout(t):
    """'LARAMIE' -> 'Laramie', '9000 NE HIGHWAY 99' -> '9000 NE Highway 99'. Only text that
    is all capitals is touched; mixed case is someone's deliberate spelling."""
    if not t or t != t.upper() or len(_re.sub(r'[^A-Z]', '', t)) < 3:
        return t
    out = []
    for w in t.split(' '):
        if w in _KEEP_UPPER or _re.fullmatch(r'[A-Z]-?\d+[A-Z]?', w):   # I-35, US, NE, 5A
            out.append(w)
        else:
            w = w.title()
            w = _re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), w)  # 1St -> 1st
            w = _re.sub(r"'S\b", "'s", w)
            out.append(w)
    return ' '.join(out)

PLUG_BITS = (1, 2, 4)            # CCS, NACS (Tesla), CHAdeMO -- the order of "pk"


def plug_kw(s):
    """{plug bit: max kW} for one listing. "pk" is only stored when a site has several plug
    types; otherwise its one plug runs at the site's kw."""
    if s.get("pk"):
        return {b: kw for b, kw in zip(PLUG_BITS, s["pk"]) if s.get("conn", 0) & b}
    return {b: s.get("kw") or 0 for b in PLUG_BITS if s.get("conn", 0) & b}


def merge_plugs(keep, other):
    """Fold another listing of the same station into keep: union of plugs, per-plug max kW."""
    a = plug_kw(keep)
    for b, kw in plug_kw(other).items():
        a[b] = max(a.get(b, 0), kw)
    keep["conn"] = keep.get("conn", 0) | other.get("conn", 0)
    keep["kw"] = max(keep.get("kw") or 0, other.get("kw") or 0)
    keep.pop("pk", None)
    if len(a) > 1:
        keep["pk"] = [a.get(b, 0) for b in PLUG_BITS]


def clean(sites):
    """Drop unusable rows, de-duplicate co-located listings, tidy names, flag dealerships."""
    stats = dict(start=len(sites), low_kw=0, truck=0, private=0, dup=0, renamed=0, dealer=0, unnamed=0)
    kept = []
    for s in sites:
        if s.get("net") in TRUCK_NETS:
            stats["truck"] += 1; continue
        if s.get("kw") and s["kw"] < MIN_KW:
            stats["low_kw"] += 1; continue
        if PRIVATE_RE.search(s.get("name", "")):
            stats["private"] += 1; continue
        # tidy the name BEFORE de-duplicating: "PIE AE AUSTIN HS DCFC1" and "...DCFC2" are the
        # same site, and only look identical once the trailing cabinet code is stripped
        pn = pretty_name(s.get("name", ""))
        if pn != s.get("name"):
            s["name"] = pn; stats["renamed"] += 1
        # 161 cities and 151 streets arrive in capitals ("LARAMIE, WY" headed a route's break).
        for f in ("city", "street"):
            if s.get(f): s[f] = unshout(s[f])
        # A few records carry a name like "DC", "76" or "M3", which tells a user nothing.
        # Fall back to the address rather than dropping an otherwise valid charger.
        if len(_re.sub(r'[^A-Za-z0-9]', '', pn)) < 3:
            alt = s.get("street") or ""
            s["name"] = alt.strip() or f"Charger · {s.get('city','')}".strip(" ·")
            stats["unnamed"] += 1
        kept.append(s)

    # de-duplicate in two passes:
    #   1. identical coordinates (~11 m)
    #   2. same name within 200 m — AFDC lists many sites once per cabinet, which is
    #      why a route could surface "Pie Ae Austin Hs" four times in a row
    def richness(x):
        return (x.get("kw") or 0, x.get("stalls") or 0, len(x.get("name") or ""))

    # Duplicates are listings of ONE station, so only the same network is merged -- and the
    # dropped listing's plugs are kept, not thrown away. Keying on coordinates alone merged a
    # Tesla Supercharger into the Electrify America station that shares its coordinates
    # (Boca Raton, Cadillac MI: 10 sites gone), and keeping only the "richest" listing lost a
    # plug type at 77 places -- a CCS cabinet listed separately from a CHAdeMO one, say.
    best = {}
    for s in kept:
        key = (round(s["lat"], 4), round(s["lon"], 4), s.get("net"))
        if key not in best:
            best[key] = s
        elif richness(s) > richness(best[key]):
            merge_plugs(s, best[key]); best[key] = s
        else:
            merge_plugs(best[key], s)
    stage1 = list(best.values())

    by_name = {}
    for s in stage1:
        by_name.setdefault((s["name"].lower(), s.get("st", "")), []).append(s)
    deduped = []
    for group in by_name.values():
        if len(group) == 1:
            deduped.extend(group); continue
        group.sort(key=richness, reverse=True)   # keep the richest of each cluster
        picked = []
        for s in group:
            near = [p for p in picked if hav(s["lat"], s["lon"], p["lat"], p["lon"]) <= 200]
            if near:
                merge_plugs(near[0], s)            # same station: keep its plugs
            else:
                picked.append(s)
        deduped.extend(picked)
    stats["dup"] = len(kept) - len(deduped)

    deduped, stats["ports"] = merge_ports(deduped)

    for s in deduped:
        if DEALER_RE.search(s["name"]):
            s["dlr"] = 1; stats["dealer"] += 1
    stats["end"] = len(deduped)
    return deduped, stats


PORT_M = 50     # port-split listings of one site sit within this many metres of each other
_SEP = " -_#/."


def _prefix(a, b):
    n = 0
    while n < min(len(a), len(b)) and a[n].lower() == b[n].lower():
        n += 1
    return n


def _same_site(s, t):
    """Two listings of one site split by port or cabinet: "Dash In Dash In-1" ... "-4",
    "City_Of_Vernon 3805 Soto-1" ... "-10", "Ucsd Cp-Athena Dc1-1" ... "-5". Same network,
    within PORT_M, and the names share most of their length (at least 60% of the shorter)."""
    if s.get("net") != t.get("net") or hav(s["lat"], s["lon"], t["lat"], t["lon"]) > PORT_M:
        return False
    n = _prefix(s["name"], t["name"])
    return n >= max(5, 0.6 * min(len(s["name"]), len(t["name"])))


def merge_ports(sites):
    """Merge listings of one site that AFDC splits by port: a route through Los Angeles opened on
    four "City_Of_Vernon 1850 E25Th-…" rows and five "…3805 Soto-…" ones. Each listing is a
    separate charger, so stalls ADD UP (unlike the duplicate listings merged above); plugs are
    unioned and the best kW kept. The richest listing stays (its id and address); the name is the
    shared part when it ends at a separator ("City_Of_Vernon 3805 Soto"), or one listing's name
    is that part, else the richest listing's own name."""
    grid = {}
    for s in sites:
        grid.setdefault((int(s["lat"] * 200), int(s["lon"] * 200)), []).append(s)
    parent = {id(s): s for s in sites}

    def root(s):
        while parent[id(s)] is not s:
            parent[id(s)] = parent[id(parent[id(s)])]
            s = parent[id(s)]
        return s
    for s in sites:
        ci, cj = int(s["lat"] * 200), int(s["lon"] * 200)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for t in grid.get((ci + di, cj + dj), ()):
                    if t is not s and _same_site(s, t):
                        a, b = root(s), root(t)
                        if a is not b:
                            parent[id(b)] = a
    groups = {}
    for s in sites:
        groups.setdefault(id(root(s)), []).append(s)
    out, merged = [], 0
    for g in groups.values():
        if len(g) == 1:
            out.append(g[0]); continue
        g.sort(key=lambda x: ((x.get("kw") or 0), (x.get("stalls") or 0), -x["id"] if isinstance(x.get("id"), int) else 0), reverse=True)
        keep = g[0]
        n = min(_prefix(keep["name"], x["name"]) for x in g[1:])
        common = keep["name"][:n]
        stalls = sum(x.get("stalls") or 0 for x in g)
        for x in g[1:]:
            merge_plugs(keep, x)
            if x.get("h24"):
                keep["h24"] = 1
        if stalls:
            keep["stalls"] = stalls
        if (common and common[-1] in _SEP) or any(x["name"] == common for x in g):
            base = common.rstrip(_SEP).strip()
            if len(base) >= 5:
                keep["name"] = base
        out.append(keep)
        merged += len(g) - 1
    return out, merged


def hav(a1, o1, a2, o2):
    R = 6371000
    p1, p2 = math.radians(a1), math.radians(a2)
    dp, dl = math.radians(a2 - a1), math.radians(o2 - o1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ── stop signals from data/amenities.json (fetch_amenities.py) ──
# Folded in as a few small per-charger numbers, never the raw points:
#   wc: public toilets mapped within WC_M, in tens of metres ("restroom likely")
#   ra: 1 when the charger is at a highway rest area or service plaza ("restroom likely")
#   ml: 1 when the charger is at a shopping mall ("restroom likely", in mall hours)
#   pg: a playground within PG_M, in tens of metres ("good for kids")
#   xh: the matched chains whose straight line from the charger crosses a motorway or a divided
#       trunk road at street level ("across the highway"; the walk shown is straight-line)
# A place on the far side of a highway is never counted as next to the charger.
WC_M, PG_M = 150, 300
AT_M = 60          # how far outside a rest area's or mall's outline a charger still counts as at it


class _Local:
    """Metres east/north of one charger, close enough at a kilometre's range."""
    def __init__(self, lat, lon):
        self.lat, self.lon = lat, lon
        self.kx = math.cos(math.radians(lat)) * 111320.0
    def xy(self, lat, lon):
        return ((lon - self.lon) * self.kx, (lat - self.lat) * 110540.0)


def _cross(ax, ay, bx, by, cx, cy, dx, dy):
    """Do segments AB and CD properly intersect?"""
    def o(px, py, qx, qy, rx, ry):
        v = (qx - px) * (ry - py) - (qy - py) * (rx - px)
        return (v > 1e-9) - (v < -1e-9)
    return (o(ax, ay, bx, by, cx, cy) * o(ax, ay, bx, by, dx, dy) < 0 and
            o(cx, cy, dx, dy, ax, ay) * o(cx, cy, dx, dy, bx, by) < 0)


def amenity_signals(chargers, matches, path=None):
    path = path or os.path.join(HERE, "amenities.json")
    if not os.path.exists(path):
        print("No data/amenities.json: no restroom / playground / highway signals this build")
        return {}
    from fetch_amenities import load as load_amenities
    A = load_amenities(path)
    G = 0.01
    def cells(lat, lon, r=1):
        i, j = int(math.floor(lat / G)), int(math.floor(lon / G))
        return [(i + a, j + b) for a in range(-r, r + 1) for b in range(-r, r + 1)]
    def index(points):
        g = {}
        for p in points:
            g.setdefault((int(math.floor(p[0] / G)), int(math.floor(p[1] / G))), []).append(p)
        return g
    toil, play = index(A.get("toilets", [])), index(A.get("playground", []))
    boxes = {}
    for kind in ("rest", "mall"):
        g = {}
        for b in A.get(kind, []):
            for i in range(int(math.floor(b[0] / G)), int(math.floor(b[2] / G)) + 1):
                for j in range(int(math.floor(b[1] / G)), int(math.floor(b[3] / G)) + 1):
                    g.setdefault((i, j), []).append(b)
        boxes[kind] = g
    segs = {}
    for line in A.get("hwy", []):
        for a, b in zip(line, line[1:]):
            for i in range(int(math.floor(min(a[0], b[0]) / G)), int(math.floor(max(a[0], b[0]) / G)) + 1):
                for j in range(int(math.floor(min(a[1], b[1]) / G)), int(math.floor(max(a[1], b[1]) / G)) + 1):
                    segs.setdefault((i, j), []).append((a, b))

    out = {}
    for s in chargers:
        L = _Local(s["lat"], s["lon"])
        near = []
        seen = set()
        for c in cells(s["lat"], s["lon"]):
            for sg in segs.get(c, ()):
                if id(sg) not in seen:
                    seen.add(id(sg))
                    near.append(L.xy(*sg[0]) + L.xy(*sg[1]))
        def across(lat, lon):
            x, y = L.xy(lat, lon)
            return any(_cross(0, 0, x, y, *q) for q in near)
        def nearest(grid, limit):
            best = None
            for c in cells(s["lat"], s["lon"]):
                for p in grid.get(c, ()):
                    d = hav(s["lat"], s["lon"], p[0], p[1])
                    if d <= limit and (best is None or d < best) and not across(p[0], p[1]):
                        best = d
            return best
        def at(kind):
            m = AT_M / 111000.0
            for c in cells(s["lat"], s["lon"], 0):
                for b in boxes[kind].get(c, ()):
                    k = m / max(0.2, math.cos(math.radians(s["lat"])))
                    if b[0] - m <= s["lat"] <= b[2] + m and b[1] - k <= s["lon"] <= b[3] + k:
                        return True
            return False
        sig = {}
        d = nearest(toil, WC_M)
        if d is not None:
            sig["wc"] = max(1, int(round(d / 10)))
        if at("rest"):
            sig["ra"] = 1
        if at("mall"):
            sig["ml"] = 1
        d = nearest(play, PG_M)
        if d is not None:
            sig["pg"] = max(1, int(round(d / 10)))
        if near:
            xh = [k for k, v in (matches.get(s["id"]) or {}).items()
                  if across(s["lat"] + v[0] / 1e4, s["lon"] + v[1] / 1e4)]
            if xh:
                sig["xh"] = xh
        if sig:
            out[s["id"]] = sig
    return out


def main():
    chargers = json.load(open(os.path.join(HERE, "chargers.json")))
    chargers, cstats = clean(chargers)
    print(f"Cleaned: {cstats['start']} -> {cstats['end']}  "
          f"(dropped {cstats['low_kw']} sub-{MIN_KW}kW, {cstats['truck']} truck-only, "
          f"{cstats['private']} private/test, {cstats['dup']} duplicates, {cstats['ports']} port-split listings; "
          f"renamed {cstats['renamed']}, flagged {cstats['dealer']} dealerships)")
    pois = json.load(open(os.path.join(HERE, "pois.json")))

    # grid-bucket POIs (0.02deg ~ 2km)
    grid = {}
    for key, pts in pois.items():
        for p in pts:
            cell = (int(p["lat"] / 0.02), int(p["lon"] / 0.02))
            grid.setdefault(cell, []).append((key, p["lat"], p["lon"]))

    matches = {}
    for s in chargers:
        lat, lon = s["lat"], s["lon"]
        c0 = (int(lat / 0.02), int(lon / 0.02))
        found = {}   # bkey -> (dist, plat, plon) of nearest POI of that brand
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for (bkey, plat, plon) in grid.get((c0[0] + di, c0[1] + dj), []):
                    d = hav(lat, lon, plat, plon)
                    if d <= WALK_M and (bkey not in found or d < found[bkey][0]):
                        found[bkey] = (d, plat, plon)
        if found:
            # store nearest POI as integer deltas x1e4 from the charger (~11 m precision),
            # ordered by distance; the app reconstructs lat/lon and recomputes walk distance.
            matches[s["id"]] = {
                k: [round((plat - lat) * 1e4), round((plon - lon) * 1e4)]
                for k, (d, plat, plon) in sorted(found.items(), key=lambda x: x[1][0])
            }

    # Stop signals (restroom likely, playground, across the highway): a few small keys per site.
    signals = amenity_signals(chargers, matches)
    for c in chargers:
        c.update(signals.get(c["id"], {}))
        if "xh" in c:   # as positions in the site's own matches (half the bytes); data_reader and the app turn them back into names
            order = list(matches[c["id"]])
            c["xh"] = [order.index(k) for k in c["xh"]]
    from collections import Counter as _C
    _n = _C(k for v in signals.values() for k in v)
    print("Signals: " + ", ".join("%s %d" % kv for kv in sorted(_n.items())) +
          " (sites); across-the-highway pairs: %d" % sum(len(v.get("xh", [])) for v in signals.values()))

    brands_out = {k: {"e": v[0], "cat": v[1], "n": len(pois.get(k, []))}
                  for k, v in RAW_BRANDS.items() if k in pois}

    import time
    # Marker colour is presentation and lives in NETCOL in index.html. It used to be baked
    # into every record here, which meant a palette change needed a full refetch and left
    # 3,081 copies of the old Tesla red in the payload waiting to be picked up again.
    for c in chargers:
        c.pop("col", None)

    payload = {
        "fmt": DATA_FMT,          # first, so it sits in the 512-byte head the app reads
        "generated": time.strftime("%Y-%m-%d"),
        "walkM": WALK_M,
        "sites": chargers,
        "brands": brands_out,
        "matches": matches,
        "cars": CARS,
    }
    # Compare against the data.js that is currently live before overwriting it. Everything
    # downstream (13k markers, 180 generated pages, the sitemap) is derived from this file,
    # so a bad build here silently breaks the whole site.
    out_path = os.path.join(HERE, "..", "data.js")
    if os.path.exists(out_path):
        # This used to slice the raw file and json.loads it, which cannot read the escaped
        # JSON.parse('...') form; the exception was swallowed and every check below was
        # silently skipped for months. Not being able to read the old file is now fatal.
        try:
            old = load_data(out_path)
        except Exception as e:
            raise SystemExit(f"ABORT: cannot read the existing data.js to compare against ({e}). "
                             "Fix or delete it deliberately; data.js not written.")
        if old:
            drop_sites = 1 - len(chargers) / max(1, len(old.get("sites", [])))
            drop_match = 1 - len(matches) / max(1, len(old.get("matches", {})))
            lost_chains = set(old.get("brands", {})) - set(brands_out)
            if drop_sites > 0.15:
                raise SystemExit(f"ABORT: chargers fell {drop_sites:.0%} "
                                 f"({len(old['sites'])} -> {len(chargers)}). data.js not written.")
            if drop_match > 0.20:
                raise SystemExit(f"ABORT: chain matches fell {drop_match:.0%} "
                                 f"({len(old['matches'])} -> {len(matches)}). data.js not written.")
            if lost_chains:
                raise SystemExit(f"ABORT: these chains vanished entirely: {sorted(lost_chains)}. "
                                 f"Usually a broken brand regex. data.js not written.")

    # JSON.parse() beats an object literal on cold parse by ~1.5-2x in the browser for
    # about +1 KB gzipped. Single-quoted so the JSON's own double quotes need no escaping.
    compact = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    esc = (compact.replace("\\", "\\\\").replace("'", "\\'")
                  .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    js = "window.PITSTOP_DATA = JSON.parse('" + esc + "');\n"
    open(out_path, "w", encoding="utf-8").write(js)

    from collections import Counter
    cnt = Counter()
    for m in matches.values():
        for k in m: cnt[k] += 1
    print(f"Wrote data.js ({len(js)//1024} KB)")
    print(f"Chargers: {len(chargers)} · with >=1 chain: {len(matches)} "
          f"({100*len(matches)//len(chargers)}%) · chains: {len(brands_out)} · cars: {len(CARS)}")
    for k, c in cnt.most_common(8):
        print(f"  {c:5d}  {k}")


if __name__ == "__main__":
    main()
