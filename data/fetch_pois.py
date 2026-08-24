#!/usr/bin/env python3
"""Fetch US locations of popular road-trip chains from Overpass (OSM).

Output: data/pois.json — {brand: [{lat,lon}, ...]}, used as a cache so reruns
skip brands already fetched. Delete a brand's entry to refetch just that one.

This script does NOT build data.js — run data/build_data.py for that.
"""
import json, math, os, re, sys, time, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
OVERPASS = "https://overpass-api.de/api/interpreter"
WALK_M = 800  # max walking distance (~10 min)

# key -> (emoji, category, brand-tag regex)
BRANDS = {
    "IHOP":            ("🥞", "food",  r"^IHOP$"),
    "Denny's":         ("🍳", "food",  r"^Denny'?s$"),
    "Waffle House":    ("🧇", "food",  r"^Waffle House$"),
    "Cracker Barrel":  ("🪵", "food",  r"^Cracker Barrel"),
    "McDonald's":      ("🍟", "food",  r"^McDonald'?s$"),
    "Chick-fil-A":     ("🐔", "food",  r"^Chick-fil-A$"),
    "In-N-Out":        ("🍔", "food",  r"^In-N-Out"),
    "Whataburger":     ("🍔", "food",  r"^Whataburger$"),
    "Culver's":        ("🍦", "food",  r"^Culver'?s$"),
    "Chipotle":        ("🌯", "food",  r"^Chipotle"),
    "Panera Bread":    ("🥖", "food",  r"^Panera"),
    "Starbucks":       ("☕", "food",  r"^Starbucks"),
    "Dunkin'":         ("🍩", "food",  r"^Dunkin"),
    "Taco Bell":       ("🌮", "food",  r"^Taco Bell$"),
    "Wendy's":         ("🍔", "food",  r"^Wendy'?s$"),
    "Burger King":     ("👑", "food",  r"^Burger King$"),
    "Five Guys":       ("🍔", "food",  r"^Five Guys$"),
    "Olive Garden":    ("🍝", "food",  r"^Olive Garden$"),
    "Panda Express":   ("🐼", "food",  r"^Panda Express$"),
    "Subway":          ("🥪", "food",  r"^Subway$"),
    "Walmart":         ("🛒", "store", r"^Walmart"),
    "Target":          ("🎯", "store", r"^Target$"),
    "Costco":          ("📦", "store", r"^Costco"),
    "Buc-ee's":        ("🦫", "store", r"^Buc-ee'?s$"),
    "Sheetz":          ("⛽", "store", r"^Sheetz$"),
    "Wawa":            ("🦆", "store", r"^Wawa$"),
    "Whole Foods":     ("🥬", "store", r"^Whole Foods"),
    "Trader Joe's":    ("🛍️", "store", r"^Trader Joe'?s$"),
    "Sonic":           ("🚗", "food",  r"^Sonic( Drive-?In)?$"),   # OSM tags these just "Sonic"
    "Dairy Queen":     ("🍦", "food",  r"^Dairy Queen"),
    "KFC":             ("🍗", "food",  r"^KFC$"),
    "Popeyes":         ("🍗", "food",  r"^Popeyes"),
    "Arby's":          ("🥩", "food",  r"^Arby'?s$"),
    "Jack in the Box": ("🤡", "food",  r"^Jack in the Box$"),
    "Raising Cane's":  ("🐕", "food",  r"^Raising Cane'?s"),
    "Zaxby's":         ("🍗", "food",  r"^Zaxby'?s$"),
    "Bojangles":       ("🍗", "food",  r"^Bojangles"),
    "Carl's Jr.":      ("⭐", "food",  r"^Carl'?s Jr\.?$"),
    "Hardee's":        ("⭐", "food",  r"^Hardee'?s$"),
    "Del Taco":        ("🌮", "food",  r"^Del Taco$"),
    "Jersey Mike's":   ("🥪", "food",  r"^Jersey Mike'?s"),
    "Firehouse Subs":  ("🚒", "food",  r"^Firehouse Subs$"),
    "Wingstop":        ("🍗", "food",  r"^Wingstop$"),
    "Shake Shack":     ("🍔", "food",  r"^Shake Shack$"),
    "Applebee's":      ("🍎", "food",  r"^Applebee'?s"),
    "Chili's":         ("🌶️", "food",  r"^Chili'?s"),
    "Texas Roadhouse": ("🤠", "food",  r"^Texas Roadhouse$"),
    "Buffalo Wild Wings": ("🦬","food",r"^Buffalo Wild Wings$"),
    "Red Robin":       ("🐦", "food",  r"^Red Robin"),
    "Domino's":        ("🍕", "food",  r"^Domino'?s"),
    "Pizza Hut":       ("🍕", "food",  r"^Pizza Hut$"),
    "Little Caesars":  ("🍕", "food",  r"^Little Caesars"),
    "Dutch Bros":      ("☕", "food",  r"^Dutch Bros"),
    "Peet's Coffee":   ("☕", "food",  r"^Peet'?s Coffee"),
    "Caribou Coffee":  ("☕", "food",  r"^Caribou Coffee$"),
    "Sam's Club":      ("🏪", "store", r"^Sam'?s Club$"),
    "Kroger":          ("🛒", "store", r"^Kroger$"),
    "Safeway":         ("🛒", "store", r"^Safeway$"),
    "Publix":          ("🛒", "store", r"^Publix"),
    "H-E-B":           ("🛒", "store", r"^H-E-B$"),
    "Aldi":            ("🛒", "store", r"^A[Ll][Dd][Ii]$"),
    "Home Depot":      ("🔨", "store", r"^(The )?Home Depot$"),
    "Lowe's":          ("🔧", "store", r"^Lowe'?s($| Home)"),
    "Best Buy":        ("💻", "store", r"^Best Buy$"),
    "IKEA":            ("🪑", "store", r"^IKEA$"),
    "Walgreens":       ("💊", "store", r"^Walgreens$"),
    "CVS":             ("💊", "store", r"^CVS( Pharmacy)?$"),
    "Love's":          ("⛽", "store", r"^Love'?s$"),   # OSM tags these just "Love's"
    "Pilot":           ("⛽", "store", r"^Pilot( Travel Center)?$"),
    "Flying J":        ("⛽", "store", r"^(Pilot )?Flying J$"),
    "QuikTrip":        ("⛽", "store", r"^QuikTrip$"),
    "RaceTrac":        ("⛽", "store", r"^RaceTrac$"),
    "Kwik Trip":       ("⛽", "store", r"^Kwik Trip$"),
    "Speedway":        ("⛽", "store", r"^Speedway$"),
    "TA Travel Center":("⛽", "store", r"^TA( Travel Center)?$"),
}

def overpass(brand_key, regex, tries=4):
    q = f"""[out:json][timeout:300];
area["ISO3166-1"="US"][admin_level=2]->.us;
nwr["brand"~"{regex}"](area.us);
out center qt;"""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                OVERPASS,
                data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": "pitstop-mvp/0.1 (personal project)"})
            with urllib.request.urlopen(req, timeout=360) as r:
                data = json.load(r)
            out = []
            for el in data.get("elements", []):
                lat = el.get("lat") or el.get("center", {}).get("lat")
                lon = el.get("lon") or el.get("center", {}).get("lon")
                if lat is None:
                    continue
                out.append({"lat": round(lat, 5), "lon": round(lon, 5)})
            return out
        except Exception as e:
            wait = 20 * (attempt + 1)
            print(f"  {brand_key}: attempt {attempt+1} failed ({e}); retry in {wait}s", flush=True)
            time.sleep(wait)
    return None

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def main():
    cache_path = os.path.join(HERE, "pois.json")
    pois = {}
    if os.path.exists(cache_path):
        pois = json.load(open(cache_path))

    for key, (emoji, cat, regex) in BRANDS.items():
        if key in pois:
            print(f"{key}: cached ({len(pois[key])})", flush=True)
            continue
        print(f"{key}: fetching...", flush=True)
        res = overpass(key, regex)
        if res is None:
            print(f"{key}: FAILED, skipping for now", flush=True)
            continue
        pois[key] = res
        print(f"{key}: {len(res)} locations", flush=True)
        json.dump(pois, open(cache_path, "w"))
        time.sleep(8)  # be polite to overpass

    # Sanity check: a brand whose OSM count collapses is almost always a bad regex
    # (Love's silently returned 1 POI for weeks because OSM tags it "Love's", not
    # "Love's Travel Stop"). Warn loudly instead of shipping an empty chain.
    thin = {k: len(v) for k, v in pois.items() if len(v) < 40}
    if thin:
        print("\n!! Suspiciously few POIs — check the brand regex for:", flush=True)
        for k, n in sorted(thin.items(), key=lambda x: x[1]):
            print(f"     {k}: {n}", flush=True)
    print(f"\nCached {len(pois)} brands, {sum(len(v) for v in pois.values())} POIs total.")
    print("Run data/build_data.py next — this script no longer writes data.js.")


if __name__ == "__main__":
    main()
