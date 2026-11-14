"""The app's drive plan, in Python, for the /trip/ pages.

A /trip/ page says "leave Los Angeles at 8:00 am, 10:05 am break in Barstow, 12:30 pm lunch in
Primm, arrive ~1:55 pm". The app opened on the same drive with ?leave=0800 must say the same, so
this is a line-by-line port of index.html's route code, not a second opinion:

    applyCorridor()   -> corridor()      which stops are on the route, and at what mile
    visibleSites()    -> visible()       in driving order (sortByKey, ties as the app breaks them)
    breakPicks()      -> break_picks()   meals near their local hour, breaks in long stretches
    breaksCard()      -> plan()          clocks, the arrival, the charger-gap row
    chargerGap(), tzOf(), localAt(), clockLabel(), walkMin(), chargeMin()

The lists and numbers the plan is made of (meal hours, what is not a meal, no-breakfast chains,
late chains, minutes at a stop, the break cadence, state time zones) are READ from index.html, so
they cannot drift apart. The logic is ported; tools/trip_plan_check.mjs runs the real app on the
trips' own geometry and compares every row, and check.sh runs it on a sample.

Arithmetic follows the JavaScript order of operations so the floats come out identical, and
Math.round is floor(x + .5), not Python's round-half-even.
"""
import math
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()


def _js(pattern, what):
    m = re.search(pattern, _SRC, re.S)
    if not m:
        raise SystemExit(f"planner.py: could not read {what} from index.html")
    return m.group(1)


def _strs(body):
    return [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", body)]


MI = float(_js(r"const WALK_MPM = \d+, MI = ([\d.]+);", "MI"))
WALK_MPM = int(_js(r"const WALK_MPM = (\d+), MI", "WALK_MPM"))
BREAK_MIN = int(_js(r"const BREAK_MIN = (\d+);", "BREAK_MIN"))
DWELL_BREAK = int(_js(r"const DWELL_BREAK = (\d+), DWELL_MEAL = \d+;", "DWELL_BREAK"))
DWELL_MEAL = int(_js(r"const DWELL_BREAK = \d+, DWELL_MEAL = (\d+);", "DWELL_MEAL"))
MEALS = [(n, eval(e, {"__builtins__": {}}))           # "12 * 60 + 30": digits and operators only
         for n, e in re.findall(r"\{ name: '(\w+)', at: ([\d *+]+) \}",
                                _js(r"const MEALS = \[(.*?)\];", "MEALS"))]
NOT_A_MEAL = set(_strs(_js(r"const NOT_A_MEAL = new Set\(\[(.*?)\]\);", "NOT_A_MEAL")))
NO_BREAKFAST = set(_strs(_js(r"const NO_BREAKFAST = new Set\(\[(.*?)\]\);", "NO_BREAKFAST")))
LATE = set(_strs(_js(r"const LATE = new Set\(\[(.*?)\]\);", "LATE")))
ST_TZ = dict(re.findall(r"(\w\w): '([\w/]+)'", _js(r"const ST_TZ = \{(.*?)\};", "ST_TZ")))
if len(MEALS) != 3 or not NOT_A_MEAL or not NO_BREAKFAST or not LATE or len(ST_TZ) < 30:
    raise SystemExit("planner.py: index.html's plan constants changed shape")

# The stop signals the guide cards can show without a clock (UI-55), read like the rest.
TRAVEL_STOPS = set(_strs(_js(r"const TRAVEL_STOPS = new Set\(\[(.*?)\]\);", "TRAVEL_STOPS")))
RR_24 = set(_strs(_js(r"const RR_24 = new Set\(\[(.*?)\]\);", "RR_24")))
SIG_ICON = dict(re.findall(r"^  (wc|kids): '(<svg[^']*</svg>)',?$", _js(r"const SIG_ICON = \{(.*?)\n\};", "SIG_ICON"), re.M))
if not TRAVEL_STOPS or not RR_24 or set(SIG_ICON) != {"wc", "kids"}:
    raise SystemExit("planner.py: index.html's stop-signal constants changed shape")

DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def jsround(x):
    return math.floor(x + 0.5)


def hav(a1, o1, a2, o2):
    R, p = 6371000, math.pi / 180
    dA, dO = (a2 - a1) * p, (o2 - o1) * p
    x = math.sin(dA / 2) ** 2 + math.cos(a1 * p) * math.cos(a2 * p) * math.sin(dO / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def walk_min(m):
    return max(1, jsround(m / WALK_MPM))


def m_dist(s, v):
    """mDist(): a match is [dLat, dLon] x 1e4 from the charger (or plain metres)."""
    if isinstance(v, (int, float)):
        return v
    return hav(s["lat"], s["lon"], s["lat"] + v[0] / 1e4, s["lon"] + v[1] / 1e4)


def tz_of(s):
    st, lat, lon = s["st"], s["lat"], s["lon"]
    if st == "HI": return "Pacific/Honolulu"
    if st == "TN" and lon > -85.6: return "America/New_York"
    if st == "IN" and ((lat > 41 and lon < -86.5) or (lat < 38.6 and lon < -86.7)): return "America/Chicago"
    if st == "KY" and lon < -86.2: return "America/Chicago"
    if st == "FL" and lon < -85.1: return "America/Chicago"
    if st == "TX" and lon < -104.9: return "America/Denver"
    if st == "ID" and lat > 45.6: return "America/Los_Angeles"
    if (st == "ND" and lon < -101.2) or (st == "SD" and lon < -100.6) or (st == "NE" and lon < -101.4): return "America/Denver"
    if (st == "OR" and lon > -117.2) or (st == "NV" and lon > -114.1) or (st == "KS" and lon < -101.4): return "America/Denver"
    return "America/" + ST_TZ.get(st, "New_York")


_ZONES = {}


def local_at(ms, tz):
    """localAt(): minutes after local midnight, the local date, its day number, the weekday.
    new Date(ms) drops the fraction of a millisecond; Intl drops the seconds."""
    z = _ZONES.get(tz) or _ZONES.setdefault(tz, ZoneInfo(tz))
    d = datetime.fromtimestamp(int(ms) // 1000, z)
    return {"min": d.hour * 60 + d.minute, "day": f"{d.year}-{d.month}-{d.day}",
            "dn": (d.date() - datetime(1970, 1, 1).date()).days, "wd": (d.weekday() + 1) % 7}


def clock_label(mins):
    m = ((jsround(mins / 5) * 5) % 1440 + 1440) % 1440
    h = m // 60
    return f"{(h % 12) or 12}:{m % 60:02d} {'am' if h < 12 else 'pm'}"


def hm_label(mins):
    t = jsround(mins)
    r = t % 60
    if t < 60:
        return f"{t} min"
    return f"{t // 60}h" + (f" {r:02d}m" if r else "")


# ---------------------------------------------------------------------- the route
def corridor(verts, mi, sites, corridor_mi=5):
    """applyCorridor(): the stops within corridor_mi of the line, each with the index of its
    nearest point (ties to the earliest) and its mile from the start, scaled to the road
    distance. Same cells, same reach, same every-third-point on long lines."""
    max_m = corridor_mi * MI
    rad = math.pi / 180
    s0 = math.sin(max_m / 2 / 6371000)
    d_lat = max_m / 6371000 / rad
    ri = math.ceil(d_lat / .05) + 1

    def rj_at(lat):
        # cells east-west within max_m of a point at this latitude: wider toward the pole
        sj = s0 / math.sqrt(math.cos(min(89.9, abs(lat)) * rad) * math.cos(min(89.9, abs(lat) + d_lat) * rad))
        return 3600 if sj >= 1 else math.ceil(2 * math.asin(sj) / rad / .05) + 1

    cells, seen = set(), set()
    for v in verts:
        c = (jsround(v[0] / .05), jsround(v[1] / .05))
        if c in seen: continue
        seen.add(c)
        rj = rj_at(abs(c[0] * .05) + .025)
        for di in range(-ri, ri + 1):
            for dj in range(-rj, rj + 1):
                cells.add((c[0] + di, c[1] + dj))
    step = 3 if len(verts) > 3000 else 1
    bucket = {}
    for i in range(0, len(verts), step):
        bucket.setdefault((jsround(verts[i][0] / .05), jsround(verts[i][1] / .05)), []).append(i)
    order = {}
    for s in sites:
        ci, cj = jsround(s["lat"] / .05), jsround(s["lon"] / .05)
        if (ci, cj) not in cells: continue
        rj = rj_at(s["lat"])
        best, bi = 9e9, 0
        for di in range(-ri, ri + 1):
            for dj in range(-rj, rj + 1):
                for i in bucket.get((ci + di, cj + dj), ()):
                    d = hav(s["lat"], s["lon"], verts[i][0], verts[i][1])
                    if d < best or (d == best and i < bi):
                        best, bi = d, i
        if best <= max_m:
            order[s["id"]] = bi
    cum = [0.0] * len(verts)
    for i in range(1, len(verts)):
        cum[i] = cum[i - 1] + hav(verts[i - 1][0], verts[i - 1][1], verts[i][0], verts[i][1])
    k = mi / (cum[-1] / MI) if cum[-1] > 0 else 1
    mile_at = {sid: jsround(cum[bi] / MI * k) for sid, bi in order.items()}
    return order, mile_at


LIST_MAX = 300


def sort_by_key(arr, key):
    """sortByKey(): stable by key, but past 600 items only the first 300 are sorted and the
    rest keep their order -- the order the plan meets the stops in, for its tie-breaks."""
    n = len(arr)
    k = [key(a) for a in arr]
    if n <= LIST_MAX * 2:
        head = sorted(range(n), key=lambda i: (k[i], i))
    else:
        cut = sorted(k)[LIST_MAX - 1]
        head, tail = [], []
        for i in range(n):
            (head if k[i] < cut else tail).append(i)
        j = 0
        while j < len(tail) and len(head) < LIST_MAX:
            if k[tail[j]] == cut:
                head.append(tail[j]); tail[j] = -1
            j += 1
        head.sort(key=lambda i: (k[i], i))
        head += [i for i in tail if i >= 0]
    return [arr[i] for i in head]


def visible(sites, order):
    """visibleSites() on a route with no filters: every stop on it, in driving order."""
    return sort_by_key([s for s in sites if s["id"] in order], lambda s: order[s["id"]])


# ---------------------------------------------------------------------- the plan
class Plan:
    def __init__(self, sites, matches, brands, verts, mi, hr, day, leave=480, corridor_mi=5):
        """sites in data.js order; matches as in data.js ([dLat, dLon] per chain); the route's
        points, miles and hours as the app gets them from OSRM; `day` the date the drive
        starts (a datetime.date); leaving at `leave` minutes after midnight where it starts."""
        self.matches, self.brands, self.mi, self.hr = matches, brands, mi, hr
        self.by_id = {s["id"]: s for s in sites}
        self.order, self.mile_at = corridor(verts, mi, sites, corridor_mi)
        self.vis = visible(sites, self.order)
        self.corridor_mi = corridor_mi
        self.first, self.last = self._ends()
        self.t0 = None
        if self.first:
            z = ZoneInfo(tz_of(self.first))
            start = datetime(day.year, day.month, day.day, tzinfo=z) + timedelta(minutes=leave)
            self.t0 = start.timestamp() * 1000
        self.picks = self._picks() if self._has_card() else []

    def _has_card(self):
        return self.mi >= 60 and self.first is not None

    def _ends(self):
        a = b = None
        for s in self.vis:
            m = self.mile_at[s["id"]]
            if a is None or m < self.mile_at[a["id"]]: a = s
            if b is None or m > self.mile_at[b["id"]]: b = s
        return a, b

    def _nearest(self, s, keys, m):
        """nearestOf(): the nearest on the charger's side of the highway first (s["xh"])."""
        k0, w0, x0 = None, 9e9, True
        xh = s.get("xh") or ()
        for k in keys:
            d, x = m_dist(s, m[k]), k in xh
            if (x0 and not x) or (x == x0 and d < w0): w0, k0, x0 = d, k, x
        return k0, w0

    @staticmethod
    def _far(s, k, w):
        """farWalk(): not a short walk -- over ~5 minutes, or across a highway."""
        return w > 400 or (k is not None and k in (s.get("xh") or ()))

    def _food(self, m):
        return [k for k in m if k in self.brands and self.brands[k].get("cat") == "food"]

    def _meal_keys(self, m, meal):
        return [k for k in self._food(m) if k not in NOT_A_MEAL and not (meal == "Breakfast" and k in NO_BREAKFAST)]

    def _picks(self):
        mi_of, hr, route_mi = self.mile_at, self.hr, self.mi
        first, last_stop = self.first, self.last
        per_min = hr * 60 / max(1, route_mi)
        drive, t0 = hr * 60, self.t0
        cands = [s for s in self.vis if s.get("lvl") != 2]
        start, had = local_at(t0, tz_of(first)), set()
        for name, at in MEALS:
            if start["min"] > at - 60: had.add(start["day"] + name)
        picks, last, extra = [], 0, 0
        for _ in range(400):
            best = {}
            end = local_at(t0 + (drive + extra) * 60000, tz_of(last_stop))
            for s in cands:
                mi = mi_of[s["id"]]
                into = mi * per_min
                if mi <= last or into < 60 or into > drive - 30: continue
                if picks and (mi - picks[-1]["mi"]) * per_min < 60: continue
                ms = t0 + (into + extra) * 60000
                at = local_at(ms, tz_of(s))
                for name, meal_at in MEALS:
                    off = abs(at["min"] - meal_at)
                    if (off > 120 or at["min"] < meal_at - 45 or (at["day"] + name) in had
                            or (end["day"] == at["day"] and end["min"] <= meal_at + 15)):
                        continue
                    m = self.matches.get(s["id"]) or {}
                    k, w = self._nearest(s, self._meal_keys(m, name), m)
                    if not k: continue
                    kw = s.get("kw") or 0
                    sc = [2 if off > 75 else 1 if off > 45 else 0, 1 if self._far(s, k, w) else 0, 1 if kw < 100 else 0,
                          -math.floor(min(kw, 350) / 50), jsround(off / 15), w]
                    key = at["day"] + name
                    cur = best.get(key)
                    if not cur or sc < cur["sc"]:
                        best[key] = {"s": s, "walk": w, "k": k, "meal": name, "sc": sc, "key": key, "mi": mi, "ms": ms}
            nxt = None
            for p in best.values():
                if not nxt or p["mi"] < nxt["mi"]: nxt = p
            to = nxt["mi"] if nxt else route_mi
            gap = to - last
            n = math.ceil(gap * per_min / BREAK_MIN) - 1
            if n < 1:
                if not nxt: break
                had.add(nxt["key"]); picks.append(nxt); last = nxt["mi"]; extra += DWELL_MEAL
                continue
            target = last + gap / (n + 1)
            span = max(12, gap / (n + 1) * 0.35)
            pick = pick_sc = None
            for s in cands:
                mi = mi_of[s["id"]]
                if (mi - last) * per_min < BREAK_MIN * 0.6 or (to - mi) * per_min < (60 if nxt else 30): continue
                m = self.matches.get(s["id"]) or {}
                keys = self._food(m)
                k, w = self._nearest(s, keys, m)
                shut = 0
                if not k: continue
                ms = t0 + (mi * per_min + extra) * 60000
                hm = local_at(ms, tz_of(s))["min"]
                if hm >= 22 * 60 or hm < 6 * 60:
                    lk, lw = self._nearest(s, [x for x in keys if x in LATE], m)
                    if lk: k, w = lk, lw
                    else: shut = 1 if s.get("h24") else 2
                off = abs(mi - target) if abs(mi - target) > span else 0
                sc = [off, shut, -min(s.get("kw") or 0, 350), 1 if self._far(s, k, w) else 0,
                      -min(s.get("stalls") or 0, 40), 0 if s.get("h24") else 1, w]
                if not pick or sc < pick_sc:
                    pick, pick_sc = {"s": s, "walk": w, "k": k, "meal": None, "mi": mi, "ms": ms}, sc
            if pick:
                picks.append(pick); last = pick["mi"]; extra += DWELL_BREAK
            elif nxt:
                had.add(nxt["key"]); picks.append(nxt); last = nxt["mi"]; extra += DWELL_MEAL
            else:
                break
        return picks

    def gap(self):
        """chargerGap(): the longest stretch with no fast charger within the corridor, or None
        under 60 miles. `longest()` is the same without the cut-off."""
        g = self.longest()
        return None if g["len"] < 60 else g

    def longest(self):
        ms = sorted(m for sid, m in self.mile_at.items() if self.by_id[sid].get("lvl") != 2)
        end = jsround(self.mi)
        prev, g = 0, {"len": 0, "from": 0, "to": 0, "end": end}
        for m in ms + [end]:
            if m - prev > g["len"]: g = {"len": m - prev, "from": prev, "to": m, "end": end}
            prev = m
        return g

    def rows(self):
        """breaksCard()'s rows in order: each stop, and the gap row at its mile. Clocks are
        local to the stop; `day` counts from the day you leave (0 = that day)."""
        if not self._has_card(): return []
        per_mi = self.hr / max(1, self.mi)
        home = local_at(self.t0, tz_of(self.first))["dn"]
        out = []
        for p in self.picks:
            l = local_at(p["ms"], tz_of(p["s"]))
            out.append({"kind": "stop", "mi": p["mi"], "clock": clock_label(l["min"]), "day": l["dn"] - home,
                        "wd": l["wd"], "label": p["meal"] or "Break", "s": p["s"], "k": p["k"],
                        "walk": walk_min(p["walk"]) if p["k"] else None})
        g = self.gap()
        if g:
            extra = sum(DWELL_MEAL if p["meal"] else DWELL_BREAK for p in self.picks if p["mi"] <= g["from"])
            at = self.first
            for s in self.vis:
                m = self.mile_at[s["id"]]
                if m <= g["from"] and m > self.mile_at[at["id"]]: at = s
            l = local_at(self.t0 + (g["from"] * per_mi * 60 + extra) * 60000, tz_of(at))
            out.append({"kind": "gap", "mi": g["from"] + 0.5, "clock": clock_label(l["min"]), "day": l["dn"] - home,
                        "wd": l["wd"], "gap": g})
            out.sort(key=lambda r: r["mi"])     # stable, as Array.prototype.sort
        return out

    def leave_label(self):
        return clock_label(local_at(self.t0, tz_of(self.first))["min"])

    def arrive(self):
        """(clock, days after the day you leave) in the time of the last stop on the drive."""
        ms = self.t0 + self.hr * 3600000 + sum(DWELL_MEAL if p["meal"] else DWELL_BREAK for p in self.picks) * 60000
        home = local_at(self.t0, tz_of(self.first))["dn"]
        l = local_at(ms, tz_of(self.last))
        return clock_label(l["min"]), l["dn"] - home


def charge_min(s, car):
    """chargeMin(): the app's rough 10-80% minutes for a car [battery kWh, peak kW, plug bit]."""
    bat, cmax, bit = car
    kw = s.get("kw") or 0
    if s.get("conn", 0) & bit and s.get("pk"):
        kw = s["pk"][0 if bit == 1 else 1 if bit == 2 else 2] or s.get("kw") or 0
    eff = min(cmax, kw or cmax)
    if not eff: return None
    return jsround((0.7 * bat) / (0.55 * eff) * 60)


# ---------------------------------------------------------------------- stop signals
def quiet_sig(s, m):
    """The one signal a guide card shows, as the app's rows do (rowSigs), for what holds at any
    hour: a restroom likely (restroomSig's reasons that need no clock -- a rest area, a travel
    stop a short walk away, mapped public toilets, a 24-hour diner next door), else a playground
    (kidsSig). The store and mall reasons depend on the hour, so a page that has no hour leaves
    them out. m is the stop's raw matches. Returns (kind, tag, why) or None."""
    if s.get("lvl") == 2:
        return None
    xh = set(s.get("xh") or ())
    def near(keys, lim):
        best = None
        for k, v in m.items():
            if k in keys and k not in xh:
                d = m_dist(s, v)
                if d <= lim and (best is None or d < best[1]):
                    best = (k, d)
        return best
    def next_door(k, d):
        return f"{k} next door" if d <= 150 else f"{k}, a {walk_min(d)}-min walk"
    def wc(short, why):
        return ("wc", "restroom likely", short[0].upper() + short[1:] + ". " + why + " Likely, not certain.")
    if s.get("ra"):
        return wc("the charger is at a highway rest area or service plaza", "Those have restrooms.")
    t = near(TRAVEL_STOPS, 250)
    if t:
        return wc(next_door(*t), "Travel stops like it have public restrooms and are usually open 24 hours.")
    if s.get("wc"):
        return wc(f"public toilets mapped {s['wc'] * 10} m away", "From OpenStreetMap.")
    t = near(RR_24, 150)
    if t:
        return wc(next_door(*t), "It is usually open 24 hours, with restrooms for customers.")
    if s.get("pg"):
        return ("kids", f"playground {walk_min(s['pg'] * 10)} min",
                f"A playground is mapped in OpenStreetMap about {s['pg'] * 10} m away in a straight line, on this side of any highway.")
    return None
