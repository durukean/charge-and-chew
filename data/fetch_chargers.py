#!/usr/bin/env python3
"""Pull all US public DC-fast charging stations (every network) from the
US DOE / NREL Alternative Fuel Stations API and distill to a compact file.

Output: data/chargers.json  — list of {id,name,lat,lon,city,st,street,net,
        stalls,kw,conn,price,h24}
  conn is a bitmask: 1=CCS1 (J1772COMBO), 2=NACS/Tesla, 4=CHAdeMO
  price: 'free' | 'paid' | '' (unknown)

API key: set AFDC_API_KEY env var. Falls back to DEMO_KEY (10 req/hour, shared).
Get a free key at https://developer.nlr.gov/signup/  (or api.data.gov).
Data is US Government public-domain.
"""
import json, os, sys, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get("AFDC_API_KEY", "DEMO_KEY")
HOST = "https://developer.nlr.gov"

# AFDC network code -> (display name, marker colour)
# Mirror of NETCOL in index.html (the app overrides these at render time; keep both
# in sync so a fresh fetch matches). No pure red — red pins read as "out of service".
NETWORKS = {
    "Tesla":               ("Tesla Supercharger", "#ff6b5a"),
    "Tesla Destination":   ("Tesla Destination",  "#ff6b5a"),
    "ChargePoint Network": ("ChargePoint",        "#f59e0b"),
    "Electrify America":   ("Electrify America",  "#22c55e"),
    "eVgo Network":        ("EVgo",               "#14b8a6"),
    "EV Connect":          ("EV Connect",         "#6366f1"),
    "Blink Network":       ("Blink",              "#0ea5e9"),
    "FORD_CHARGE":         ("Ford BlueOval",      "#2563eb"),
    "IONNA":               ("IONNA",              "#7c3aed"),
    "RIVIAN_ADVENTURE":    ("Rivian Adventure",   "#0891b2"),
    "RIVIAN_WAYPOINTS":    ("Rivian Waypoints",   "#0891b2"),
    "FLO":                 ("FLO",                "#10b981"),
    "BP_PULSE":            ("bp pulse",           "#059669"),
    "SHELL_RECHARGE":      ("Shell Recharge",     "#eab308"),
    "EVCS":                ("EVCS",               "#84cc16"),
    "RED_E":               ("Red E",              "#a855f7"),
    "WALMART":             ("Walmart Charge",     "#3b82f6"),
    "FCN":                 ("Francis Energy",     "#c084fc"),
    "CHARGELAB":           ("ChargeLab",          "#64748b"),
    "EVGATEWAY":           ("EV Gateway",         "#818cf8"),
    "FPLEV":               ("FPL EVolution",      "#34d399"),
    "Non-Networked":       ("Non-networked",      "#94a3b8"),
}
def net_name(code):
    if not code or code == "Non-Networked":
        return "Non-networked", "#94a3b8"
    if code in NETWORKS:
        return NETWORKS[code]
    return code.replace("_", " ").title(), "#94a3b8"

CONN_BIT = {"J1772COMBO": 1, "TESLA": 2, "J3271": 2, "CHADEMO": 4}  # J3271 = NACS


def fetch():
    params = urllib.parse.urlencode({
        "api_key": KEY, "fuel_type": "ELEC", "ev_charging_level": "dc_fast",
        "country": "US", "status": "E", "access": "public", "limit": "all"})
    url = f"{HOST}/api/alt-fuel-stations/v1.json?{params}"
    print(f"Fetching all US public DC-fast stations (key={'DEMO_KEY' if KEY=='DEMO_KEY' else 'custom'})…", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "chargeandchew/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["fuel_stations"]


def distill(fs):
    out = []
    for s in fs:
        lat, lon = s.get("latitude"), s.get("longitude")
        if lat is None or lon is None:
            continue
        # connectors + max DC power from the detailed units, fall back to summary
        conn = 0
        maxkw = 0
        for unit in (s.get("ev_charging_units") or []):
            if unit.get("charging_level") != "dc_fast":
                continue
            for cname, c in (unit.get("connectors") or {}).items():
                bit = CONN_BIT.get(cname)
                if bit and (c.get("port_count") or 0) > 0:
                    conn |= bit
                    if c.get("power_kw"):
                        maxkw = max(maxkw, int(round(c["power_kw"])))
        if conn == 0:  # fall back to the flat connector list
            for cname in (s.get("ev_connector_types") or []):
                conn |= CONN_BIT.get(cname, 0)
        if conn == 0:
            continue  # no usable DC connector
        name, color = net_name(s.get("ev_network"))
        pricing = (s.get("ev_pricing") or "").strip().lower()
        # 'Free' / 'Free; ...' -> free, but 'free for 30 min then $x' style -> unknown (safer than wrong)
        if pricing.startswith("free") and "$" not in pricing and " then " not in pricing:
            price = "free"
        elif pricing and pricing not in ("call for pricing", "unknown"):
            price = "paid"
        else:
            price = ""
        hours = (s.get("access_days_time") or "")
        out.append({
            "id": s["id"],
            "name": s.get("station_name", "").strip()[:60],
            "lat": round(lat, 5), "lon": round(lon, 5),
            "city": s.get("city", "") or "", "st": s.get("state", "") or "",
            "street": (s.get("street_address") or "")[:60],
            "net": name, "col": color,
            "stalls": s.get("ev_dc_fast_num") or 0,
            "kw": maxkw,
            "conn": conn,
            "price": price,
            "h24": 1 if "24 hour" in hours.lower() else 0,
        })
    return out


# A partial API response must never reach the site. The shared DEMO_KEY is rate-limited and
# AFDC occasionally returns short payloads; without this the pipeline would happily rebuild
# every page from a fraction of the data and push it live.
MIN_STATIONS = 9000          # we normally distill ~15k; well below that means something broke
MAX_DROP_PCT = 15            # and never silently lose this much vs the previous good run


def sanity_check(out, prev_path):
    if len(out) < MIN_STATIONS:
        raise SystemExit(f"ABORT: only {len(out)} stations distilled, expected >= {MIN_STATIONS}. "
                         f"Refusing to overwrite chargers.json — the API response was probably "
                         f"truncated or rate-limited. Nothing was changed.")
    if os.path.exists(prev_path):
        try:
            prev = json.load(open(prev_path))
        except Exception:
            return
        if prev and len(out) < len(prev) * (1 - MAX_DROP_PCT / 100):
            raise SystemExit(f"ABORT: {len(out)} stations is a "
                             f"{100 * (1 - len(out) / len(prev)):.0f}% drop from the previous "
                             f"{len(prev)}. That is almost certainly a bad fetch, not reality. "
                             f"Re-run, or delete chargers.json deliberately if the drop is real.")
        # a healthy run should still have plenty of connector and power data
        if sum(1 for x in out if x.get("kw")) < len(out) * 0.5:
            raise SystemExit("ABORT: over half the stations have no power rating — the response "
                             "shape probably changed. Check ev_charging_units in the API.")


def main():
    fs = fetch()
    print(f"  {len(fs)} stations returned", flush=True)
    out = distill(fs)
    path = os.path.join(HERE, "chargers.json")
    sanity_check(out, path)
    json.dump(out, open(path, "w"), separators=(",", ":"))
    import collections
    nets = collections.Counter(s["net"] for s in out)
    conn = collections.Counter()
    for s in out:
        if s["conn"] & 1: conn["CCS1"] += 1
        if s["conn"] & 2: conn["NACS"] += 1
        if s["conn"] & 4: conn["CHAdeMO"] += 1
    print(f"Kept {len(out)} DC-fast stations. Top networks:")
    for n, c in nets.most_common(12):
        print(f"  {c:5d}  {n}")
    print("Connectors:", dict(conn))
    haskw = sum(1 for s in out if s["kw"])
    print(f"Have power rating: {haskw}/{len(out)}")


if __name__ == "__main__":
    main()
