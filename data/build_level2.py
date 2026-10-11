#!/usr/bin/env python3
"""Level 2 chargers at the chains -> level2.js, an optional layer the app loads on demand.

Level 2 ("regular", J1772) adds roughly 20-30 miles per hour parked: little on a 20-minute
stop, a lot over a sit-down meal or a big shop. The US has ~68,600 public Level 2 stations
against ~15,900 fast ones, so shipping them all inside data.js would multiply every visitor's
download. Only the ones at a chain we track -- within LOT_M of it, i.e. the same lot or
shopping centre -- are kept, in their own file that is fetched only when someone switches
Level 2 on (measured 2026-10-11: ~16,500 stations within 200 m).

    python3 data/build_level2.py                 # fetch from AFDC (needs AFDC_API_KEY)
    python3 data/build_level2.py --raw FILE.json # build from a saved AFDC response

Shape (fmt 1), mirroring data.js: {"fmt", "generated", "walkM", "lotM", "sites", "matches"}.
A site is {id, name, lat, lon, city, st, street, net, stalls (= ports), kw (0 = not listed),
conn (8 = J1772, 2 = Tesla destination), price, h24, lvl: 2}. matches is the same delta format
as data.js: chain -> [dLat, dLon] x1e4, nearest first, for every tracked chain within walkM.
"""
import json, math, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from fetch_chargers import HOST, KEY, net_name                     # noqa: E402
from build_data import pretty_name, PRIVATE_RE, DEALER_RE, WALK_M  # noqa: E402
from data_reader import load_data                                  # noqa: E402

FMT = 1
LOT_M = 200          # "at the chain": same parking lot or shopping centre
MAX_MATCHES = 6      # walkable chains kept per site beyond those in its lot: Level 2 is about
                     # the place you park at, and every chain within 800 m doubled the file
MIN_SITES = 8000     # a normal build is ~16k; far fewer means a short or broken API response
MAX_DROP = 0.25      # and never silently lose this much against the live file
L2_BIT = {"J1772": 8, "TESLA": 2, "J3271": 2}
OUT = os.path.join(ROOT, "level2.js")


def fetch():
    params = urllib.parse.urlencode({
        "api_key": KEY, "fuel_type": "ELEC", "ev_charging_level": "2",
        "country": "US", "status": "E", "access": "public", "limit": "all"})
    req = urllib.request.Request(f"{HOST}/api/alt-fuel-stations/v1.json?{params}",
                                 headers={"User-Agent": "chargeandchew/1.0"})
    print("Fetching all US public Level 2 stations…", flush=True)
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["fuel_stations"]


def hav(a1, o1, a2, o2):
    R, p = 6371000.0, math.pi / 180
    a = (math.sin((a2 - a1) * p / 2) ** 2 +
         math.cos(a1 * p) * math.cos(a2 * p) * math.sin((o2 - o1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def distill(s):
    lat, lon = s.get("latitude"), s.get("longitude")
    if lat is None or lon is None:
        return None
    conn, kw = 0, 0
    for unit in (s.get("ev_charging_units") or []):
        if str(unit.get("charging_level")) != "2":
            continue
        for cname, c in (unit.get("connectors") or {}).items():
            bit = L2_BIT.get(cname)
            if bit and (c.get("port_count") or 0) > 0:
                conn |= bit
                if c.get("power_kw"):
                    kw = max(kw, int(round(c["power_kw"])))
    if not conn:
        for cname in (s.get("ev_connector_types") or []):
            conn |= L2_BIT.get(cname, 0)
    ports = s.get("ev_level2_evse_num") or 0
    if not conn or not ports:
        return None
    name = pretty_name((s.get("station_name") or "").strip()[:60])
    if PRIVATE_RE.search(name):
        return None
    pricing = (s.get("ev_pricing") or "").strip().lower()
    price = ("free" if pricing.startswith("free") and "$" not in pricing and " then " not in pricing
             else "paid" if pricing and pricing not in ("call for pricing", "unknown") else "")
    out = {"id": s["id"], "name": name or (s.get("street_address") or "Level 2 charger")[:60],
           "lat": round(lat, 5), "lon": round(lon, 5),
           "city": s.get("city") or "", "st": s.get("state") or "",
           "street": (s.get("street_address") or "")[:60],
           "net": net_name(s.get("ev_network"))[0], "stalls": ports,
           "kw": kw if 3 <= kw <= 25 else 0,          # outside this is a data error, not Level 2
           "conn": conn, "price": price,
           "h24": 1 if "24 hour" in (s.get("access_days_time") or "").lower() else 0, "lvl": 2}
    if DEALER_RE.search(out["name"]):
        out["dlr"] = 1
    return out


def main():
    raw_path = sys.argv[sys.argv.index("--raw") + 1] if "--raw" in sys.argv else None
    stations = json.load(open(raw_path))["fuel_stations"] if raw_path else fetch()
    dc = load_data(os.path.join(ROOT, "data.js"))
    dc_ids = {s["id"] for s in dc["sites"]}
    pois = json.load(open(os.path.join(HERE, "pois.json")))
    brands = dc["brands"]                                     # same chains as the app

    cell = 0.01
    grid = {}
    for key, pts in pois.items():
        if key not in brands:
            continue
        for p in pts:
            grid.setdefault((int(p["lat"] / cell), int(p["lon"] / cell)), []).append((key, p["lat"], p["lon"]))

    sites, matches, seen = [], {}, {}
    skipped = dict(dc=0, bad=0, far=0, dup=0)
    for st in stations:
        if st.get("id") in dc_ids:            # also has fast charging: already in data.js
            skipped["dc"] += 1; continue
        s = distill(st)
        if not s:
            skipped["bad"] += 1; continue
        k = (round(s["lat"], 4), round(s["lon"], 4), s["net"])
        if k in seen:
            # Level 2 sites are often listed once per charger at the same spot: one site,
            # with the ports added up and every plug kept.
            first = seen[k]
            first["stalls"] += s["stalls"]; first["conn"] |= s["conn"]; first["kw"] = max(first["kw"], s["kw"])
            skipped["dup"] += 1; continue
        seen[k] = s
        c0 = (int(s["lat"] / cell), int(s["lon"] / cell))
        found = {}
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for key, pla, plo in grid.get((c0[0] + di, c0[1] + dj), ()):
                    d = hav(s["lat"], s["lon"], pla, plo)
                    if d <= WALK_M and (key not in found or d < found[key][0]):
                        found[key] = (d, pla, plo)
        if not found or min(v[0] for v in found.values()) > LOT_M:
            skipped["far"] += 1; continue
        sites.append(s)
        near = sorted(found.items(), key=lambda x: x[1][0])
        near = [x for i, x in enumerate(near) if x[1][0] <= LOT_M or i < MAX_MATCHES]
        matches[s["id"]] = {key: [round((pla - s["lat"]) * 1e4), round((plo - s["lon"]) * 1e4)]
                            for key, (d, pla, plo) in near}

    if len(sites) < MIN_SITES:
        raise SystemExit(f"ABORT: only {len(sites)} Level 2 sites at chains (expected ~16k). level2.js not written.")
    if os.path.exists(OUT):
        try:
            old = load_data(OUT, prefix="window.PITSTOP_L2")
        except Exception as e:
            raise SystemExit(f"ABORT: cannot read the existing level2.js ({e}); level2.js not written.")
        drop = 1 - len(sites) / max(1, len(old.get("sites", [])))
        if drop > MAX_DROP:
            raise SystemExit(f"ABORT: Level 2 sites fell {drop:.0%} ({len(old['sites'])} -> {len(sites)}).")

    payload = {"fmt": FMT, "generated": time.strftime("%Y-%m-%d"), "walkM": WALK_M, "lotM": LOT_M,
               "sites": sites, "matches": matches}
    compact = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    esc = (compact.replace("\\", "\\\\").replace("'", "\\'")
                  .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    with open(OUT + ".tmp", "w", encoding="utf-8") as f:
        f.write("window.PITSTOP_L2 = JSON.parse('" + esc + "');\n")
    os.replace(OUT + ".tmp", OUT)
    print(f"level2.js: {len(sites)} Level 2 sites within {LOT_M} m of a chain "
          f"({os.path.getsize(OUT) // 1024} KB); skipped {skipped}")


if __name__ == "__main__":
    main()
