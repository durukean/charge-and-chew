#!/usr/bin/env python3
"""Fill data/amenities.json from an OpenStreetMap extract instead of Overpass.

    python3 data/amenities_from_pbf.py us-latest.osm.pbf [--out data/amenities.json]

The full fill: every cell within a kilometre of a charger, all kinds at once, from a Geofabrik
.osm.pbf (the US extract is ~12 GB; a state extract for testing). The weekly refresh keeps using
fetch_amenities.py, which only asks Overpass for the cells new chargers need.

Needs osmium-tool on PATH. Two passes: `osmium tags-filter` keeps only the objects the Overpass
selectors in fetch_amenities.KINDS would match (plus the nodes their geometry needs), then
`osmium export` writes them as GeoJSON text sequences, read here a line at a time. The same
rules as the Overpass queries: access=private/no left out of toilets and playgrounds; motorways,
and trunk roads only where oneway=yes; neither on a bridge or in a tunnel. Positions as Overpass
gives them: a node's own, the centre of a way's or relation's bounding box ("center"), or the
bounding box itself ("bb"). Then the same clip, simplification and de-duplication as a fetch.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_amenities as F

PRIVATE = {"private", "no"}
BRIDGE = {"yes", "viaduct", "cantilever", "covered"}
TUNNEL = {"yes", "building_passage", "culvert"}
FILTERS = ["nwr/amenity=toilets", "nwr/leisure=playground", "nwr/shop=mall", "nwr/highway=rest_area,services",
           "w/highway=motorway,trunk"]


def kinds_of(t):
    """The fetch_amenities kinds an object with these tags belongs to (the Overpass selectors)."""
    out = []
    if t.get("amenity") == "toilets" and t.get("access") not in PRIVATE:
        out.append("toilets")
    if t.get("leisure") == "playground" and t.get("access") not in PRIVATE:
        out.append("playground")
    if t.get("shop") == "mall":
        out.append("mall")
    if t.get("highway") in ("rest_area", "services"):
        out.append("rest")
    return out


def is_hwy(t, osm_type):
    if osm_type != "w" or t.get("bridge") in BRIDGE or t.get("tunnel") in TUNNEL:
        return False
    return t.get("highway") == "motorway" or (t.get("highway") == "trunk" and t.get("oneway") == "yes")


def coords(geom):
    """Every position in a GeoJSON geometry."""
    t, c = geom["type"], geom["coordinates"]
    if t == "Point":
        return [c]
    if t in ("LineString", "MultiPoint"):
        return c
    if t in ("Polygon", "MultiLineString"):
        return [p for ring in c for p in ring]
    if t == "MultiPolygon":
        return [p for poly in c for ring in poly for p in ring]
    return []


def run(pbf, chargers, out_path, keep_tmp=False, tmp_dir=None):
    need = F.needed_cells(chargers)
    tmp = tempfile.mkdtemp(prefix="amen-", dir=tmp_dir)
    try:
        filt = os.path.join(tmp, "filtered.osm.pbf")
        print("osmium tags-filter ...", flush=True)
        subprocess.run(["osmium", "tags-filter", "--overwrite", "-o", filt, pbf] + FILTERS, check=True)
        print("osmium export ...", flush=True)
        p = subprocess.Popen(["osmium", "export", "-f", "geojsonseq", "-x", "print_record_separator=false",
                              "-a", "type,id", "-i", "sparse_file_array," + os.path.join(tmp, "nodes.idx"),
                              "--geometry-types", "point,linestring,polygon", filt],
                             stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
        items = {k: [] for k in F.KINDS}
        seen = set()
        n = 0
        for line in p.stdout:
            line = line.strip()
            if not line:
                continue
            f = json.loads(line)
            t = f.get("properties") or {}
            ot, oid = t.get("@type", "")[:1], t.get("@id")
            g = f.get("geometry")
            if not g:
                continue
            n += 1
            ks = kinds_of(t)
            if ks and (ot, oid, "p") not in seen:
                seen.add((ot, oid, "p"))
                pts = coords(g)
                if pts:
                    lo0, lo1 = min(q[0] for q in pts), max(q[0] for q in pts)
                    la0, la1 = min(q[1] for q in pts), max(q[1] for q in pts)
                    for k in ks:
                        if F.KINDS[k][1] == "center":
                            it = [F.r5((la0 + la1) / 2), F.r5((lo0 + lo1) / 2)]
                        else:
                            it = [F.r5(la0), F.r5(lo0), F.r5(la1), F.r5(lo1)]
                        items[k].extend(F.clip(k, [it], need))
            if is_hwy(t, ot) and g["type"] == "LineString" and (ot, oid, "h") not in seen:
                seen.add((ot, oid, "h"))
                line_ = [[F.r5(q[1]), F.r5(q[0])] for q in g["coordinates"]]
                if len(line_) >= 2:
                    items["hwy"].extend(F.clip("hwy", [line_], need))
        if p.wait() != 0:
            raise SystemExit("osmium export failed")
        cache = {"v": F.VERSION, "cell": F.CELL, "source": os.path.basename(pbf)}
        for k in F.KINDS:
            cache[k] = F.dedupe(k, items[k])
        cache["cells"] = sorted(F.ckey(c) for c in need)
        F.save(cache, out_path)
        print("%d features read; %s; %d cells -> %s (%d bytes)" % (
            n, ", ".join("%s %d" % (k, len(cache[k])) for k in F.KINDS), len(need), out_path, os.path.getsize(out_path)))
        return cache
    finally:
        if not keep_tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pbf")
    ap.add_argument("--out", default=F.CACHE)
    ap.add_argument("--chargers", default=os.path.join(F.HERE, "chargers.json"))
    ap.add_argument("--tmp", help="where the filtered extract goes (default: the system temp dir)")
    a = ap.parse_args()
    if not shutil.which("osmium"):
        raise SystemExit("osmium-tool is not installed (brew install osmium-tool / apt install osmium-tool)")
    run(a.pbf, json.load(open(a.chargers)), a.out, tmp_dir=a.tmp)


if __name__ == "__main__":
    main()
