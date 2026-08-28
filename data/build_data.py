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
    prev = None
    while prev != n:                       # strip repeated trailing unit codes
        prev = n
        n = _CODE_TAIL.sub('', n).strip(' -–—·,')
    if not n:
        n = host or name or "Charging station"
    letters = [c for c in n if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.85 and len(n) > 6:
        n = n.title()                       # ALL CAPS -> Title Case
        n = _re.sub(r'\b(Ev|Dc|Ac|Hq|Us|Ii|Iii|Iv)\b', lambda m: m.group(0).upper(), n)
    return n[:60]

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

    best = {}
    for s in kept:
        key = (round(s["lat"], 4), round(s["lon"], 4))
        if key not in best or richness(s) > richness(best[key]):
            best[key] = s
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
            if all(hav(s["lat"], s["lon"], p["lat"], p["lon"]) > 200 for p in picked):
                picked.append(s)
        deduped.extend(picked)
    stats["dup"] = len(kept) - len(deduped)

    for s in deduped:
        if DEALER_RE.search(s["name"]):
            s["dlr"] = 1; stats["dealer"] += 1
    stats["end"] = len(deduped)
    return deduped, stats


def hav(a1, o1, a2, o2):
    R = 6371000
    p1, p2 = math.radians(a1), math.radians(a2)
    dp, dl = math.radians(a2 - a1), math.radians(o2 - o1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    chargers = json.load(open(os.path.join(HERE, "chargers.json")))
    chargers, cstats = clean(chargers)
    print(f"Cleaned: {cstats['start']} -> {cstats['end']}  "
          f"(dropped {cstats['low_kw']} sub-{MIN_KW}kW, {cstats['truck']} truck-only, "
          f"{cstats['private']} private/test, {cstats['dup']} duplicates; "
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

    brands_out = {k: {"e": v[0], "cat": v[1], "n": len(pois.get(k, []))}
                  for k, v in RAW_BRANDS.items() if k in pois}

    import time
    # Marker colour is presentation and lives in NETCOL in index.html. It used to be baked
    # into every record here, which meant a palette change needed a full refetch and left
    # 3,081 copies of the old Tesla red in the payload waiting to be picked up again.
    for c in chargers:
        c.pop("col", None)

    payload = {
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
        try:
            old_raw = open(out_path).read()
            old = json.loads(old_raw[old_raw.index("{"): old_raw.rindex("}") + 1])
        except Exception:
            old = None
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
