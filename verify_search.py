#!/usr/bin/env python3
"""Regression tests for the search-query parser.

The parser is the part users touch first and it has broken twice in ways that sent people to
the wrong state:
  - "tesla supercharger near westwood" -> Augusta, Georgia   (network word leaked into the place)
  - "tesla charger near costco in my area" -> New York       ("area" survived and got geocoded)

Runs the real parser from index.html in headless Chrome. No network calls: geocoding is not
exercised, only what the parser hands it.

    python3 verify_search.py
"""
import json, os, re, shutil, subprocess, sys, tempfile, threading, http.server, socketserver, functools, time

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/Applications/Chromium.app/Contents/MacOS/Chromium",
          "/usr/bin/google-chrome", "/usr/bin/chromium")

# query -> expected {here, chains, net, place}. None means "don't care".
CASES = [
    ("tesla charger near costco in my area", dict(here=True,  chains=["Costco"], net="tesla", place="")),
    ("chargers near me",                     dict(here=True,  chains=[],         net=None,    place="")),
    ("costco near my location",              dict(here=True,  chains=["Costco"], net=None,    place="")),
    ("chargers around here",                 dict(here=True,  chains=[],         net=None,    place="")),
    ("supercharger nearby",                  dict(here=True,  chains=[],         net="tesla", place="")),
    ("best chargers with food",              dict(here=False, chains=[],         net=None,    place="")),
    ("tesla supercharger near westwood",     dict(here=False, chains=[],         net="tesla", place="westwood")),
    ("superchargers in brooklyn",            dict(here=False, chains=[],         net="tesla", place="brooklyn")),
    ("evgo near target in austin",           dict(here=False, chains=["Target"], net="EVgo",  place="austin")),
    ("chargers near in n out in san diego",  dict(here=False, chains=["In-N-Out"], net=None,  place="san diego")),
    ("costco 92602",                         dict(here=False, chains=["Costco"], net=None,    place="92602")),
    ("starbucks charger seattle wa",         dict(here=False, chains=["Starbucks"], net=None, place="seattle wa")),
    ("charging station near buc-ees texas",  dict(here=False, chains=["Buc-ee's"], net=None,  place="texas")),
    ("cheapest fast charging near walmart",  dict(here=False, chains=["Walmart"], net=None,   place="")),
    ("ihop",                                 dict(here=False, chains=["IHOP"],   net=None,    place="")),
    ("mcdonalds near me",                    dict(here=True,  chains=["McDonald's"], net=None, place="")),
    ("electrify america near walmart in dallas tx",
                                             dict(here=False, chains=["Walmart"], net="Electrify America", place="dallas tx")),
    # Regressions: filler words used to survive into the place text and get geocoded to a
    # real town ("wheres to" -> West Springfield, MA), teleporting the map mid-search.
    ("wheres the nearest supercharger to an in n out",
                                             dict(here=False, chains=["In-N-Out"], net="tesla", place="")),
    ("whats the closest charger to a target",dict(here=False, chains=["Target"],   net=None,    place="")),
    ("i want to find a charger near costco", dict(here=False, chains=["Costco"],   net=None,    place="")),
    ("show me chargers near walmart",        dict(here=False, chains=["Walmart"],  net=None,    place="")),
]


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    binpath = next((c for c in CHROME if os.path.exists(c)), None)
    if not binpath:
        print("SKIP: Chrome not found")
        return 0

    handler = functools.partial(_Quiet, directory=HERE)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)

    # A tiny page that loads the app's script context and prints parse results into the DOM.
    probe = os.path.join(HERE, "__search_probe.html")
    cases_json = json.dumps([c[0] for c in CASES])
    open(probe, "w").write(f"""<!doctype html><meta charset=utf-8>
<div id=out>pending</div>
<script>
window.__ready = function () {{
  var P = window.__parseQuery, qs = {cases_json}, r = [];
  for (var i = 0; i < qs.length; i++) {{
    var p = P(qs[i]);
    r.push({{q: qs[i], here: !!p.here, chains: p.chains, net: p.net, place: p.place}});
  }}
  document.getElementById('out').textContent = JSON.stringify(r);
}};
</script>
<iframe src="/?nosw=1" style="width:900px;height:700px" onload="setTimeout(function(){{
  try {{ window.__parseQuery = this.contentWindow.__parseQuery; window.__ready(); }}
  catch (e) {{ document.getElementById('out').textContent = 'ERR ' + e.message; }}
}}.bind(this), 6000)"></iframe>""")

    prof = tempfile.mkdtemp()
    try:
        domfile = os.path.join(prof, "dom.html")
        cmd = [binpath, "--headless=new", "--disable-gpu", "--no-sandbox",
               f"--user-data-dir={prof}", "--virtual-time-budget=15000",
               "--disable-features=ServiceWorker", "--dump-dom",
               f"http://127.0.0.1:{port}/__search_probe.html"]
        with open(domfile, "w") as fh:
            proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.DEVNULL)
            deadline = time.time() + 90
            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                if os.path.getsize(domfile) > 400:
                    time.sleep(2)
                    proc.terminate()
                    break
                time.sleep(0.5)
            else:
                proc.kill()
        dom = open(domfile, encoding="utf-8", errors="replace").read()
    finally:
        shutil.rmtree(prof, ignore_errors=True)
        httpd.shutdown()
        try:
            os.remove(probe)
        except OSError:
            pass

    m = re.search(r'<div id="out">(.*?)</div>', dom, re.S)
    if not m or m.group(1).strip() in ("pending", ""):
        print("FAIL: parser probe produced no result (is __parseQuery still exported?)")
        return 1
    if m.group(1).startswith("ERR"):
        print("FAIL:", m.group(1)[:200])
        return 1
    try:
        got = json.loads(m.group(1))
    except Exception as e:
        print("FAIL: could not read probe output:", e)
        return 1

    bad = []
    for (q, want), g in zip(CASES, got):
        for key, exp in want.items():
            actual = g.get(key)
            if key == "chains":
                actual = list(actual or [])
            if actual != exp:
                bad.append(f"{q!r}: {key} = {actual!r}, expected {exp!r}")
    for (q, _), g in zip(CASES, got):
        print(f"  {'ok  ' if all(g.get(k) == v or (k=='chains' and list(g.get(k) or [])==v) for k, v in dict(CASES[[c[0] for c in CASES].index(q)][1]).items()) else 'FAIL'}  {q}")
    if bad:
        print("\nFAILED:")
        for b in bad:
            print("  ✗", b)
        return 1
    print(f"\nsearch parser: {len(CASES)}/{len(CASES)} cases pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
