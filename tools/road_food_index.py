#!/usr/bin/env python3
"""The Road Food Index: every number on /road-food-index/, computed from the shipped data.

    python3 tools/road_food_index.py            # print the headline findings and table sizes
    python3 tools/road_food_index.py --csv DIR  # also write the CSVs into DIR

build.py renders the page and writes the CSVs from compute(); verify.py runs compute() again
and checks that the page and the CSVs say exactly what it says. Nothing here is typed in by
hand: change the data and every number moves with it.

Inputs, all committed: data.js (chargers and the chains within a walk of each), data/pois.json
(where each chain's locations are), data/highways.json (the interstates, as the /along/ pages
read them), highways.js (the same interstates in road order, as the app draws them) and
data/trips.json (the /trip/ drives, planned by planner.py exactly as their pages are).
"""
import csv
import datetime as dt
import io
import json
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from data_reader import load_data   # noqa: E402
import planner                      # noqa: E402

STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
          "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "Washington DC", "FL": "Florida",
          "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
          "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
          "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
          "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
          "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
          "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
          "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
          "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}

CATEGORY_KEYS = {"Ice cream shop"}   # a kind of place, not a chain: kept out of the chain tables
WALK = 80                            # metres a minute, as everywhere else
CLOSE_M = 200                        # "a two-minute walk or less": round(m / 80) <= 2
CHAIN_MIN_LOCATIONS = 50             # below this a chain's "share of locations" is noise
LOCATION_M = 250                     # one chain's map entries this close together are one location
STATE_MIN_SITES = 25                 # states ranked only with at least this many fast-charger sites
# The interstate corridor exactly as the /along/ pages draw it (build.py): 50 kW and up within
# 3 miles of the road, interstates with at least 12 such chargers.
CORRIDOR_MI = 3.0
INTERSTATE_MIN_KW = 50
INTERSTATE_MIN_FOUND = 12
JUMP_KM = 15                         # a highways.js step longer than this is a hole in the line
# The drives exactly as the /trip/ pages plan them.
TRIP_MI = 5.0
TRIP_MIN_KW = 50


def hav_m(a1, o1, a2, o2):
    R, p = 6371000, math.pi / 180
    x = math.sin((a2 - a1) * p / 2) ** 2 + math.cos(a1 * p) * math.cos(a2 * p) * math.sin((o2 - o1) * p / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def pct(n, d):
    return round(100 * n / d, 1) if d else 0.0


def slug(s):
    import re
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def thanksgiving(year):
    """The fourth Thursday of November."""
    d = dt.date(year, 11, 1)
    return d + dt.timedelta(days=(3 - d.weekday()) % 7 + 21)


def compute(root=ROOT, plans=None):
    """plans: {trip key: planner.Plan} when the caller has already planned the drives (build.py
    has); they are planned here otherwise, the same way."""
    D = load_data(os.path.join(root, "data.js"))
    sites = D["sites"]
    by_id = {s["id"]: s for s in sites}
    brands = D["brands"]
    raw = {int(k): v for k, v in D["matches"].items()}
    # walk distance in whole metres per (site, chain), as build.py derives it
    walk = {sid: {k: int(hav_m(by_id[sid]["lat"], by_id[sid]["lon"],
                               by_id[sid]["lat"] + v[0] / 1e4, by_id[sid]["lon"] + v[1] / 1e4))
                  for k, v in m.items()} for sid, m in raw.items() if sid in by_id}
    is_food = lambda k: brands.get(k, {}).get("cat") == "food"
    food_at = lambda sid: any(is_food(k) for k in walk.get(sid, {}))
    n_sites = len(sites)
    n_food = sum(1 for s in sites if food_at(s["id"]))
    n_any = sum(1 for s in sites if walk.get(s["id"]))
    n_food_close = sum(1 for s in sites if any(is_food(k) and d < CLOSE_M for k, d in walk.get(s["id"], {}).items()))

    # ---- chains: next to how many fast chargers, and how many of their own locations have one ----
    cell = 0.02
    grid = {}
    for s in sites:
        grid.setdefault((int(s["lat"] / cell), int(s["lon"] / cell)), []).append(s)
    pois = json.load(open(os.path.join(root, "data", "pois.json")))
    chains = []
    for k, b in brands.items():
        if k in CATEGORY_KEYS:
            continue
        at = [d[k] for d in walk.values() if k in d]
        if not at:
            continue
        # OpenStreetMap often maps one store several times (the shop, its fuel station, the EV
        # site, the building): Buc-ee's has 162 entries for about 50 stores. Entries of the same
        # chain within LOCATION_M of each other are one location; it has a charger within a walk
        # when any of its entries does.
        locs = []    # [lat, lon, ready]
        lgrid = {}
        lc = 0.01
        for p in pois.get(k, []):
            c0 = (int(p["lat"] / cell), int(p["lon"] / cell))
            ok = any(hav_m(p["lat"], p["lon"], s["lat"], s["lon"]) <= D["walkM"]
                     for di in (-1, 0, 1) for dj in (-1, 0, 1) for s in grid.get((c0[0] + di, c0[1] + dj), ()))
            l0 = (int(p["lat"] / lc), int(p["lon"] / lc))
            same = next((x for di in (-1, 0, 1) for dj in (-1, 0, 1) for x in lgrid.get((l0[0] + di, l0[1] + dj), ())
                         if hav_m(p["lat"], p["lon"], x[0], x[1]) <= LOCATION_M), None)
            if same:
                same[2] = same[2] or ok
            else:
                x = [p["lat"], p["lon"], ok]
                locs.append(x)
                lgrid.setdefault(l0, []).append(x)
        ready = sum(1 for x in locs if x[2])
        chains.append({
            "chain": k, "type": b["cat"], "emoji": b["e"], "slug": slug(k),
            "sites": len(at), "share": pct(len(at), n_sites),
            "close": sum(1 for d in at if d < CLOSE_M),
            "median_walk": max(1, round(statistics.median(at) / WALK)),
            "locations": len(locs), "ready": ready, "ready_share": pct(ready, len(locs)),
        })
    chains.sort(key=lambda c: (-c["sites"], c["chain"]))
    for i, c in enumerate(chains, 1):
        c["rank"] = i

    # ---- states ----
    states = []
    by_st = {}
    for s in sites:
        by_st.setdefault(s["st"], []).append(s)
    for st, ss in by_st.items():
        if st not in STATES:
            continue
        food = [s for s in ss if food_at(s["id"])]
        cnt = {}
        for s in ss:
            for k in walk.get(s["id"], {}):
                if is_food(k) and k not in CATEGORY_KEYS:
                    cnt[k] = cnt.get(k, 0) + 1
        top = sorted(cnt.items(), key=lambda x: (-x[1], x[0]))[:1]
        states.append({
            "st": st, "state": STATES[st], "sites": len(ss), "food": len(food), "food_share": pct(len(food), len(ss)),
            "big": sum(1 for s in ss if (s.get("kw") or 0) >= 150),
            "top_chain": top[0][0] if top else "", "top_chain_sites": top[0][1] if top else 0,
            "ranked": len(ss) >= STATE_MIN_SITES,
        })
    states.sort(key=lambda r: (not r["ranked"], -r["food_share"], -r["sites"], r["st"]))
    for i, r in enumerate([r for r in states if r["ranked"]], 1):
        r["rank"] = i

    # ---- interstates: the /along/ corridor, measured along the road as the app draws it ----
    highways = json.load(open(os.path.join(root, "data", "highways.json")))
    src = open(os.path.join(root, "highways.js")).read()
    drawn = json.loads(src[src.index("=") + 1: src.rindex(";")])
    roads = []
    maxm = CORRIDOR_MI * 1609.34
    hcell = 0.05
    reach = int(maxm / 111000 / hcell) + 1
    fast = [s for s in sites if (s.get("kw") or 0) >= INTERSTATE_MIN_KW]
    for ref, pts in highways.items():
        if len(pts) < 50:
            continue
        g = {}
        for i, (la, lo) in enumerate(pts):
            g.setdefault((round(la / hcell), round(lo / hcell)), []).append(i)
        found = []
        for s in fast:
            ci, cj = round(s["lat"] / hcell), round(s["lon"] / hcell)
            best = None
            for di in range(-reach, reach + 1):
                for dj in range(-reach, reach + 1):
                    for i in g.get((ci + di, cj + dj), ()):
                        d = hav_m(s["lat"], s["lon"], pts[i][0], pts[i][1])
                        if best is None or d < best:
                            best = d
            if best is not None and best <= maxm:
                found.append(s)
        if len(found) < INTERSTATE_MIN_FOUND:
            continue
        disp = ref.replace(" ", "-")
        path = drawn.get(disp)
        if not path:
            continue
        cum = [0.0]
        jump = False
        for i in range(1, len(path)):
            step = hav_m(path[i - 1][0], path[i - 1][1], path[i][0], path[i][1])
            jump = jump or step > JUMP_KM * 1000
            cum.append(cum[-1] + step)
        miles = cum[-1] / 1609.34
        food = [s for s in found if food_at(s["id"])]
        row = {"interstate": disp, "slug": slug(ref), "miles": round(miles), "chargers": len(found),
               "food": len(food), "food_share": pct(len(food), len(found)),
               "food_per_100": round(100 * len(food) / miles, 1) if miles else 0.0,
               "gap": None, "gap_from": None, "gap_to": None}
        if not jump:
            # Each charger at the mile of its nearest point on the drawn road; the gaps between
            # consecutive chargers, and from each end of the road to the first and last one.
            pg = {}
            for i, (la, lo) in enumerate(path):
                pg.setdefault((int(la / 0.1), int(lo / 0.1)), []).append(i)
            def nearest(s):
                c0 = (int(s["lat"] / 0.1), int(s["lon"] / 0.1))
                cand = [i for di in (-1, 0, 1) for dj in (-1, 0, 1) for i in pg.get((c0[0] + di, c0[1] + dj), ())]
                return min(cand or range(len(path)), key=lambda i: (hav_m(s["lat"], s["lon"], path[i][0], path[i][1]), i))
            at = sorted(cum[nearest(s)] / 1609.34 for s in found)
            prev, best = 0.0, (0.0, 0.0, 0.0)
            for m in at + [miles]:
                if m - prev > best[0]:
                    best = (m - prev, prev, m)
                prev = m
            row["gap"], row["gap_from"], row["gap_to"] = round(best[0]), round(best[1]), round(best[2])
        roads.append(row)
    roads.sort(key=lambda r: (-r["food_share"], -r["chargers"], r["interstate"]))
    for i, r in enumerate(roads, 1):
        r["rank"] = i

    # ---- the drives: the longest stretch with no DC fast charger, as each /trip/ page says ----
    trips = json.load(open(os.path.join(root, "data", "trips.json")))
    day = dt.date.fromisoformat(D["generated"])
    drives = []
    for tk, t in trips.items():
        plan = (plans or {}).get(tk) or planner.Plan(sites, raw, brands, t["pts"], t["mi"], t["hr"], day, 8 * 60, TRIP_MI)
        if sum(1 for sid in plan.order if (by_id[sid].get("kw") or 0) >= TRIP_MIN_KW) < 10:
            continue   # build.py makes no page for it
        g = plan.longest()
        def place_at(mi):
            for s in plan.vis:
                if plan.mile_at[s["id"]] == mi:
                    return f"{s['city']}, {s['st']}"
            return ""
        A, B = t["a"].split(",")[0], t["b"].split(",")[0]
        rows = plan.rows()
        lunch = next((r for r in rows if r["kind"] == "stop" and r["label"] == "Lunch"), None)
        drives.append({
            "slug": f"{slug(A)}-to-{slug(B)}", "from": t["a"], "to": t["b"], "a": A, "b": B,
            "miles": round(t["mi"]), "hours": round(t["hr"], 2),
            "chargers": len(plan.order), "gap": g["len"], "gap_from": g["from"], "gap_to": g["to"],
            "gap_end": g["end"],
            "gap_from_place": t["a"] if g["from"] == 0 else place_at(g["from"]),
            "gap_to_place": t["b"] if g["to"] == g["end"] else place_at(g["to"]),
            "lunch_place": f"{lunch['s']['city']}, {lunch['s']['st']}" if lunch else "",
            "lunch_clock": lunch["clock"] if lunch else "",
            "lunch_chain": lunch["k"] or "" if lunch else "",
            "lunch_walk": lunch["walk"] if lunch and lunch["k"] else None,
        })
    drives.sort(key=lambda r: (-r["gap"], r["slug"]))

    return {"generated": D["generated"], "n_sites": n_sites, "n_food": n_food, "n_any": n_any,
            "n_food_close": n_food_close, "n_chains": len(chains),
            "thanksgiving": thanksgiving(day.year).isoformat(),
            "chains": chains, "states": states, "interstates": roads, "drives": drives}


# ---------------------------------------------------------------- findings and tables
def unique_pairs(drives):
    """A drive and its way back share their longest gap; the table names the pair once."""
    seen, out = set(), []
    for r in drives:
        key = frozenset((r["from"], r["to"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def ready_ranked(r):
    return sorted((c for c in r["chains"] if c["locations"] >= CHAIN_MIN_LOCATIONS),
                  key=lambda c: (-c["ready_share"], -c["ready"], c["chain"]))


def headlines(r):
    """The findings the page leads with, as plain sentences. Each one is chosen by the data
    (whoever is first or last), so it stays true whatever the next refresh brings."""
    food = [c for c in r["chains"] if c["type"] == "food"]
    top, second = food[0], food[1]
    ready = ready_ranked(r)
    ready_food = [c for c in ready if c["type"] == "food"]
    roads = r["interstates"]
    best, worst = roads[0], roads[-1]
    gap = r["drives"][0]
    out = [
        f"{pct(r['n_food'], r['n_sites'])}% of US DC fast-charger sites ({r['n_food']:,} of {r['n_sites']:,}) "
        f"have somewhere to eat within a 10-minute walk.",
        f"{top['chain']} is within a 10-minute walk of more fast chargers than any other restaurant chain: "
        f"{top['sites']:,} sites, {top['share']}% of all of them, "
        f"{'just ' if second['sites'] >= top['sites'] * 0.95 else ''}ahead of {second['chain']} ({second['sites']:,}).",
    ]
    if ready_food:
        f0 = ready_food[0]
        line = (f"Of the restaurant chains, {f0['chain']} has a fast charger within a walk of the most of its "
                f"locations: {f0['ready_share']}% of {f0['locations']:,}.")
        if ready[0] is not f0:
            line += (f" Among all chains it is {ready[0]['chain']}, at {ready[0]['ready_share']}% of "
                     f"{ready[0]['locations']:,}.")
        out.append(line)
    out.append(f"{best['interstate']} is the best interstate for food at a fast charger: {best['food_share']}% of "
               f"its chargers have somewhere to eat within a walk. {worst['interstate']} is the worst, at "
               f"{worst['food_share']}%.")
    out.append(f"On the {len(r['drives'])} drives we plan, the longest stretch with no DC fast charger within "
               f"{TRIP_MI:g} miles of the road is {gap['gap']} miles, between {gap['gap_from_place']} and "
               f"{gap['gap_to_place']} ({gap['a']} to {gap['b']}).")
    return out


TABLES = {
    "chains": (["rank", "chain", "type", "fast_charger_sites_within_walk", "share_of_all_sites_pct",
                "sites_within_2_min_walk", "median_walk_min", "chain_locations_osm",
                "locations_with_fast_charger_within_walk", "share_of_locations_pct"],
               lambda r: [[c["rank"], c["chain"], c["type"], c["sites"], c["share"], c["close"], c["median_walk"],
                           c["locations"], c["ready"], c["ready_share"]] for c in r["chains"]]),
    "interstates": (["rank", "interstate", "miles_mapped", "fast_chargers_within_3_mi", "with_food_within_walk",
                     "with_food_pct", "food_stops_per_100_mi", "longest_gap_mi", "gap_from_mile", "gap_to_mile"],
                    lambda r: [[x["rank"], x["interstate"], x["miles"], x["chargers"], x["food"], x["food_share"],
                                x["food_per_100"], "" if x["gap"] is None else x["gap"],
                                "" if x["gap"] is None else x["gap_from"], "" if x["gap"] is None else x["gap_to"]]
                               for x in r["interstates"]]),
    "states": (["rank", "state", "fast_charger_sites", "with_food_within_walk", "with_food_pct",
                "sites_150_kw_plus", "most_common_chain", "most_common_chain_sites"],
               lambda r: [[s.get("rank", ""), s["state"], s["sites"], s["food"], s["food_share"], s["big"],
                           s["top_chain"], s["top_chain_sites"]] for s in r["states"]]),
    "drives": (["from", "to", "miles", "fast_chargers_within_5_mi", "longest_gap_mi", "gap_from_mile",
                "gap_to_mile", "gap_from_place", "gap_to_place"],
               lambda r: [[d["from"], d["to"], d["miles"], d["chargers"], d["gap"], d["gap_from"], d["gap_to"],
                           d["gap_from_place"], d["gap_to_place"]] for d in r["drives"]]),
}


def csv_text(r, name):
    head, rows = TABLES[name]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(head)
    w.writerows(rows(r))
    return buf.getvalue()


def write_csvs(r, outdir):
    os.makedirs(outdir, exist_ok=True)
    for name in TABLES:
        with open(os.path.join(outdir, f"{name}.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(csv_text(r, name))


if __name__ == "__main__":
    import time
    t0 = time.time()
    res = compute()
    for h in headlines(res):
        print("-", h)
    print(f"{len(res['chains'])} chains, {len(res['interstates'])} interstates, {len(res['states'])} states, "
          f"{len(res['drives'])} drives ({time.time() - t0:.1f} s)")
    if "--csv" in sys.argv:
        write_csvs(res, sys.argv[sys.argv.index("--csv") + 1])
