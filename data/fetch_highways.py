#!/usr/bin/env python3
"""Fetch simplified centre-lines for major US interstates from OSM.

Output: data/highways.json  {"I 95": [[lat,lon], ...ordered-ish...], ...}

Used by build.py to generate /along/<interstate>/ corridor pages — "EV chargers
with food along I-95" is a real search intent that nothing currently serves well.
Points are thinned to ~1 km spacing; we only need proximity, not navigation.
"""
import json, math, os, time, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
OVERPASS = "https://overpass-api.de/api/interpreter"
US_BBOX = "24.0,-125.5,49.5,-66.5"
THIN_M = 1000            # keep one point per ~km

INTERSTATES = ["I 95","I 10","I 5","I 80","I 40","I 90","I 75","I 70","I 35","I 20",
               "I 25","I 15","I 65","I 55","I 94","I 85","I 45","I 30","I 84","I 77",
               "I 64","I 81","I 4","I 24","I 44","I 91","I 71","I 96","I 74","I 26"]

def hav(a1, o1, a2, o2):
    R = 6371000; p = math.pi / 180
    x = math.sin((a2-a1)*p/2)**2 + math.cos(a1*p)*math.cos(a2*p)*math.sin((o2-o1)*p/2)**2
    return 2 * R * math.asin(math.sqrt(x))

def overpass(ref, tries=3):
    q = (f'[out:json][timeout:280];'
         f'way["highway"="motorway"]["ref"~"(^|;){ref}(;|$)"]({US_BBOX});out geom;')
    for a in range(tries):
        try:
            req = urllib.request.Request(OVERPASS,
                data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": "chargeandchew/1.0 (chargeandchew.com)"})
            with urllib.request.urlopen(req, timeout=320) as r:
                return json.load(r)
        except Exception as e:
            print(f"    attempt {a+1} failed: {e}", flush=True)
            time.sleep(20 * (a + 1))
    return None

def thin(points):
    """Drop points closer than THIN_M to the last kept one."""
    out = []
    for p in points:
        if not out or hav(out[-1][0], out[-1][1], p[0], p[1]) >= THIN_M:
            out.append(p)
    return out

def main():
    path = os.path.join(HERE, "highways.json")
    data = json.load(open(path)) if os.path.exists(path) else {}
    for ref in INTERSTATES:
        if ref in data:
            print(f"{ref}: cached ({len(data[ref])} pts)", flush=True); continue
        print(f"{ref}: fetching…", flush=True)
        d = overpass(ref)
        if not d:
            print(f"{ref}: FAILED", flush=True); continue
        pts = []
        for w in d.get("elements", []):
            for g in w.get("geometry", []) or []:
                pts.append([round(g["lat"], 4), round(g["lon"], 4)])
        # sort roughly along the road so listings read north->south / west->east
        if pts:
            span_lat = max(p[0] for p in pts) - min(p[0] for p in pts)
            span_lon = max(p[1] for p in pts) - min(p[1] for p in pts)
            pts.sort(key=lambda p: -p[0] if span_lat >= span_lon else p[1])
        kept = thin(pts)
        data[ref] = kept
        print(f"{ref}: {len(pts)} pts -> {len(kept)} after thinning", flush=True)
        json.dump(data, open(path, "w"), separators=(",", ":"))
        time.sleep(6)
    print(f"\nDone: {len(data)} interstates, {sum(len(v) for v in data.values())} points")

if __name__ == "__main__":
    main()
