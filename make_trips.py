#!/usr/bin/env python3
"""Fetch and cache driving geometry for the trip landing pages.

Deliberately separate from build.py, for the same reason make_og.py is: build.py runs in CI
on every data refresh and must not depend on a third-party demo server being up. This writes
data/trips.json, that file is committed, and build.py only ever reads it. Re-run this by hand
when you add a trip to TRIPS; it skips anything already cached.

    python3 make_trips.py           # fetch missing routes
    python3 make_trips.py --force   # refetch everything
"""
import json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "trips.json")
OSRM = "https://router.project-osrm.org/route/v1/driving"

# (from, from lat/lon, to, to lat/lon). One direction each -- the reverse of a route is a
# near-duplicate page, and the corpus audit counts those against us.
TRIPS = [
    ("Los Angeles, CA", 34.0522, -118.2437, "Las Vegas, NV", 36.1699, -115.1398),
    ("Los Angeles, CA", 34.0522, -118.2437, "San Francisco, CA", 37.7749, -122.4194),
    ("Los Angeles, CA", 34.0522, -118.2437, "San Diego, CA", 32.7157, -117.1611),
    ("Los Angeles, CA", 34.0522, -118.2437, "Phoenix, AZ", 33.4484, -112.0740),
    ("San Francisco, CA", 37.7749, -122.4194, "Portland, OR", 45.5152, -122.6784),
    ("Seattle, WA", 47.6062, -122.3321, "Portland, OR", 45.5152, -122.6784),
    ("Sacramento, CA", 38.5816, -121.4944, "South Lake Tahoe, CA", 38.9399, -119.9772),
    ("Las Vegas, NV", 36.1699, -115.1398, "Salt Lake City, UT", 40.7608, -111.8910),
    ("Phoenix, AZ", 33.4484, -112.0740, "Las Vegas, NV", 36.1699, -115.1398),
    ("Denver, CO", 39.7392, -104.9903, "Salt Lake City, UT", 40.7608, -111.8910),
    ("Denver, CO", 39.7392, -104.9903, "Colorado Springs, CO", 38.8339, -104.8214),
    ("Dallas, TX", 32.7767, -96.7970, "Austin, TX", 30.2672, -97.7431),
    ("Dallas, TX", 32.7767, -96.7970, "Houston, TX", 29.7604, -95.3698),
    ("Houston, TX", 29.7604, -95.3698, "San Antonio, TX", 29.4241, -98.4936),
    ("Austin, TX", 30.2672, -97.7431, "Houston, TX", 29.7604, -95.3698),
    ("Chicago, IL", 41.8781, -87.6298, "Detroit, MI", 42.3314, -83.0458),
    ("Chicago, IL", 41.8781, -87.6298, "Indianapolis, IN", 39.7684, -86.1581),
    ("Minneapolis, MN", 44.9778, -93.2650, "Chicago, IL", 41.8781, -87.6298),
    ("Detroit, MI", 42.3314, -83.0458, "Cleveland, OH", 41.4993, -81.6944),
    ("New York, NY", 40.7128, -74.0060, "Boston, MA", 42.3601, -71.0589),
    ("New York, NY", 40.7128, -74.0060, "Washington, DC", 38.9072, -77.0369),
    ("Philadelphia, PA", 39.9526, -75.1652, "Pittsburgh, PA", 40.4406, -79.9959),
    ("Washington, DC", 38.9072, -77.0369, "Charlotte, NC", 35.2271, -80.8431),
    ("Atlanta, GA", 33.7490, -84.3880, "Nashville, TN", 36.1627, -86.7816),
    ("Atlanta, GA", 33.7490, -84.3880, "Orlando, FL", 28.5383, -81.3792),
    ("Miami, FL", 25.7617, -80.1918, "Orlando, FL", 28.5383, -81.3792),
    ("Orlando, FL", 28.5383, -81.3792, "Tampa, FL", 27.9506, -82.4572),
    ("Charlotte, NC", 35.2271, -80.8431, "Atlanta, GA", 33.7490, -84.3880),
]


def key(a, b):
    return f"{a} -> {b}"


def fetch(fa, fo, ta, to):
    """curl, not urllib: the system python here fails the OSRM TLS handshake."""
    url = f"{OSRM}/{fo},{fa};{to},{ta}?overview=full&geometries=geojson"
    raw = subprocess.run(["curl", "-sS", "--max-time", "40", url],
                         capture_output=True, text=True).stdout
    j = json.loads(raw)
    if j.get("code") != "Ok" or not j.get("routes"):
        raise RuntimeError(j.get("code", "no route"))
    r = j["routes"][0]
    pts = [[round(c[1], 5), round(c[0], 5)] for c in r["geometry"]["coordinates"]]
    # Thin the line: these are only used to decide which chargers sit near the corridor, and
    # the full 2,200-point geometry makes the cache file pointlessly large.
    if len(pts) > 900:
        step = len(pts) // 900 + 1
        pts = pts[::step] + [pts[-1]]
    return {"mi": round(r["distance"] / 1609.34, 1),
            "hr": round(r["duration"] / 3600, 2), "pts": pts}


def main():
    force = "--force" in sys.argv
    cache = {}
    if os.path.exists(OUT) and not force:
        cache = json.load(open(OUT))
    todo = [t for t in TRIPS if key(t[0], t[3]) not in cache]
    print(f"{len(cache)} cached, {len(todo)} to fetch")
    for a, fa, fo, b, ta, to in todo:
        k = key(a, b)
        try:
            cache[k] = fetch(fa, fo, ta, to)
            cache[k].update(a=a, b=b, alat=fa, alon=fo, blat=ta, blon=to)
            print(f"  ok   {k}  {cache[k]['mi']} mi")
        except Exception as e:
            print(f"  FAIL {k}: {e}")
        time.sleep(1.2)          # the demo server is a shared courtesy, not a product
    # drop anything no longer in TRIPS so removing a trip actually removes its page
    live = {key(t[0], t[3]) for t in TRIPS}
    cache = {k: v for k, v in cache.items() if k in live}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(cache, open(OUT, "w"), separators=(",", ":"), sort_keys=True)
    print(f"wrote {OUT}: {len(cache)} routes, {os.path.getsize(OUT)//1024} KB")
    return 0 if len(cache) == len(TRIPS) else 1


if __name__ == "__main__":
    sys.exit(main())
