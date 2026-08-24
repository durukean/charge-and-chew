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

# AFDC network code -> (display name, brand color)
NETWORKS = {
    "Tesla":               ("Tesla Supercharger", "#e82127"),
    "Tesla Destination":   ("Tesla Destination",  "#e82127"),
    "ChargePoint Network": ("ChargePoint",        "#f7941e"),
    "Electrify America":   ("Electrify America",  "#00b04f"),
    "eVgo Network":        ("EVgo",               "#00a3a3"),
    "EV Connect":          ("EV Connect",         "#5b6cff"),
    "Blink Network":       ("Blink",              "#00b0e6"),
    "FORD_CHARGE":         ("Ford BlueOval",      "#1a56db"),
    "IONNA":               ("IONNA",              "#6d4bff"),
    "RIVIAN_ADVENTURE":    ("Rivian Adventure",   "#5b7f95"),
    "RIVIAN_WAYPOINTS":    ("Rivian Waypoints",   "#5b7f95"),
    "FLO":                 ("FLO",                "#00c389"),
    "BP_PULSE":            ("bp pulse",           "#009e42"),
    "SHELL_RECHARGE":      ("Shell Recharge",     "#fbce07"),
    "EVCS":                ("EVCS",               "#2bb673"),
    "RED_E":               ("Red E",              "#d0021b"),
    "WALMART":             ("Walmart Charge",     "#0071ce"),
    "FCN":                 ("Francis Energy",     "#7b61ff"),
    "CHARGELAB":           ("ChargeLab",          "#333333"),
    "EVGATEWAY":           ("EV Gateway",         "#5b6cff"),
    "FPLEV":               ("FPL EVolution",      "#00a94f"),
    "Non-Networked":       ("Non-networked",      "#8892a0"),
}
def net_name(code):
    if not code or code == "Non-Networked":
        return "Non-networked", "#8892a0"
    if code in NETWORKS:
        return NETWORKS[code]
    return code.replace("_", " ").title(), "#8892a0"

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


def main():
    fs = fetch()
    print(f"  {len(fs)} stations returned", flush=True)
    out = distill(fs)
    json.dump(out, open(os.path.join(HERE, "chargers.json"), "w"), separators=(",", ":"))
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
