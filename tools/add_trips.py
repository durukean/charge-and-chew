#!/usr/bin/env python3
"""The road trips behind the /trip/ pages: which drives, where they start and end, their roads.

    python3 tools/add_trips.py                 # route every pair in PAIRS not in data/trips.json
    python3 tools/add_trips.py --refresh       # re-route every pair (end points and roads)
    python3 tools/add_trips.py --places-only   # just look up the end points
    python3 tools/add_trips.py --dry-run       # show what would be fetched

End points. A trip page's "Open this drive in the app" link makes the app look each town up
with Nominatim and route between the answers, and the page's 8 am plan must be the plan the app
then shows. So each town is looked up here the way the app's search does it (index.html
geocode(): "Town, State" spelled out, the same ranking and filters), once, and kept in
data/trip_places.json. A hand-typed city centre started LA -> Las Vegas 200 m from where the app
starts it, which moved a stop's mile and a clock by a step now and then.

Roads. Each pair is routed once by the public OSRM demo server, the app's router, and kept in
data/trips.json: a point every ~450 m (the full line would be ~20 MB for 150 drives), with the
distance and time as OSRM gives them, unrounded, because every clock on the page is drive time.
build.py only ever reads these files, so builds stay offline and reproducible.

Both services are free and shared: one request at a time, a pause between them, a named agent.
"""
import json
import math
import os
import re
import subprocess
import sys
import time
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "data", "trips.json")
PLACES = os.path.join(HERE, "..", "data", "trip_places.json")
OSRM = "https://router.project-osrm.org/route/v1/driving/{},{};{},{}?overview=full&geometries=geojson"
NOMINATIM = "https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&limit=8&countrycodes=us&q="
AGENT = "chargeandchew-trips/1.1 (+https://chargeandchew.com)"
STEP_M = 450          # keep a point every ~450 m: ~3.5 points a mile

# Dropped after routing (2026-11-11), too thin for a page: Kansas City -> Branson and San
# Antonio -> Corpus Christi, the only drives with fewer than 16 fast chargers that have food in
# walking distance (14 and 15). Every drive below has 17 or more.
#
# One direction each, unless both are searched for often (the big holiday pairs): a reverse is
# a different plan (other meal stops at other hours), but still a near-duplicate page.
PAIRS = [
    # the first 43 (October 2026)
    ("Atlanta, GA", "Nashville, TN"), ("Atlanta, GA", "Orlando, FL"), ("Atlanta, GA", "Savannah, GA"),
    ("Austin, TX", "Houston, TX"), ("Boston, MA", "Portland, ME"), ("Charlotte, NC", "Atlanta, GA"),
    ("Chicago, IL", "Detroit, MI"), ("Chicago, IL", "Indianapolis, IN"), ("Dallas, TX", "Austin, TX"),
    ("Dallas, TX", "Houston, TX"), ("Dallas, TX", "Oklahoma City, OK"), ("Denver, CO", "Colorado Springs, CO"),
    ("Denver, CO", "Kansas City, MO"), ("Denver, CO", "Salt Lake City, UT"), ("Detroit, MI", "Cleveland, OH"),
    ("Houston, TX", "New Orleans, LA"), ("Houston, TX", "San Antonio, TX"), ("Kansas City, MO", "St. Louis, MO"),
    ("Las Vegas, NV", "Flagstaff, AZ"), ("Las Vegas, NV", "Salt Lake City, UT"), ("Los Angeles, CA", "Las Vegas, NV"),
    ("Los Angeles, CA", "Palm Springs, CA"), ("Los Angeles, CA", "Phoenix, AZ"), ("Los Angeles, CA", "San Diego, CA"),
    ("Los Angeles, CA", "San Francisco, CA"), ("Miami, FL", "Key West, FL"), ("Miami, FL", "Orlando, FL"),
    ("Minneapolis, MN", "Chicago, IL"), ("Nashville, TN", "Memphis, TN"), ("New York, NY", "Boston, MA"),
    ("New York, NY", "Washington, DC"), ("Orlando, FL", "Tampa, FL"), ("Philadelphia, PA", "Pittsburgh, PA"),
    ("Phoenix, AZ", "Las Vegas, NV"), ("Phoenix, AZ", "Tucson, AZ"), ("Sacramento, CA", "South Lake Tahoe, CA"),
    ("Salt Lake City, UT", "Boise, ID"), ("San Antonio, TX", "El Paso, TX"), ("San Francisco, CA", "Portland, OR"),
    ("San Francisco, CA", "South Lake Tahoe, CA"), ("Seattle, WA", "Portland, OR"), ("Seattle, WA", "Spokane, WA"),
    ("Washington, DC", "Charlotte, NC"),
    # November 2026: holiday drives (Thanksgiving is Nov 26), the reverse of the busiest pairs,
    # the next tier of metro pairs, and the vacation drives people plan around a meal stop.
    # West
    ("San Francisco, CA", "Los Angeles, CA"), ("Las Vegas, NV", "Los Angeles, CA"), ("Phoenix, AZ", "Los Angeles, CA"),
    ("San Diego, CA", "Las Vegas, NV"), ("San Francisco, CA", "Las Vegas, NV"), ("Los Angeles, CA", "Sacramento, CA"),
    ("San Francisco, CA", "Monterey, CA"), ("San Francisco, CA", "Yosemite Valley, CA"), ("San Francisco, CA", "Reno, NV"),
    ("Los Angeles, CA", "Mammoth Lakes, CA"), ("Los Angeles, CA", "Joshua Tree, CA"), ("Phoenix, AZ", "San Diego, CA"),
    ("Los Angeles, CA", "Grand Canyon Village, AZ"), ("Las Vegas, NV", "Grand Canyon Village, AZ"),
    ("Phoenix, AZ", "Sedona, AZ"), ("Phoenix, AZ", "Albuquerque, NM"), ("Denver, CO", "Albuquerque, NM"),
    ("Denver, CO", "Aspen, CO"), ("Denver, CO", "Steamboat Springs, CO"), ("Denver, CO", "Moab, UT"),
    ("Salt Lake City, UT", "Moab, UT"), ("Salt Lake City, UT", "Jackson, WY"), ("Salt Lake City, UT", "West Yellowstone, MT"),
    ("Denver, CO", "Rapid City, SD"), ("Denver, CO", "Omaha, NE"), ("Portland, OR", "Bend, OR"),
    ("Seattle, WA", "Boise, ID"), ("Portland, OR", "Boise, ID"),
    # Texas and the south-central states
    ("Houston, TX", "Dallas, TX"), ("Austin, TX", "Dallas, TX"), ("Houston, TX", "Austin, TX"),
    ("Dallas, TX", "San Antonio, TX"), ("Houston, TX", "Corpus Christi, TX"),
    ("Houston, TX", "South Padre Island, TX"), ("Dallas, TX", "Little Rock, AR"), ("Dallas, TX", "New Orleans, LA"),
    ("Dallas, TX", "Amarillo, TX"), ("Dallas, TX", "Memphis, TN"), ("Dallas, TX", "Kansas City, MO"),
    # Southeast
    ("Atlanta, GA", "Birmingham, AL"), ("Atlanta, GA", "Chattanooga, TN"), ("Atlanta, GA", "Jacksonville, FL"),
    ("Atlanta, GA", "Asheville, NC"), ("Atlanta, GA", "Gatlinburg, TN"), ("Atlanta, GA", "Destin, FL"),
    ("Atlanta, GA", "Tampa, FL"), ("Atlanta, GA", "Miami, FL"), ("Atlanta, GA", "New Orleans, LA"),
    ("Atlanta, GA", "Myrtle Beach, SC"), ("Nashville, TN", "Atlanta, GA"), ("Nashville, TN", "Gatlinburg, TN"),
    ("Nashville, TN", "Louisville, KY"), ("Nashville, TN", "St. Louis, MO"), ("Nashville, TN", "Birmingham, AL"),
    ("Nashville, TN", "Chicago, IL"), ("Memphis, TN", "New Orleans, LA"), ("Jacksonville, FL", "Orlando, FL"),
    ("Tampa, FL", "Miami, FL"), ("Orlando, FL", "Miami, FL"), ("Orlando, FL", "Atlanta, GA"),
    ("Charlotte, NC", "Raleigh, NC"), ("Charlotte, NC", "Myrtle Beach, SC"), ("Charlotte, NC", "Asheville, NC"),
    ("Charlotte, NC", "Charleston, SC"), ("Washington, DC", "Raleigh, NC"),
    # Northeast and mid-Atlantic
    ("Boston, MA", "New York, NY"), ("Washington, DC", "New York, NY"), ("Philadelphia, PA", "Washington, DC"),
    ("Philadelphia, PA", "Boston, MA"), ("New York, NY", "Niagara Falls, NY"), ("New York, NY", "Pittsburgh, PA"),
    ("New York, NY", "Burlington, VT"), ("New York, NY", "Hyannis, MA"), ("New York, NY", "Albany, NY"),
    ("New York, NY", "Lake Placid, NY"), ("New York, NY", "Raleigh, NC"), ("Boston, MA", "Burlington, VT"),
    ("Boston, MA", "Bar Harbor, ME"), ("Boston, MA", "North Conway, NH"), ("Washington, DC", "Pittsburgh, PA"),
    ("Washington, DC", "Richmond, VA"), ("Washington, DC", "Virginia Beach, VA"), ("Washington, DC", "Ocean City, MD"),
    ("Pittsburgh, PA", "Columbus, OH"),
    # Midwest
    ("Chicago, IL", "Minneapolis, MN"), ("Detroit, MI", "Chicago, IL"), ("Chicago, IL", "Madison, WI"),
    ("Chicago, IL", "St. Louis, MO"), ("Chicago, IL", "Columbus, OH"), ("Chicago, IL", "Cincinnati, OH"),
    ("Chicago, IL", "Louisville, KY"), ("Chicago, IL", "Grand Rapids, MI"), ("Chicago, IL", "Traverse City, MI"),
    ("Chicago, IL", "Wisconsin Dells, WI"), ("Chicago, IL", "Kansas City, MO"), ("Chicago, IL", "Omaha, NE"),
    ("Chicago, IL", "Cleveland, OH"), ("Detroit, MI", "Columbus, OH"), ("Detroit, MI", "Traverse City, MI"),
    ("Detroit, MI", "Mackinaw City, MI"), ("Cleveland, OH", "Columbus, OH"), ("Cincinnati, OH", "Cleveland, OH"),
    ("Indianapolis, IN", "Columbus, OH"), ("Indianapolis, IN", "St. Louis, MO"), ("Kansas City, MO", "Omaha, NE"),
    ("St. Louis, MO", "Memphis, TN"), ("Minneapolis, MN", "Duluth, MN"),
    ("Minneapolis, MN", "Des Moines, IA"), ("Minneapolis, MN", "Fargo, ND"),
]

STATE = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
         "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
         "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
         "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
         "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
         "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
         "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
         "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
         "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
         "WI": "Wisconsin", "WY": "Wyoming"}
NOT_A_PLACE = re.compile(r"^(path|footway|track|cycleway|bridleway|steps|viewpoint|trailhead|picnic_site|bench|information)$")
CLASS_BONUS = {"place": 3, "boundary": 3, "landuse": 1}


def hav(a, b):
    R, p = 6371000.0, math.pi / 180
    x = (math.sin((b[0] - a[0]) * p / 2) ** 2 +
         math.cos(a[0] * p) * math.cos(b[0] * p) * math.sin((b[1] - a[1]) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(x))


def get(url):
    # curl, not urllib: the macOS system Python's SSL is too old for these servers' TLS setup.
    out = subprocess.run(["curl", "-sf", "--max-time", "60", "-A", AGENT, url],
                         capture_output=True, check=True).stdout
    return json.loads(out)


def app_query(name):
    """What the app's geocode() sends for "Town, ST": the state spelled out (DC stays DC)."""
    m = re.match(r"^(.*?\S)[,\s]+([A-Za-z]{2})\.?\s*$", name)
    if m and m.group(2).upper() in STATE:
        return f"{m.group(1).rstrip(',')}, {STATE[m.group(2).upper()]}", STATE[m.group(2).upper()]
    return name, None


def geocode(name):
    """index.html geocode() for a typed "Town, ST" with no location known: rank by place class
    and importance, keep the named state, drop paths and viewpoints, keep hits that echo a word
    typed, a town ahead of its own county."""
    q, want = app_query(name)
    hits = get(NOMINATIM + quote(q))
    ranked = sorted(hits, key=lambda h: -(CLASS_BONUS.get(h.get("class"), 0) + float(h.get("importance") or 0)))
    if want:
        ranked = [h for h in ranked if (h.get("address") or {}).get("state") == want]
    ranked = [h for h in ranked if not NOT_A_PLACE.match(h.get("type") or "")]
    words = re.findall(r"[a-z]{4,}", q.lower())
    if words:
        def echoes(h):
            toks = re.findall(r"[a-z]{3,}", ((h.get("display_name") or "") + " " + json.dumps(h.get("address") or {})).lower())
            return any(t.startswith(w[:4]) or w.startswith(t[:4]) for w in words for t in toks)
        ranked = [h for h in ranked if echoes(h)]
    if not ranked:
        raise RuntimeError(f"no place for {name!r}")
    nm = lambda h: (h.get("display_name") or "").split(",")[0].strip().lower()
    if (ranked[0].get("addresstype") == "county" and re.search(r" (county|parish)$", nm(ranked[0]))
            and not re.search(r"\b(county|parish)\b", q.lower())):
        town = next((h for h in ranked if nm(h) == re.sub(r" (county|parish)$", "", nm(ranked[0]))
                     and h.get("class") in ("place", "boundary")), None)
        if town:
            ranked.remove(town); ranked.insert(0, town)
    best = ranked[0]
    return {"lat": float(best["lat"]), "lon": float(best["lon"]), "found": best.get("display_name", "")}


def route(a, b, places):
    pa, pb = places[a], places[b]
    j = get(OSRM.format(pa["lon"], pa["lat"], pb["lon"], pb["lat"]))
    if j.get("code") != "Ok" or not j.get("routes"):
        raise RuntimeError(f"OSRM: {j.get('code')} {j.get('message', '')}")
    rt = j["routes"][0]
    # The app keeps 5 decimals of each point (index.html runRoute): so does this.
    full = [(round(c[1], 5), round(c[0], 5)) for c in rt["geometry"]["coordinates"]]
    pts, last = [full[0]], full[0]
    for p in full[1:-1]:
        if hav(last, p) >= STEP_M:
            pts.append(p); last = p
    pts.append(full[-1])
    return {"a": a, "alat": pa["lat"], "alon": pa["lon"], "b": b, "blat": pb["lat"], "blon": pb["lon"],
            "hr": rt["duration"] / 3600, "mi": rt["distance"] / 1609.34, "pts": [list(p) for p in pts]}


def save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"), sort_keys=path == PLACES)
    os.replace(tmp, path)


def main():
    trips = json.load(open(PATH)) if os.path.exists(PATH) else {}
    places = json.load(open(PLACES)) if os.path.exists(PLACES) else {}
    refresh = "--refresh" in sys.argv
    names = sorted({n for p in PAIRS for n in p})
    need = [n for n in names if n not in places]
    todo = [(a, b) for a, b in PAIRS if refresh or f"{a} -> {b}" not in trips]
    print(f"{len(PAIRS)} drives, {len(names)} places ({len(need)} to look up), {len(todo)} to route")
    if "--dry-run" in sys.argv:
        for n in need: print("   look up", n)
        for a, b in todo: print("   route", a, "->", b)
        return
    for n in need:
        try:
            places[n] = geocode(n)
            print(f"  {n}: {places[n]['lat']:.4f}, {places[n]['lon']:.4f}  ({places[n]['found'][:70]})")
        except Exception as e:
            print(f"  skip {n}: {e}")
        save(PLACES, places)
        time.sleep(1.1)
    if "--places-only" in sys.argv:
        return
    for a, b in todo:
        if a not in places or b not in places:
            print(f"  skip {a} -> {b}: no place"); continue
        try:
            t = route(a, b, places)
        except Exception as e:
            print(f"  skip {a} -> {b}: {e}"); continue
        trips[f"{a} -> {b}"] = t
        print(f"  {a} -> {b}: {t['mi']:.1f} mi, {t['hr']:.2f} h, {len(t['pts'])} points")
        save(PATH, trips)
        time.sleep(1.5)
    # A drive taken off PAIRS goes from the cache too, so build.py stops making its page.
    gone = [k for k in trips if tuple(k.split(" -> ")) not in set(PAIRS)]
    for k in gone:
        del trips[k]; print(f"  dropped {k}")
    save(PATH, trips)
    for n in [n for n in places if n not in names]:
        del places[n]
    save(PLACES, places)
    print(f"{len(trips)} trips stored")


if __name__ == "__main__":
    main()
