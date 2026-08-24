# Charge & Chew

Find EV fast chargers within a short walk of the restaurants and stores you actually want to
stop at. Live at **https://chargeandchew.com** — static site, no backend, no accounts, free to run.

## Why it exists

Every EV app answers "where can I charge?". None answered "which of these has an IHOP next to
it?". Surveys back the gap up: ~67% of EV drivers say they'd drive farther for a charger near
shopping and ~63% for one near dining. This does that lookup, for 90 chains.

## Layout

| Path | What it is |
|---|---|
| `index.html` | The whole app: map, filters, routing, car profiles, offline support |
| `data.js` | Generated. `{sites, brands, matches, cars}` — the only data the app loads |
| `near/` | Generated SEO pages: chain, and chain × state |
| `along/` | Generated SEO pages: chargers along each major interstate |
| `sw.js` / `manifest.json` | Offline + installable |
| `data/` | The pipeline (below) and its committed caches |

## Pipeline

Run in this order. Each step writes a cache that the next one reads, so a normal refresh only
re-runs the first and last steps.

```bash
python3 data/fetch_chargers.py    # US DOE/NREL AFDC -> data/chargers.json  (needs AFDC_API_KEY)
python3 data/fetch_pois.py        # OSM Overpass     -> data/pois.json      (cached per brand)
python3 data/fetch_highways.py    # OSM Overpass     -> data/highways.json  (cached per interstate)
python3 data/build_data.py        # clean + match    -> data.js
python3 build.py --base https://chargeandchew.com   # -> near/, along/, sitemap.xml, robots.txt
```

`refresh.sh` does all of it; a GitHub Action runs it monthly and pushes the result.

### Things that will bite you

- **`data/build_data.py` owns the cleaning.** It drops sub-24 kW listings, heavy-truck-only
  depots, anything named private/test, and de-duplicates twice (identical coordinates, then
  same-name-within-200 m). Names are tidied *before* de-duplication, because `FOO DCFC1` and
  `FOO DCFC2` only look like duplicates once the cabinet code is stripped.
- **A brand returning almost no POIs means a bad regex, not a rare chain.** Love's and Sonic
  both silently matched ~1 location because OSM tags them `Love's` and `Sonic`, not
  `Love's Travel Stop` / `Sonic Drive-In`. `fetch_pois.py` now warns under 40 POIs — believe it.
- **Adding a chain** = one line in `fetch_pois.py` `BRANDS`, then rerun fetch + build.
- **Bump `?v=` on `data.js` in `index.html`** whenever the data shape changes; the service
  worker caches it by URL.
- **No `??` or `?.` in `index.html`.** A syntax error blanks the whole app on older in-car
  browsers, and Tesla's centre screen is a target. CSS `inset` needs longhand fallbacks for
  the same reason.
- **Service workers don't register in every embedded browser.** Test PWA behaviour in real
  Chrome.

## SEO position

Google crawled the first ~2,400 generated pages and declined to index them
("crawled – currently not indexed"), which since the 2024 core update usually means
"templated, low unique value" — and a big thin set drags the whole pattern down. So the
sitemap is deliberately throttled to ~150 high-conviction pages (all chain pages, the biggest
chain × state pages, the interstate pages). Everything else is `noindex,follow`: still
crawlable, still passing equity, just not asking to be indexed yet. Raise `STATE_INDEX_MIN`
in `build.py` once these are indexing and ranking.

The other half of that problem is off-site: the domain has no inbound links. `LAUNCH-POST.md`
has drafts to fix that.

## Not included, on purpose

Live availability and pricing (no free feed — it needs a backend and per-network deals, and
it's where the funded competitors already win), and community reviews (cold start, plus
PlugShare owns it). Both would end the $0 hosting model.
