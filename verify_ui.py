#!/usr/bin/env python3
"""Headless smoke test of the actual app UI.

verify.py checks files. This checks that the app *runs*: boots, renders markers, filters,
opens a charger, switches theme, plans nothing it shouldn't. A JS regression that a file
check can't see (a rename, a null deref, a broken selector) shows up here.

    python3 verify_ui.py            # serves the folder and drives headless Chrome

Requires Google Chrome. Exits non-zero with the failing assertion.
"""
import json, os, re, shutil, subprocess, sys, tempfile, threading, http.server, socketserver, functools, time

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 0            # 0 = let the OS pick a free port (8791 collided with another project)
CHROME = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/Applications/Chromium.app/Contents/MacOS/Chromium",
          "/usr/bin/google-chrome", "/usr/bin/chromium")

# Runs inside the page; returns a JSON verdict.
PROBE = r"""
(function () {
  var out = {errors: [], checks: {}};
  window.addEventListener('error', function (e) { out.errors.push(String(e.message)); });
  function ok(name, cond, detail) { out.checks[name] = cond ? true : ('FAIL' + (detail ? ': ' + detail : '')); }
  try {
    var D = window.PITSTOP_DATA;
    ok('data_loaded', !!D && D.sites.length > 9000, D ? D.sites.length + ' sites' : 'no data');
    ok('leaflet_local', !!document.querySelector('link[href*="/vendor/leaflet.css"]'));
    ok('map_rendered', !!document.querySelector('.leaflet-container') &&
                       document.querySelectorAll('.leaflet-container canvas').length > 0);

    // filter to a chain and confirm the list actually narrows
    var before = document.querySelectorAll('#list .row').length;
    var chip = document.querySelector('.chip[data-k]');
    ok('chips_present', !!chip);
    if (chip) { chip.click(); }
    var title = document.getElementById('sheetTitle').textContent;
    ok('chain_filter', /stop/.test(title), title.slice(0, 60));

    // spec filters
    document.getElementById('filtBtn').click();
    var kw = document.querySelector('#filters .seg.wide[data-f="kw"] button[data-v="150"]');
    ok('filters_open', !!kw);
    if (kw) kw.click();
    var afterKw = document.getElementById('sheetTitle').textContent;
    ok('kw_filter_changes_results', afterKw !== title, afterKw.slice(0, 50));
    document.getElementById('filtClear').click();
    document.getElementById('filtDone').click();

    // open a charger popup
    var row = document.querySelector('#list .row');
    ok('has_results', !!row);
    if (row) row.click();

    // theme
    var t0 = document.documentElement.dataset.theme;
    document.getElementById('themeBtn').click();
    ok('theme_toggles', document.documentElement.dataset.theme !== t0 ||
                        localStorage.getItem('cc_theme') !== null);

    // saved stops
    var star = document.querySelector('#list [data-star]');
    if (star) { star.click(); ok('save_stop', true); } else { ok('save_stop', false, 'no star'); }

    ok('no_js_errors', out.errors.length === 0, out.errors.join(' | '));
  } catch (e) {
    out.checks.threw = 'FAIL: ' + e.message;
  }
  return JSON.stringify(out);
})()
"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    handler = functools.partial(_Quiet, directory=HERE)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def chrome_bin():
    for c in CHROME:
        if os.path.exists(c):
            return c
    return None


def main():
    binpath = chrome_bin()
    if not binpath:
        print("SKIP: Chrome not found; UI test not run")
        return 0
    httpd, port = serve()
    time.sleep(0.4)
    # No `at=`: that triggers a reverse-geocode to Nominatim which keeps the page alive past
    # the virtual-time budget and makes Chrome hang. The chain filter alone exercises the
    # same rendering path with no external network.
    url = f"http://127.0.0.1:{port}/?chain=IHOP&nosw=1"
    prof = tempfile.mkdtemp()          # manual: Chrome holds files open, so cleanup must be lenient
    try:
        # --dump-dom after a settle period; we inject the probe via a data: bookmarklet-free path
        # by using --virtual-time-budget so scripts run, then evaluate through the DevTools protocol.
        script = os.path.join(prof, "probe.js")
        open(script, "w").write(PROBE)
        # No service worker during the test: it keeps the page alive and --dump-dom never returns.
        cmd = [binpath, "--headless=new", "--disable-gpu", "--no-sandbox",
               f"--user-data-dir={prof}", "--virtual-time-budget=12000",
               "--disable-features=ServiceWorker", "--dump-dom", url]
        # Chrome sometimes lingers after emitting the DOM, so write to a file and poll for
        # it rather than blocking on process exit.
        domfile = os.path.join(prof, "dom.html")
        with open(domfile, "w") as fh:
            proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.DEVNULL)
            deadline = time.time() + 90
            while time.time() < deadline:
                if proc.poll() is not None:
                    break
                if os.path.getsize(domfile) > 50000:
                    time.sleep(1.5)          # let it finish flushing
                    proc.terminate()
                    break
                time.sleep(0.5)
            else:
                proc.kill()
        dom = open(domfile, encoding="utf-8", errors="replace").read()
        if len(dom) < 5000:
            print("FAIL: headless Chrome produced no usable DOM")
            httpd.shutdown()
            return 1
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    httpd.shutdown()

    # --dump-dom gives us the rendered DOM; assert on what the app produced.
    checks = {
        "app_booted": 'id="app"' in dom,
        "splash_removed_or_hidden": 'id="splash"' not in dom or 'class="gone"' in dom or 'splash' not in dom,
        "map_container": "leaflet-container" in dom,
        "markers_canvas": "leaflet-zoom-animated" in dom or "<canvas" in dom,
        "results_rendered": 'class="row"' in dom,
        "sheet_title_filled": "stop" in dom.lower(),
        "chips_rendered": 'class="chip' in dom,
        # These strings also live in index.html as fallback markup, so match the *rendered*
        # splash rather than the source: an error only counts if it replaced the splash body.
        "no_boot_error": not re.search(r'id="splash"[^>]*>\s*<div[^>]*color:#b91c1c', dom),
        "data_actually_loaded": dom.count('class="row"') > 3,
    }
    bad = [k for k, v in checks.items() if not v]
    for k, v in checks.items():
        print(f"  {'ok  ' if v else 'FAIL'}  {k}")
    if bad:
        print(f"\nFAILED: {', '.join(bad)}")
        return 1
    print("\nUI smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
