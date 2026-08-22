# Charge & Chew

Tesla Superchargers within a 10-minute walk of the restaurants and stores you actually want to stop at.
Static site — no backend, no API keys.

- `index.html` — the interactive map (Explore + Road Trip modes). Deep links: `?chain=IHOP,Walmart&state=TX`, `?from=Los Angeles, CA&to=Las Vegas, NV`
- `data.js` — precomputed Supercharger ⇄ chain matches (generated)
- `near/` — ~1,000 generated SEO pages (one per chain, one per chain × state)
- `data/fetch_pois.py` — pulls Superchargers from supercharge.info and chain locations from OpenStreetMap (Overpass), matches within 800 m, writes `data.js`
- `build.py` — generates `near/`, `sitemap.xml`, `robots.txt`

## Refresh data (monthly-ish)
```
curl -s https://supercharge.info/service/supercharge/allSites -o data/allSites.json
rm data/pois.json            # optional: force re-download of chain locations
python3 data/fetch_pois.py   # ~20 min, polite to Overpass
python3 build.py --base https://YOUR-DOMAIN
```

## Deploy
Any static host. For GitHub Pages: push to `main`, enable Pages on the repo root, point your domain at it
(add a `CNAME` file containing the domain).

Data: supercharge.info (chargers), OpenStreetMap (chains). Not affiliated with Tesla, Inc.
