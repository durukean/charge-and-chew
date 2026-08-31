#!/usr/bin/env python3
"""Render one social card per chain into og/<slug>.png.

Every generated page shared the same generic card, so a link to "EV chargers near IHOP in
Texas" previewed as an unrelated banner. Per-chain cards are cheap (~1.9 s each, 90 chains,
about three minutes) whereas per-page would be 2,978 renders and roughly 95 minutes, so the
state pages reuse their chain's card — it still names the right chain.

Needs headless Chrome, so it is NOT part of build.py: CI has no browser and must not break.
build.py falls back to the generic og.png for any chain whose card is missing.

Usage:  python3 -m http.server 8642 &   # build.py output must be servable
        python3 make_og.py [--only ihop,starbucks]
"""
import json, os, re, subprocess, sys, time
from data_reader import load_data

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 8642

def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")

CARD = """<!doctype html><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1200px;height:630px;background:#0e1116;color:#eef1f5;position:relative;overflow:hidden;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
.glow{{position:absolute;width:820px;height:820px;right:-230px;top:-300px;border-radius:50%;
  background:radial-gradient(circle,rgba(22,163,74,.30),rgba(245,158,11,.16) 45%,transparent 70%)}}
.in{{position:absolute;inset:0;padding:74px 78px;display:flex;flex-direction:column;justify-content:space-between}}
.top{{display:flex;align-items:center;gap:16px}}
.mk{{width:54px;height:54px;border-radius:14px;background:linear-gradient(135deg,#16a34a,#f59e0b)}}
.wm{{font-size:27px;font-weight:800;letter-spacing:-.5px}}
.wm .a{{color:#4ade80}} .wm .b{{color:#fbbf24}} .wm .c{{color:#8b949f;font-weight:600}}
h1{{font-size:{size}px;line-height:1.04;letter-spacing:-2.4px;font-weight:800;max-width:1000px}}
h1 .e{{font-size:{size}px}}
.n{{color:#4ade80}}
p{{font-size:26px;color:#a2abb7;margin-top:20px;max-width:900px;line-height:1.35}}
.foot{{display:flex;align-items:center;justify-content:space-between;font-size:20px;color:#8b949f}}
.pill{{background:rgba(74,222,128,.13);border:1px solid rgba(74,222,128,.30);color:#4ade80;
  padding:9px 17px;border-radius:999px;font-weight:700;font-size:19px}}
</style><div class="glow"></div><div class="in">
<div class="top"><div class="mk"></div><div class="wm"><span class="a">Charge</span><span class="c"> &amp; </span><span class="b">Chew</span></div></div>
<div><h1><span class="e">{emoji}</span> <span class="n">{count}</span> fast chargers<br>near {name}</h1>
<p>{blurb}</p></div>
<div class="foot"><span>chargeandchew.com</span><span class="pill">Free · no sign-up</span></div>
</div>"""

def main():
    D = load_data(os.path.join(HERE, "data.js"))
    counts = {}
    for m in D["matches"].values():
        for k in m: counts[k] = counts.get(k, 0) + 1

    only = None
    if "--only" in sys.argv:
        only = {s.strip() for s in sys.argv[sys.argv.index("--only") + 1].split(",")}

    os.makedirs(os.path.join(HERE, "og"), exist_ok=True)
    tmp = os.path.join(HERE, "og", "_card.html")
    made = skipped = 0
    for name, meta in D["brands"].items():
        sl = slug(name)
        if only and sl not in only: continue
        n = counts.get(name, 0)
        if not n: skipped += 1; continue
        # long names need a smaller headline or they overflow the card
        size = 74 if len(name) <= 14 else 64 if len(name) <= 22 else 56
        html = CARD.format(emoji=meta.get("e", "⚡"), count=f"{n:,}", name=name,
                           size=size,
                           blurb=f"Every one within a 10-minute walk of {'an' if name[0] in 'AEIOU' else 'a'} {name}. "
                                 f"All networks — Tesla, Electrify America, EVgo, ChargePoint and more.")
        open(tmp, "w", encoding="utf-8").write(html)
        out = os.path.join(HERE, "og", sl + ".png")
        subprocess.run([CHROME, "--headless=new", f"--screenshot={out}",
                        "--window-size=1200,630", "--hide-scrollbars",
                        f"http://127.0.0.1:{PORT}/og/_card.html"],
                       capture_output=True, timeout=60)
        made += 1
        print(f"  {sl}.png  ({n:,} chargers)", flush=True)
    if os.path.exists(tmp): os.remove(tmp)
    print(f"\n{made} cards written to og/ ({skipped} chains skipped: no chargers)")

if __name__ == "__main__":
    main()
