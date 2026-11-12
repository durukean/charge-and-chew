#!/usr/bin/env python3
"""Fetch what is around each fast charger besides the chains, from OpenStreetMap (Overpass).

Output: data/amenities.json, a committed cache like pois.json and highways.json. build_data.py
reads it and folds a few per-charger numbers into data.js (never these raw points):

  toilets     amenity=toilets, not access=private/no            -> "restroom likely"
  playground  leisure=playground, not access=private/no         -> "good for kids"
  mall        shop=mall (bounding box)                          -> "restroom likely"
  rest        highway=rest_area / services (bounding box)       -> "restroom likely"
  hwy         motorways, and divided (oneway) trunk roads, not on a bridge or in a tunnel
                                                                -> "across the highway"

Only what lies near a charger is kept: the cache covers the 0.02-degree cells (~2 km) within a
kilometre of a charger ("cells"), and everything is clipped to them. Highway lines are stored
delta-encoded ("hwyz") and the cells run-length encoded ("cellz"); load() and save() convert.

The full fill comes from an OpenStreetMap extract: data/amenities_from_pbf.py (osmium). This
script is the weekly gap-fill: it asks Overpass only for the cells a new charger needs, a few per
week. (It can also fill a missing kind for every cell, a tile at a time, but that is hours of
Overpass time; use the extract.)

Overpass is a shared free service: one request at a time, a named User-Agent, a pause between
requests, and exponential backoff on 429/502/503/504 or a timeout.
"""
import json, math, os, sys, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OVERPASS = "https://overpass-api.de/api/interpreter"
UA = "chargeandchew-data/1.0 (+https://chargeandchew.com; weekly data refresh)"
CELL = 0.02          # degrees; the cells within REACH_M of a charger are covered
REACH_M = 1000
TILE = 2.0           # degrees, for a full fetch of one kind (split further when Overpass will not answer)
BATCH = 30           # cells per gap-fill request
GROUP_TILES, GROUP_CELLS = 8, 300   # small tiles fetched together in one request
PAUSE = 5            # seconds between requests
CACHE = os.path.join(HERE, "amenities.json")
VERSION = 3          # 2: highway lines delta-encoded; 3: chained, points and cells encoded too

NOT_PRIVATE = '["access"!~"^(private|no)$"]'
SAME_LEVEL = '["bridge"!~"^(yes|viaduct|cantilever|covered)$"]["tunnel"!~"^(yes|building_passage|culvert)$"]'
# kind -> (Overpass selectors, output mode)
KINDS = {
    "toilets":    (['nwr["amenity"="toilets"]' + NOT_PRIVATE], "center"),
    "playground": (['nwr["leisure"="playground"]' + NOT_PRIVATE], "center"),
    "mall":       (['nwr["shop"="mall"]'], "bb"),
    "rest":       (['nwr["highway"~"^(rest_area|services)$"]'], "bb"),
    "hwy":        (['way["highway"="motorway"]' + SAME_LEVEL,
                    'way["highway"="trunk"]["oneway"="yes"]' + SAME_LEVEL], "geom"),
}


def cell_of(lat, lon):
    return (math.floor(lat / CELL), math.floor(lon / CELL))


def needed_cells(chargers):
    """The cells within ~1 km of a charger: walks are 800 m at most, so nothing further out
    can matter. (All eight neighbours tripled the cache for nothing.)"""
    out = set()
    for s in chargers:
        dl = REACH_M / 110540.0
        do = REACH_M / (111320.0 * max(0.2, math.cos(math.radians(s["lat"]))))
        for a in (-dl, 0, dl):
            for b in (-do, 0, do):
                out.add(cell_of(s["lat"] + a, s["lon"] + b))
    return out


def ckey(c):
    return "%d,%d" % c


def query(body, tries=7):
    """POST one query; back off and retry when Overpass is busy. None after the last try."""
    # A modest timeout and memory claim: Overpass schedules queries by what they declare, and a
    # 1 GB / 600 s claim waited behind everyone else and came back 504 again and again.
    q = "[out:json][timeout:240][maxsize:268435456];" + body
    wait = 30
    for attempt in range(tries):
        try:
            req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.load(r)
            if "remark" in d and "error" in str(d.get("remark", "")).lower():
                raise RuntimeError("Overpass remark: " + str(d["remark"])[:200])
            return d
        except (urllib.error.URLError, OSError, RuntimeError, ValueError) as e:
            code = getattr(e, "code", None)
            ra = e.headers.get("Retry-After") if getattr(e, "headers", None) else None
            pause = max(wait, int(ra)) if ra and str(ra).isdigit() else wait
            print("    attempt %d failed (%s); retrying in %ds" % (attempt + 1, code or e, pause), flush=True)
            time.sleep(pause)
            wait = min(wait * 2, 900)
    return None


def block(kinds, bbox):
    """One request body for these kinds in one box. Each kind's output is preceded by a made-up
    marker element, so the answer can be split without asking for every tag."""
    parts = []
    for k in kinds:
        sels, mode = KINDS[k]
        out = {"center": "out ids center qt;", "bb": "out ids bb qt;", "geom": "out skel geom qt;"}[mode]
        parts.append('make sep kind="%s";out;(%s);%s' % (k, "".join(s + "(%s);" % bbox for s in sels), out))
    return "".join(parts)


def split(elements):
    """Marker-separated answer -> {kind: [element, ...]}"""
    out, cur = {}, None
    for e in elements:
        if e.get("type") == "sep":
            cur = e["tags"]["kind"]; out.setdefault(cur, []); continue
        if cur:
            out[cur].append(e)
    return out


def r5(x):
    return round(x, 5)


def to_items(kind, els):
    mode = KINDS[kind][1]
    items = []
    for e in els:
        if mode == "center":
            la = e.get("lat", (e.get("center") or {}).get("lat"))
            lo = e.get("lon", (e.get("center") or {}).get("lon"))
            if la is not None:
                items.append([r5(la), r5(lo)])
        elif mode == "bb":
            b = e.get("bounds")
            if b:
                items.append([r5(b["minlat"]), r5(b["minlon"]), r5(b["maxlat"]), r5(b["maxlon"])])
            elif "lat" in e:
                items.append([r5(e["lat"]), r5(e["lon"]), r5(e["lat"]), r5(e["lon"])])
        else:
            g = [[r5(p["lat"]), r5(p["lon"])] for p in (e.get("geometry") or []) if p]
            if len(g) >= 2:
                items.append(g)
    return items


def simplify(line, tol_m=4.0):
    """Douglas-Peucker in local metres: drops the points a straight-line test cannot tell apart."""
    if len(line) < 3:
        return line
    k = math.cos(math.radians(line[0][0])) * 111320.0
    xy = [(p[1] * k, p[0] * 110540.0) for p in line]
    keep = [False] * len(line); keep[0] = keep[-1] = True
    stack = [(0, len(line) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = xy[a]; bx, by = xy[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1e-9
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            d = abs((xy[i][0] - ax) * dy - (xy[i][1] - ay) * dx) / L
            if d > best:
                best, bi = d, i
        if best > tol_m:
            keep[bi] = True
            stack.append((a, bi)); stack.append((bi, b))
    return [p for p, f in zip(line, keep) if f]


def seg_touches(a, b, cells):
    n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1])) / (CELL / 4)) + 1
    return any(cell_of(a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n) in cells for t in range(n + 1))


def clip(kind, items, cells):
    """Keep only what touches a covered cell. Lines are cut into runs of points in covered cells,
    plus one point either side, so a segment that crosses into the area survives whole."""
    if kind in ("toilets", "playground"):
        return [p for p in items if cell_of(p[0], p[1]) in cells]
    if kind in ("mall", "rest"):
        return [b for b in items if cell_of((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) in cells
                or cell_of(b[0], b[1]) in cells or cell_of(b[2], b[3]) in cells]
    out = []
    for g in items:
        # A point counts as inside when it, or the segment after it, touches a covered cell: a
        # straight motorway can run kilometres between two nodes, both outside the cells.
        inside = [cell_of(p[0], p[1]) in cells or (i + 1 < len(g) and seg_touches(p, g[i + 1], cells))
                  for i, p in enumerate(g)]
        run = []
        for i, p in enumerate(g):
            near = inside[i] or (i > 0 and inside[i - 1]) or (i + 1 < len(g) and inside[i + 1])
            if near:
                run.append(p)
            elif run:
                if len(run) >= 2: out.append(simplify(run))
                run = []
        if len(run) >= 2:
            out.append(simplify(run))
    return out


def dedupe(kind, items):
    seen, out = set(), []
    for it in items:
        key = json.dumps(it, separators=(",", ":"))
        if key not in seen:
            seen.add(key); out.append(it)
    return out


def bbox_of_cells(cs):
    la0 = min(c[0] for c in cs) * CELL; lo0 = min(c[1] for c in cs) * CELL
    la1 = (max(c[0] for c in cs) + 1) * CELL; lo1 = (max(c[1] for c in cs) + 1) * CELL
    return "%.4f,%.4f,%.4f,%.4f" % (la0, lo0, la1, lo1)


def encode_line(g, start=(0, 0)):
    """[[lat, lon], ...] -> [dlat, dlon, ...] in 1e-5 degrees (~1 m), the first point from `start`."""
    out, (pa, po) = [], start
    for la, lo in g:
        a, b = int(round(la * 1e5)), int(round(lo * 1e5))
        out += [a - pa, b - po]
        pa, po = a, b
    return out


def decode_line(a, start=(0, 0)):
    g, (la, lo) = [], start
    for i in range(0, len(a), 2):
        la += a[i]; lo += a[i + 1]
        g.append([la / 1e5, lo / 1e5])
    return g


def merge_lines(lines):
    """Join lines that continue one another (OSM splits a motorway at every bridge, lane change
    and junction): the same segments in fewer, longer lines. Lossless for the crossing test,
    which only looks at segments."""
    key = lambda p: (int(round(p[0] * 1e5)), int(round(p[1] * 1e5)))
    starts, ends = {}, set()
    for i, g in enumerate(lines):
        starts.setdefault(key(g[0]), []).append(i)
        ends.add(key(g[-1]))
    used, out = [False] * len(lines), []
    order = [i for i, g in enumerate(lines) if key(g[0]) not in ends] + list(range(len(lines)))
    for i in order:
        if used[i]:
            continue
        used[i] = True
        g = list(lines[i])
        while True:
            nxt = next((j for j in starts.get(key(g[-1]), ()) if not used[j]), None)
            if nxt is None:
                break
            used[nxt] = True
            g += lines[nxt][1:]
        out.append(g)
    return out


def encode_lines(lines):
    """Lines sorted by their first point, each one's first point a step from the one before:
    with the plain first point every short motorway piece cost ~18 bytes before its first delta."""
    out, prev = [], (0, 0)
    for g in sorted(lines):
        out.append(encode_line(g, prev))
        prev = (int(round(g[0][0] * 1e5)), int(round(g[0][1] * 1e5)))
    return out


def decode_lines(z):
    out, prev = [], (0, 0)
    for a in z:
        g = decode_line(a, prev)
        out.append(g)
        prev = (int(round(g[0][0] * 1e5)), int(round(g[0][1] * 1e5)))
    return out


POINT_KINDS = ("toilets", "playground")


def load(path=None):
    """The cache as plain lists, however it is stored: highway lines delta-encoded ("hwyz"),
    points as one sorted delta list ("<kind>z"), cells run-length encoded ("cellz")."""
    path = path or CACHE
    A = json.load(open(path)) if os.path.exists(path) else {}
    if "hwyz" in A:
        A["hwy"] = decode_lines(A.pop("hwyz")) if A.get("v", 1) >= 3 else [decode_line(a) for a in A.pop("hwyz")]
    for k in POINT_KINDS:
        if k + "z" in A:
            A[k] = decode_line(A.pop(k + "z"))
    if "cellz" in A:            # [i, j, run, j, run, ...] per row of cells
        A["cells"] = ["%d,%d" % (r[0], j + d) for r in A.pop("cellz") for j, n in zip(r[1::2], r[2::2]) for d in range(n)]
    A["v"] = VERSION
    return A


def save(cache, path=None):
    path = path or CACHE
    out = dict(cache)
    out["hwyz"] = encode_lines(merge_lines(out.pop("hwy", [])))
    for k in POINT_KINDS:
        if k in out:
            out[k + "z"] = encode_line(sorted(out.pop(k)))
    rows = {}
    for c in out.pop("cells", []):
        i, j = (int(x) for x in c.split(","))
        rows.setdefault(i, []).append(j)
    out["cellz"] = []
    for i in sorted(rows):
        r, js = [i], sorted(rows[i])
        for j in js:
            if len(r) > 1 and r[-2] + r[-1] == j:
                r[-1] += 1
            else:
                r += [j, 1]
        out["cellz"].append(r)
    # Write-then-rename: a crash mid-dump must never leave a truncated cache behind.
    with open(path + ".tmp", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    os.replace(path + ".tmp", path)


def got_for(kinds, bodies, tries):
    got = {}
    for body in bodies:
        d = query(body, tries)
        if d is None:
            return None
        for k, els in split(d.get("elements", [])).items():
            got.setdefault(k, []).extend(els)
        time.sleep(PAUSE)
    return got


def add(cache, kinds, got, cs):
    counts = []
    for k in kinds:
        items = clip(k, to_items(k, got.get(k, [])), cs)
        cache[k] = dedupe(k, cache.get(k, []) + items)
        counts.append("%s %d" % (k, len(items)))
    return ", ".join(counts)


def done_within(tid, done):
    """Is this tile, or a larger tile holding it, already fetched? (An interrupted run may be
    carried on with a different tile size.)"""
    size, ij = tid.split(":")
    size = float(size); i, j = (int(x) for x in ij.split(","))
    for d in done:
        ds, dij = d.split(":")
        ds = float(ds); di, dj = (int(x) for x in dij.split(","))
        if ds >= size and math.floor(i * size / ds) == di and math.floor(j * size / ds) == dj:
            return True
    return False


def fill_kinds(cache, kinds, area):
    """Every covered cell for these kinds, a tile at a time. Progress is saved after each tile
    ("partial"), so an interrupted run carries on where it stopped. A tile Overpass will not
    answer is split in four, down to half a degree."""
    part = cache.get("partial") or {}
    if part.get("kinds") != kinds:
        part = {"kinds": kinds, "done": []}
        for k in kinds:
            cache[k] = []
    cache["partial"] = part
    todo = []
    tiles = {}
    for c in area:
        tiles.setdefault((math.floor(c[0] * CELL / TILE), math.floor(c[1] * CELL / TILE)), []).append(c)
    for t in sorted(tiles):
        todo.append((TILE, t, tiles[t]))
    solo = set()
    while todo:
        size, t, cs = todo.pop(0)
        tid = "%g:%d,%d" % (size, t[0], t[1])
        if done_within(tid, part["done"]):
            continue
        # Small neighbouring tiles go in one request (one box each): most of the country is a
        # handful of cells per tile, and every request waits its turn at Overpass.
        group = [(tid, t, cs)]
        if size == TILE and tid not in solo:
            while todo and todo[0][0] == TILE and len(group) < GROUP_TILES and "%g:%d,%d" % (TILE, *todo[0][1]) not in solo and \
                    sum(len(g[2]) for g in group) + len(todo[0][2]) <= GROUP_CELLS:
                s2, t2, c2 = todo.pop(0)
                t2id = "%g:%d,%d" % (s2, t2[0], t2[1])
                if not done_within(t2id, part["done"]):
                    group.append((t2id, t2, c2))
        got = got_for(kinds, ["".join(block(kinds, bbox_of_cells(g[2])) for g in group)], 4 if size > 0.5 else 7)
        if got is None and len(group) > 1:
            print("  %d tiles together: no answer; one at a time" % len(group), flush=True)
            todo[:0] = [(size, g[1], g[2]) for g in group]
            solo.update(g[0] for g in group)
            continue
        if got is None:
            if size <= 0.5:
                print("  tile %s: Overpass gave up" % tid, flush=True)
                return False
            half, sub = size / 2, {}
            for c in cs:
                sub.setdefault((math.floor(c[0] * CELL / half), math.floor(c[1] * CELL / half)), []).append(c)
            print("  tile %s: too big for Overpass right now; trying it as %d smaller tiles" % (tid, len(sub)), flush=True)
            todo[:0] = [(half, k, v) for k, v in sorted(sub.items())]
            continue
        allc = set(c for g in group for c in g[2])
        msg = add(cache, kinds, got, allc)
        part["done"].extend(g[0] for g in group)
        save(cache)
        print("  tile %s (%d tiles, %d cells, %d left): %s" % (",".join(g[0] for g in group), len(group), len(allc), len(todo), msg), flush=True)
    return True


def fill_cells(cache, cells):
    """New cells (a charger added since the last run): one box per cell, BATCH cells a request."""
    groups = [cells[i:i + BATCH] for i in range(0, len(cells), BATCH)]
    for n, cs in enumerate(groups, 1):
        bodies = ["".join(block([k], bbox_of_cells([c])) for c in cs) for k in KINDS]
        got = got_for(list(KINDS), bodies, 7)
        if got is None:
            print("  batch %d/%d: Overpass gave up; the cache keeps what it has" % (n, len(groups)), flush=True)
            return False
        msg = add(cache, list(KINDS), got, set(cs))
        cache["cells"] = sorted(set(cache.get("cells", [])) | {ckey(c) for c in cs})
        save(cache)
        print("  batch %d/%d (%d cells): %s" % (n, len(groups), len(cs), msg), flush=True)
    return True


def cells_of(cache):
    return {tuple(int(x) for x in k.split(",")) for k in cache.get("cells", [])}


def main():
    chargers = json.load(open(os.path.join(HERE, "chargers.json")))
    need = needed_cells(chargers)
    cache = load()
    if cache.get("v") != VERSION:
        cache = {"v": VERSION, "cell": CELL}

    # 1. Kinds the cache does not have (or only half has): every covered cell, by tile.
    missing = (cache.get("partial") or {}).get("kinds") or [k for k in KINDS if k not in cache]
    if missing:
        area = cells_of(cache) | need
        print("Fetching %s for %d cells" % (", ".join(missing), len(area)), flush=True)
        if not fill_kinds(cache, missing, area):
            save(cache)     # "partial" stays, so these kinds still count as missing
            raise SystemExit("ABORT: could not fetch %s yet; run again to carry on" % ", ".join(missing))
        cache.pop("partial", None)
        cache["cells"] = sorted({ckey(c) for c in area})
        save(cache)

    # 2. Cells a new charger needs.
    new = sorted(need - cells_of(cache))
    ok = True
    if new:
        print("%d new cells to fill" % len(new), flush=True)
        ok = fill_cells(cache, new)
    print("amenities.json: %d cells; %s" % (len(cache.get("cells", [])),
          ", ".join("%s %d" % (k, len(cache.get(k, []))) for k in KINDS)))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
