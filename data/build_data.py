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
    "Tesla Model 3":        [57, 250, 2],
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


def hav(a1, o1, a2, o2):
    R = 6371000
    p1, p2 = math.radians(a1), math.radians(a2)
    dp, dl = math.radians(a2 - a1), math.radians(o2 - o1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    chargers = json.load(open(os.path.join(HERE, "chargers.json")))
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
        found = {}
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for (bkey, plat, plon) in grid.get((c0[0] + di, c0[1] + dj), []):
                    d = hav(lat, lon, plat, plon)
                    if d <= WALK_M and (bkey not in found or d < found[bkey]):
                        found[bkey] = d
        if found:
            matches[s["id"]] = {k: int(v) for k, v in sorted(found.items(), key=lambda x: x[1])}

    brands_out = {k: {"e": v[0], "cat": v[1], "n": len(pois.get(k, []))}
                  for k, v in RAW_BRANDS.items() if k in pois}

    import time
    payload = {
        "generated": time.strftime("%Y-%m-%d"),
        "walkM": WALK_M,
        "sites": chargers,
        "brands": brands_out,
        "matches": matches,
        "cars": CARS,
    }
    js = "window.PITSTOP_DATA = " + json.dumps(payload, separators=(",", ":")) + ";\n"
    open(os.path.join(HERE, "..", "data.js"), "w").write(js)

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
