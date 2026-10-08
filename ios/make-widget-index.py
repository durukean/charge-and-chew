#!/usr/bin/env python3
"""Writes the home-screen widget's own small index of stops with food nearby.

The widget used to parse the full data.js: 4.5 MB of text decoded into Foundation objects,
measured at a 71.5 MB peak against a WidgetKit memory limit of roughly 30 MB. On a real
iPhone that is a widget killed on every refresh, stuck on its placeholder. The widget only
ever answers "nearest stop with food", so it gets exactly that: one tab-separated line per
charger with a food chain within a walk, walking distances precomputed.

    id  lat  lon  kw  stalls  net  city  st  name  food
    food = brand<US>emoji<US>metres, joined by <RS>, nearest first, at most 4

Run by sync-web.sh; ChargerStore.parseCompact reads it.

    python3 make-widget-index.py ../data.js ChargeAndChew/Web/widget.tsv
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data_reader import load_data  # noqa: E402

US, RS = "\x1f", "\x1e"


def metres(lat1, lon1, lat2, lon2):
    r, p = 6371000.0, math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def clean(s):
    return " ".join(str(s or "").replace(US, " ").replace(RS, " ").split())


def main(src, dest):
    d = load_data(src)
    brands = d["brands"]
    lines = []
    for s in d["sites"]:
        m = d["matches"].get(str(s["id"])) or {}
        food = []
        for b, (dlat, dlon) in m.items():
            info = brands.get(b)
            if not info or info.get("cat") != "food":
                continue
            # Same reconstruction as the web app's mDist(): integer degree deltas x1e4.
            food.append((metres(s["lat"], s["lon"], s["lat"] + dlat / 1e4, s["lon"] + dlon / 1e4),
                         b, info.get("e", "")))
        if not food:
            continue
        food.sort()
        f = RS.join(f"{clean(b)}{US}{clean(e)}{US}{round(m_)}" for m_, b, e in food[:4])
        lines.append("\t".join([str(s["id"]), f"{s['lat']:.5f}", f"{s['lon']:.5f}",
                                str(int(s.get("kw") or 0)), str(int(s.get("stalls") or 0)),
                                clean(s.get("net")), clean(s.get("city")), clean(s.get("st")),
                                clean(s.get("name")), f]))
    if len(lines) < 3000:
        sys.exit(f"widget index has only {len(lines)} stops -- refusing to write it")
    with open(dest + ".tmp", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(dest + ".tmp", dest)
    print(f"widget index: {len(lines)} stops, {os.path.getsize(dest) // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
