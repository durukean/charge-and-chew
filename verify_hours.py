#!/usr/bin/env python3
"""Exercise the opening_hours parser in index.html against real OSM strings.

Getting this wrong is worse than omitting it: sending someone to a closed shop is a
concrete failure. Anything the parser cannot read must return null so the UI falls back to
showing the raw string rather than guessing.
"""
import json, os, re, subprocess, sys, tempfile, shutil, http.server, socketserver, threading

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# (spec, ISO datetime, expected open state or None when the parser should decline)
CASES = [
    ("24/7",                              "2026-08-31T03:00", True),
    ("Mo-Fr 08:00-18:00",                 "2026-08-31T09:00", True),    # Monday 09:00
    ("Mo-Fr 08:00-18:00",                 "2026-08-31T19:00", False),
    ("Mo-Fr 08:00-18:00",                 "2026-08-30T12:00", False),   # Sunday
    ("Mo-Sa 08:00-18:00",                 "2026-09-05T10:00", True),    # Saturday
    ("Mo-Fr 10:00-20:30; Sa 09:30-18:00; Su 10:00-18:00", "2026-08-30T11:00", True),
    ("Mo-Fr 09:00-12:00,13:00-17:00",     "2026-08-31T12:30", False),   # lunch gap
    ("Mo-Fr 09:00-12:00,13:00-17:00",     "2026-08-31T14:00", True),
    ("Mo,We,Fr 09:00-17:00",              "2026-09-01T10:00", False),   # Tuesday
    ("Mo,We,Fr 09:00-17:00",              "2026-09-02T10:00", True),    # Wednesday
    ("Mo-Su 20:00-02:00",                 "2026-08-31T01:00", True),    # spans midnight
    ("Mo-Fr 08:00-18:00; Sa off",         "2026-09-05T10:00", False),
    ("sunrise-sunset",                    "2026-08-31T12:00", None),    # unparseable
    ("Mo-Fr 08:00-18:00 open \"by appt\"","2026-08-31T09:00", None),
]

def main():
    os.chdir(HERE)
    port = 8757
    srv = socketserver.TCPServer(("127.0.0.1", port), http.server.SimpleHTTPRequestHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp()
    probe = os.path.join(HERE, "_hours_probe.html")
    open(probe, "w").write("""<!doctype html><meta charset="utf-8"><body><pre id="o"></pre>
<iframe src="/index.html?nosw=1" style="display:none" onload="run(this)"></iframe>
<script>
const CASES = %s;
function run(f){
  const fn = f.contentWindow.__hoursNow;
  const out = CASES.map(([spec, when, exp]) => {
    let got; try { got = fn(spec, new Date(when)); } catch(e){ got = 'ERR ' + e.message; }
    return { spec, when, exp, got: got && typeof got === 'object' ? got.open : got, note: got && got.note };
  });
  document.getElementById('o').textContent = JSON.stringify(out);
}
</script>""" % json.dumps(CASES))
    out = os.path.join(tmp, "o.html")
    subprocess.run([CHROME, "--headless=new", "--virtual-time-budget=9000",
                    f"--dump-dom", f"http://127.0.0.1:{port}/_hours_probe.html"],
                   stdout=open(out, "w"), stderr=subprocess.DEVNULL, timeout=90)
    dom = open(out).read()
    os.remove(probe); srv.shutdown(); shutil.rmtree(tmp, ignore_errors=True)
    m = re.search(r'<pre id="o">(.*?)</pre>', dom, re.S)
    if not m or not m.group(1).strip():
        print("FAIL: probe produced nothing"); return 1
    got = json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    bad = 0
    for r in got:
        ok = (r["got"] is None and r["exp"] is None) or (r["got"] == r["exp"])
        if not ok: bad += 1
        print(f"  {'ok  ' if ok else 'FAIL'}  {r['spec'][:38]:40s} @ {r['when'][5:]}  -> {r['got']}"
              f"{'  (' + str(r['note']) + ')' if r.get('note') else ''}")
    if bad: print(f"\n{bad} case(s) wrong"); return 1
    print(f"\nopening hours: {len(got)}/{len(got)} cases pass")
    return 0

if __name__ == "__main__":
    sys.exit(main())
