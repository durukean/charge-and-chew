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
    # Category queries: "somewhere to eat" is a chain query that names a category. The
    # trigger word must never survive into the place text -- "hungry in denver" geocoding
    # "hungry denver" is exactly the class of bug that sent people to the wrong state.
    ("somewhere to eat near me",             dict(here=True,  chains=[], place="",       anyCat="food")),
    ("food near me",                         dict(here=True,  chains=[], place="",       anyCat="food")),
    ("hungry in denver",                     dict(here=False, chains=[], place="denver", anyCat="food")),
    ("tesla charger with lunch in barstow",  dict(here=False, chains=[], net="tesla", place="barstow", anyCat="food")),
    ("shopping near me",                     dict(here=True,  chains=[], place="",       anyCat="store")),
    # A named chain wins: the category word must not override what they actually asked for.
    ("ihop lunch",                           dict(here=False, chains=["IHOP"], place="", anyCat=None)),
    # No category word means no category filter.
    ("superchargers in brooklyn",            dict(anyCat=None)),
    # Trips typed into the search bar. The route planner is one unlabelled icon in a stack
    # of four, so this is how people will actually reach it.
    ("LA to Las Vegas",                      dict(trip="Los Angeles, CA|Las Vegas")),
    ("denver - salt lake city",              dict(trip="Denver|Salt Lake City")),
    # A hyphenated place name is one place, not two.
    ("winston-salem",                        dict(trip=None)),
    # Run-together names: "lasvegas" is nothing to a geocoder but obvious to a person.
    ("la to lasvegas",                       dict(trip="Los Angeles, CA|Las Vegas, NV")),
    ("sanfrancisco to sacramento",           dict(trip="San Francisco, CA|Sacramento")),
    ("newyork to boston",                    dict(trip="New York, NY|Boston")),
    # A real one-word city is left alone for the geocoder to disambiguate.
    ("portland to seattle",                  dict(trip="Portland|Seattle")),
    # A picked suggestion arrives comma-less ("las vegas nv"); the state code must come back
    # as ", NV" rather than being title-cased into "Nv".
    ("las vegas nv to los angeles ca",        dict(trip="Las Vegas, NV|Los Angeles, CA")),
    # ...but a trailing two-letter word that is not a state is left alone.
    ("denver to el paso tx",                  dict(trip="Denver|El Paso, TX")),
    ("los angeles to las vegas",             dict(trip="Los Angeles|Las Vegas")),
    ("chargers from denver to moab",         dict(trip="Denver|Moab")),
    ("toledo to detroit",                    dict(trip="Toledo|Detroit")),
    ("nyc -> boston",                        dict(trip="New York, NY|Boston")),
    # A chain named alongside a trip must keep BOTH: route the drive, filter to the brand.
    ("ihop from la to vegas",                dict(trip="Los Angeles, CA|Las Vegas, NV",
                                                  chains=["IHOP"])),
    # False positives are the whole risk here: every one of these contains " to " and is a
    # chain or place search, not a drive. Hijacking one would be worse than the feature.
    ("wheres the nearest supercharger to an in n out", dict(trip=None)),
    ("whats the closest charger to a target",dict(trip=None)),
    ("i want to find a charger near costco", dict(trip=None)),
    ("take me to denver",                    dict(trip=None)),
    ("can i get to denver",                  dict(trip=None)),
    ("go to san diego",                      dict(trip=None)),
    ("closest charger to me",                dict(trip=None)),
    ("chargers near me",                     dict(trip=None)),
    ("ihop",                                 dict(trip=None)),
    ("superchargers in brooklyn",            dict(trip=None)),

    # ── A category wanted ALONG a drive. This is the app's whole premise and it was
    # broken: "LA to las vegas near ice cream shop" put the entire tail into the
    # destination and routed to a town called "Las Vegas Ice Cream Shop". A wrong
    # destination that the geocoder happily resolves is worse than no route at all.
    ("LA to las vegas near ice cream shop",
        dict(trip="Los Angeles, CA|Las Vegas", filter="ice cream shop",
             poi="amenity=ice_cream+shop=ice_cream", poiLabel="ice cream shop")),
    # No joining word: the tail is cut where the known place ends.
    ("la to vegas ice cream",
        dict(trip="Los Angeles, CA|Las Vegas, NV", filter="ice cream",
             poi="amenity=ice_cream+shop=ice_cream")),
    ("denver to moab near coffee shop",
        dict(trip="Denver|Moab", filter="coffee shop", poi="amenity=cafe")),
    ("la to vegas with a gas station",
        dict(trip="Los Angeles, CA|Las Vegas, NV", poi="amenity=fuel",
             poiLabel="gas station")),
    # A named chain alongside a trip stays a chain: no live lookup, no category.
    ("la to vegas with starbucks",
        dict(trip="Los Angeles, CA|Las Vegas, NV", chains=["Starbucks"], poi=None)),
    ("ihop from la to vegas",
        dict(trip="Los Angeles, CA|Las Vegas, NV", chains=["IHOP"], filter="", poi=None)),

    # Destinations that must NEVER be cut. Every one of these is a real place whose name
    # has more than one word, or ends in something that looks like a qualifier.
    ("la to salt lake city",      dict(trip="Los Angeles, CA|Salt Lake City", filter="")),
    ("denver to el paso tx",      dict(trip="Denver|El Paso, TX", filter="")),
    ("la to san francisco",       dict(trip="Los Angeles, CA|San Francisco", filter="")),
    ("chicago to st louis",       dict(trip="Chicago|St Louis", filter="")),
    ("la to las vegas",           dict(trip="Los Angeles, CA|Las Vegas", filter="")),
    ("phoenix to new york",       dict(trip="Phoenix|New York", filter="")),
    # A destination we have no chargers in is left whole rather than guessed at.
    ("denver to moab",            dict(trip="Denver|Moab", filter="")),

    # ── Brand names typed split or joined any which way. The user's own phrase,
    # "la to santa barbara chick fila", drew the right route but matched NO chain, because
    # "chick fila" was the one spelling not in the alias table. Adjacent words are now also
    # compared with their spaces removed.
    ("la to santa barbara chick fila",
        dict(trip="Los Angeles, CA|Santa Barbara", chains=["Chick-fil-A"])),
    ("chick fila from la to santa barbara",
        dict(trip="Los Angeles, CA|Santa Barbara", chains=["Chick-fil-A"])),
    ("mc donalds near me",   dict(chains=["McDonald's"], here=True)),
    ("star bucks in austin", dict(chains=["Starbucks"], place="austin")),
    # A chain at the END of a destination is never part of the place -- even an unknown one.
    # "la to sb chick fila" used to route to a town called "Sb Chick Fila".
    ("la to sb chick fila",   dict(trip="Los Angeles, CA|Santa Barbara, CA", chains=["Chick-fil-A"])),
    ("la to ojai chick fila", dict(trip="Los Angeles, CA|Ojai", chains=["Chick-fil-A"])),
    # Zzyzx, CA is real (on I-15) but has no chargers, so it is NOT a known place: this is the
    # case that exercises the trailing-chain rule by itself -- the others are caught earlier.
    ("la to zzyzx chick fila", dict(trip="Los Angeles, CA|Zzyzx", chains=["Chick-fil-A"])),
    ("fort wayne to chicago sonic", dict(trip="Fort Wayne|Chicago", chains=["Sonic"])),
    # Squashing must never invent a chain out of ordinary words or places.
    ("coffee shop",          dict(chains=[])),
    ("la to santa barbara",  dict(trip="Los Angeles, CA|Santa Barbara", chains=[])),

    # ── Found by typing what road-trippers actually type.
    # "dc" is ALSO a noise word ("DC fast charger"), stripped before the city alias was tried,
    # so "dc to nyc" was not a trip at all -- it searched around NYC.
    ("dc to nyc",            dict(trip="Washington, DC|New York, NY")),
    ("nyc to dc",            dict(trip="New York, NY|Washington, DC")),
    ("washington dc to nyc", dict(trip="Washington, DC|New York, NY")),
    ("dc fast chargers in austin", dict(trip=None, place="austin")),   # ...and still noise here
    ("la to san diego in and out", dict(trip="Los Angeles, CA|San Diego", chains=["In-N-Out"])),
    # Words describing the visit must never reach the geocoder as a place name.
    ("where can i charge near costco", dict(chains=["Costco"], place="")),
    ("denny's 24 hours",               dict(chains=["Denny's"], place="")),
    ("starbucks drive thru",           dict(chains=["Starbucks"], place="")),
    ("mcdonalds drive-thru in phoenix", dict(chains=["McDonald's"], place="phoenix")),

    # ── Round two of real typing.
    # One slip of the thumb used to send the misspelling to the geocoder as a place.
    ("starbuks near me",       dict(chains=["Starbucks"], place="", here=True)),
    ("mcdonals in dallas",     dict(chains=["McDonald's"], place="dallas")),
    ("chik fil a",             dict(chains=["Chick-fil-A"], place="")),
    ("chikfila near me",       dict(chains=["Chick-fil-A"], place="", here=True)),
    ("chipolte in austin",     dict(chains=["Chipotle"], place="austin")),
    ("starbuck near me",       dict(chains=["Starbucks"], here=True)),
    ("walmarts near me",       dict(chains=["Walmart"], place="", here=True)),
    ("targets in houston",     dict(chains=["Target"], place="houston")),
    # ...but a real town one letter from a brand is still the town.
    ("culver city",            dict(chains=[], place="culver city")),
    ("casey",                  dict(chains=[], place="casey")),
    # The kind of stop is not a place.
    ("walmart supercenter near me", dict(chains=["Walmart"], place="", here=True)),
    ("costco gas",             dict(chains=["Costco"], place="")),
    ("free chargers in sf",    dict(place="San Francisco, CA", free=True)),
    ("chargers in sf",         dict(place="San Francisco, CA", free=False)),
    # Two-letter nicknames fell under the 3-letter floor and the search became "near me".
    ("starbucks in la",        dict(chains=["Starbucks"], place="Los Angeles, CA")),
    ("chargers in dc",         dict(place="Washington, DC")),
    ("starbucks in washington dc", dict(chains=["Starbucks"], place="Washington, DC")),
    ("tesla dc",               dict(net="tesla", place="")),
    # "or", "me" and "in" are state codes as well as filler words.
    ("portland or to seattle", dict(trip="Portland, OR|Seattle")),
    ("portland me to boston",  dict(trip="Portland, ME|Boston")),
    ("seattle to portland or", dict(trip="Seattle|Portland, OR")),
    ("chargers in portland or", dict(place="portland, OR", trip=None)),
    ("evansville in",          dict(place="evansville, IN")),
    ("find me a charger",      dict(place="")),
    ("new orleans la to houston", dict(trip="New Orleans, LA|Houston")),
    # Another way of saying a drive.
    ("halfway between la and sf", dict(trip="Los Angeles, CA|San Francisco, CA")),
    ("starbucks between dallas and houston", dict(trip="Dallas|Houston", chains=["Starbucks"])),
    # Plugs. "ccs" never names a place, on either side of a trip.
    ("ccs chargers near me",       dict(plug=1, here=True, place="")),
    ("la to vegas ccs",            dict(plug=1, trip="Los Angeles, CA|Las Vegas, NV")),
    ("ccs la to vegas",            dict(plug=1, trip="Los Angeles, CA|Las Vegas, NV")),
    ("la to vegas with ccs chargers", dict(plug=1, trip="Los Angeles, CA|Las Vegas, NV")),
    ("ccs from sf to sacramento",  dict(plug=1, trip="San Francisco, CA|Sacramento")),
    ("chademo in portland or",     dict(plug=4, place="portland, OR")),
    ("nacs near costco",           dict(plug=2, chains=["Costco"], place="")),
    ("ccs starbucks in dallas",    dict(plug=1, chains=["Starbucks"], place="dallas")),
    ("starbucks in dallas",        dict(plug=0)),
    ("ccs",                        dict(plug=1, place="", poi=None)),
    # Level 2 ("regular") chargers switch the optional layer on; the words are never a place.
    ("level 2 chargers near target", dict(l2=True, chains=["Target"], place="")),
    ("j1772 in austin",              dict(l2=True, place="austin")),
    ("la to vegas level 2",          dict(l2=True, trip="Los Angeles, CA|Las Vegas, NV")),
    ("level 2 la to vegas",          dict(l2=True, trip="Los Angeles, CA|Las Vegas, NV")),
    ("destination chargers near me", dict(l2=True, here=True, place="")),
    ("chargers in austin",           dict(l2=False)),
    # ── Round three of real typing.
    # Speed in words is a filter, never part of the place ("350kw denver" was geocoded).
    ("350kw chargers in denver",     dict(kw=350, place="denver")),
    ("150 kw chargers near me",      dict(kw=150, here=True, place="")),
    ("200kw near costco",            dict(kw=150, chains=["Costco"], place="")),
    ("chargers in denver",           dict(kw=0)),
    # One generic word is a kind of place; amenities are never places.
    ("chargers near the beach",      dict(place="")),
    ("chargers with bathrooms",      dict(place="")),
    ("chargers in long beach",       dict(place="long beach")),
    ("starbucks near the airport",   dict(chains=["Starbucks"], place="")),
    # Abbreviations the geocoder and the trip card want spelled out.
    ("ft worth to austin",           dict(trip="Fort Worth|Austin")),
    ("chargers in mt shasta",        dict(place="mount shasta")),
    # A destination with no start: a drive from where you are.
    ("where to charge on the way to tahoe", dict(trip="|South Lake Tahoe, CA")),
    ("sacramento to lake tahoe",     dict(trip="Sacramento|South Lake Tahoe, CA")),
    ("on my way to vegas with in n out",    dict(trip="|Las Vegas, NV", chains=["In-N-Out"])),
    ("driving to san diego",         dict(trip="|San Diego")),
    # Interstates are corridors, never places.
    ("chargers on i-5 with in n out", dict(hwy="I-5", chains=["In-N-Out"], place="")),
    ("superchargers on i95",         dict(hwy="I-95", net="tesla", place="")),
    # The App Store text uses these two exact phrasings.
    ("i-5 with starbucks",           dict(hwy="I-5", chains=["Starbucks"], place="")),
    ("I-95 with Chick-fil-A",        dict(hwy="I-95", chains=["Chick-fil-A"], place="")),
    ("interstate 10",                dict(hwy="I-10", place="")),
    ("I-75 ccs",                     dict(hwy="I-75", plug=1, place="")),
    ("i want chargers near me",      dict(hwy=None, here=True)),
    ("la to sf on i-5",              dict(trip="Los Angeles, CA|San Francisco, CA")),

    # ── Ice cream is a precomputed category (2026-10-18): every way of asking for it, and the
    #    common misspellings, must resolve to it -- "icea cream" used to say "Couldn't find".
    ("ice cream",            dict(chains=["Ice cream shop"])),
    ("icea cream",           dict(chains=["Ice cream shop"])),
    ("icecream",             dict(chains=["Ice cream shop"])),
    ("icecream shop",        dict(chains=["Ice cream shop"])),
    ("ice cream shops",      dict(chains=["Ice cream shop"])),
    ("gelato",               dict(chains=["Ice cream shop"])),
    ("ice cream near me",    dict(chains=["Ice cream shop"], here=True)),
    ("ice cream in phoenix", dict(chains=["Ice cream shop"], place="phoenix")),
    # Food words mean a set of chains (2026-10-19): "tacos" listed McDonald's and Wendy's.
    ("tacos",                dict(chains=["Taco Bell", "Del Taco", "Chipotle"])),
    ("pizza in denver",      dict(chains=["Domino's", "Pizza Hut", "Little Caesars"], place="denver")),
    # The About panel suggests these two.
    ("tacos in denver",      dict(chains=["Taco Bell", "Del Taco", "Chipotle"], place="denver")),
    ("bakery",               dict(poi="shop=bakery")),
    ("fried chicken near me", dict(here=True)),
    ("donuts",               dict(chains=["Dunkin'", "Krispy Kreme"])),
    ("taco bell",            dict(chains=["Taco Bell"])),
    # ── "ice cream" as a plain search, with no trip.
    ("ice cream",            dict(poi="amenity=ice_cream+shop=ice_cream", trip=None)),
    ("ice cream shop",       dict(poi="amenity=ice_cream+shop=ice_cream", poiLabel="ice cream shop")),
    ("ice cream near me",    dict(poi="amenity=ice_cream+shop=ice_cream", poiLabel="ice cream", here=True)),
    ("frozen yogurt",        dict(poi="amenity=ice_cream+shop=ice_cream")),
    # The two-word phrase must beat the single word: matching "ice" alone left "cream" as a
    # NAME filter, so every result had to be called "cream" and Baskin-Robbins was dropped.
    ("ice cream shop",       dict(poi="amenity=ice_cream+shop=ice_cream")),
    # Categories that already worked must keep working, labels included.
    ("tire shop",            dict(poi="shop=tyres", poiLabel="tire shop")),
    ("bank near me",         dict(poi="amenity=bank", poiLabel="bank", here=True)),
    ("pharmacy",             dict(poi="amenity=pharmacy", poiLabel="pharmacy")),
    ("gym",                  dict(poi="leisure=fitness_centre")),
    # A chain we precompute must not be hijacked into a live category lookup.
    ("ihop",                 dict(chains=["IHOP"])),
    ("starbucks",            dict(chains=["Starbucks"])),
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
    var tp = window.__parseTrip(qs[i]);
    /* The app hands parseQuery only the trip's trailing filter when there is one, so the
       probe has to do the same or it tests a code path nobody runs. */
    var pq = (tp && tp.filter) ? P(tp.filter) : p;
    var poi = window.__detectPoiIntent((tp && tp.filter) ? tp.filter : qs[i]);
    r.push({{q: qs[i], here: !!p.here, chains: pq.chains, net: p.net, place: p.place, free: !!p.free, plug: pq.plug || p.plug || 0, l2: !!(pq.l2 || p.l2), kw: pq.kw || p.kw || 0, hwy: p.hwy || null,
              anyCat: pq.anyCat == null ? null : pq.anyCat,
              trip: tp ? tp.from + '|' + tp.to : null,
              filter: tp ? tp.filter : null,
              poi: poi ? poi.tags.join('+') : null,
              poiLabel: poi ? poi.label : null}});
  }}
  document.getElementById('out').textContent = JSON.stringify(r);
}};
</script>
<!-- Poll for the parser instead of sleeping a fixed 6 s after onload. Chrome dumps the DOM when
     a VIRTUAL-time budget runs out; when loading was slow, onload arrived late, onload + 6 s
     overshot the budget, and the dump caught "pending" -- measured failing 2 runs in 6 on
     unchanged code. This suite gates the monthly data refresh, so a flake here silently
     skipped a month's data. Now it runs the moment the parser exists. -->
<iframe src="/?nosw=1" style="width:900px;height:700px" onload="(function (f) {{
  var n = 0, t = setInterval(function () {{
    var w = f.contentWindow; n++;
    if (w && typeof w.__parseQuery === 'function' && typeof w.__parseTrip === 'function'
          && typeof w.__detectPoiIntent === 'function') {{
      clearInterval(t);
      try {{ window.__parseQuery = w.__parseQuery; window.__parseTrip = w.__parseTrip;
             window.__detectPoiIntent = w.__detectPoiIntent; window.__ready(); }}
      catch (e) {{ document.getElementById('out').textContent = 'ERR ' + e.message; }}
    }} else if (n > 240) {{
      clearInterval(t);
      document.getElementById('out').textContent = 'ERR the app never exported its parser';
    }}
  }}, 250);
}})(this)"></iframe>""")

    def run_probe():
        prof = tempfile.mkdtemp()
        try:
            domfile = os.path.join(prof, "dom.html")
            cmd = [binpath, "--headless=new", "--disable-gpu", "--no-sandbox",
                   f"--user-data-dir={prof}", "--virtual-time-budget=90000",
                   "--disable-features=ServiceWorker", "--dump-dom",
                   f"http://127.0.0.1:{port}/__search_probe.html"]
            with open(domfile, "w") as fh:
                proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.DEVNULL)
                # Generous: measured 45-101 s under load, and a slow CI runner must not turn a
                # correct parser into a failed data refresh. It exits as soon as the dump lands.
                deadline = time.time() + 240
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
            return open(domfile, encoding="utf-8", errors="replace").read()
        finally:
            shutil.rmtree(prof, ignore_errors=True)

    # An EMPTY probe (Chrome dumped before the app had exported its parser) is an
    # environment hiccup, not a parser bug: it happened once in ~20 runs on a busy machine
    # with the code unchanged, and because this suite gates the monthly data refresh a
    # flake costs a month of data. Retry that case only; a probe that produced results, or
    # an explicit ERR, is final.
    try:
        for attempt in range(3):
            dom = run_probe()
            m = re.search(r'<div id="out">(.*?)</div>', dom, re.S)
            if m and m.group(1).strip() not in ("pending", ""):
                break
            print(f"  (probe empty on attempt {attempt + 1}; retrying)")
    finally:
        httpd.shutdown()
        try:
            os.remove(probe)
        except OSError:
            pass

    if not m or m.group(1).strip() in ("pending", ""):
        print("FAIL: parser probe produced no result in 3 attempts (is __parseQuery still exported?)")
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
