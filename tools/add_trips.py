#!/usr/bin/env python3
"""Add road trips to data/trips.json (the source of the /trip/ pages).

    python3 tools/add_trips.py                 # add every pair in PAIRS not already there
    python3 tools/add_trips.py --dry-run       # show what would be fetched

Each trip is routed once by the public OSRM demo server and stored with its geometry, so
build.py never needs the network. Requests go one at a time with a pause: it is a shared,
free service. Existing trips are never refetched or changed.
"""
import json
import math
import os
import sys
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "data", "trips.json")
OSRM = "https://router.project-osrm.org/route/v1/driving/{},{};{},{}?overview=full&geometries=geojson"
STEP_M = 450          # keep a point every ~450 m: the stored trips run ~3.5 points a mile

CITY = {
    "Miami, FL": (25.7617, -80.1918), "Key West, FL": (24.5551, -81.7800),
    "Los Angeles, CA": (34.0522, -118.2437), "Palm Springs, CA": (33.8303, -116.5453),
    "Houston, TX": (29.7604, -95.3698), "New Orleans, LA": (29.9511, -90.0715),
    "Dallas, TX": (32.7767, -96.7970), "Oklahoma City, OK": (35.4676, -97.5164),
    "Atlanta, GA": (33.7490, -84.3880), "Savannah, GA": (32.0809, -81.0912),
    "Boston, MA": (42.3601, -71.0589), "Portland, ME": (43.6591, -70.2568),
    "Kansas City, MO": (39.0997, -94.5786), "St. Louis, MO": (38.6270, -90.1994),
    "Denver, CO": (39.7392, -104.9903),
    "Phoenix, AZ": (33.4484, -112.0740), "Tucson, AZ": (32.2226, -110.9747),
    "Salt Lake City, UT": (40.7608, -111.8910), "Boise, ID": (43.6150, -116.2023),
    "Nashville, TN": (36.1627, -86.7816), "Memphis, TN": (35.1495, -90.0490),
    "San Antonio, TX": (29.4241, -98.4936), "El Paso, TX": (31.7619, -106.4850),
    "Las Vegas, NV": (36.1699, -115.1398), "Flagstaff, AZ": (35.1983, -111.6513),
    "San Francisco, CA": (37.7749, -122.4194), "South Lake Tahoe, CA": (38.9399, -119.9772),
    "Seattle, WA": (47.6062, -122.3321), "Spokane, WA": (47.6588, -117.4260),
}
PAIRS = [
    ("Miami, FL", "Key West, FL"), ("Los Angeles, CA", "Palm Springs, CA"),
    ("Houston, TX", "New Orleans, LA"), ("Dallas, TX", "Oklahoma City, OK"),
    ("Atlanta, GA", "Savannah, GA"), ("Boston, MA", "Portland, ME"),
    ("Kansas City, MO", "St. Louis, MO"), ("Denver, CO", "Kansas City, MO"),
    ("Phoenix, AZ", "Tucson, AZ"), ("Salt Lake City, UT", "Boise, ID"),
    ("Nashville, TN", "Memphis, TN"), ("San Antonio, TX", "El Paso, TX"),
    ("Las Vegas, NV", "Flagstaff, AZ"), ("San Francisco, CA", "South Lake Tahoe, CA"),
    ("Seattle, WA", "Spokane, WA"),
]


def hav(a, b):
    R, p = 6371000.0, math.pi / 180
    x = (math.sin((b[0] - a[0]) * p / 2) ** 2 +
         math.cos(a[0] * p) * math.cos(b[0] * p) * math.sin((b[1] - a[1]) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(x))


def route(a, b):
    (alat, alon), (blat, blon) = CITY[a], CITY[b]
    # curl, not urllib: the macOS system Python's SSL is too old for OSRM's TLS setup.
    out = subprocess.run(["curl", "-sf", "--max-time", "60", "-A", "chargeandchew-trips/1.0",
                          OSRM.format(alon, alat, blon, blat)], capture_output=True, check=True).stdout
    j = json.loads(out)
    if j.get("code") != "Ok" or not j.get("routes"):
        raise RuntimeError(f"OSRM: {j.get('code')} {j.get('message', '')}")
    rt = j["routes"][0]
    full = [(c[1], c[0]) for c in rt["geometry"]["coordinates"]]
    pts, last = [full[0]], full[0]
    for p in full[1:-1]:
        if hav(last, p) >= STEP_M:
            pts.append(p); last = p
    pts.append(full[-1])
    return {"a": a, "alat": alat, "alon": alon, "b": b, "blat": blat, "blon": blon,
            "hr": round(rt["duration"] / 3600, 2), "mi": round(rt["distance"] / 1609.34, 1),
            "pts": [[round(la, 5), round(lo, 5)] for la, lo in pts]}


def main():
    trips = json.load(open(PATH))
    todo = [(a, b) for a, b in PAIRS if f"{a} -> {b}" not in trips]
    print(f"{len(trips)} trips stored; {len(todo)} to add")
    if "--dry-run" in sys.argv:
        for a, b in todo: print("  ", a, "->", b)
        return
    for a, b in todo:
        try:
            t = route(a, b)
        except Exception as e:
            print(f"  skip {a} -> {b}: {e}"); continue
        trips[f"{a} -> {b}"] = t
        print(f"  {a} -> {b}: {t['mi']} mi, {t['hr']} h, {len(t['pts'])} points")
        time.sleep(1.5)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(trips, f, separators=(",", ":"))
    os.replace(tmp, PATH)
    print(f"{len(trips)} trips stored")


if __name__ == "__main__":
    main()
