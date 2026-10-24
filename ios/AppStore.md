# App Store listing

Everything App Store Connect asks for. 1.0.5 released 2026-10-19; 1.0.6 (build 35, the redesign)
released 2026-10-20; 1.0.7 (build 36) released 2026-10-22; **1.0.8** (build 39, search audit
fixes) submitted 2026-10-24. The next version is 1.0.9. Listing, keywords and screenshots are
the 1.0.6 ones; release stays manual. The old-design preview video is gone and still needs
re-recording in the new design.

**Name** (30): `Charge & Chew: EV Stops`
**Subtitle** (30): `Fast chargers near good food`
**Category:** Navigation · secondary Travel · **Age:** 4+ · **Price:** Free

---

## 1.0.8 (build 39, submitted 2026-10-24)

**What's New:**
> Better search, clearer lists:
>
> • Searching a chain that isn't near the area on screen (In-N-Out while looking at New York) now finds the ones near you, or the nearest ones, instead of an empty map.
> • Search understands more: plurals ("ihops"), common typos ("walmat"), "jackson ms" and other town + state searches, and it keeps your route when you add a chain.
> • Dealership chargers are listed after public stations, under their own heading, since they're often for that brand's drivers.
> • Walk times read the same everywhere: "5 min".
> • On long drives, the suggested breaks say the longest leg when a stretch has no good stop.
> • Cleaner station names and addresses.
> • Saved stops and the search box behave more predictably.

**Review notes** (replace the 1.0.7 "what is new" steps):
> WHAT IS NEW IN 1.0.8 (small list and wording fixes) — how to try it:
> 1. Allow location when asked (or decline: search a city instead).
> 2. Search:  tacos in phoenix   — public stations come first; dealership chargers follow under the heading "At car dealerships".
> 3. Search:  denver to salt lake city with starbucks   — the "Suggested breaks" card gives the longest leg.

---

## 1.0.7 What's New

> Smoother everyday use:
>
> • Charge times read clearly: "~23 min" or "~1h 55m".
> • Set your car from a stop and that stop comes back, showing how long you'd charge and what the time is good for.
> • The suggestion favors what you searched for: search Starbucks and it suggests a coffee run there.
> • Filters show how many stops you'll get before you close them.
> • The route card puts distance and drive time first.
> • City searches zoom to the stops found, not the whole search circle.
> • Clearing the search box no longer loses the area you were looking at.

---

## 1.0.6

Numbers are from the 2026-10-19 data: 14,239 US DC fast chargers, 90 chains plus ice cream
shops, and 83% of those chargers have at least one of the chains within a 10-minute walk.

**Keywords** (94 of 100). Words already in the name or subtitle (ev, stops, fast, chargers, near,
good, food) are indexed anyway, so they are left out:
`charging,tesla,supercharger,road trip,electric car,ihop,restaurant,ice cream,nacs,dining,route`

**Promotional text** (170). This can be changed at any time without a new version:
> New look, and a stop card that tells you what your charge is good for: "23 min here, time for
> a coffee run at Starbucks." Long drives now suggest where to break.

**What's New** (about 900 of 4,000):
> A redesign, and a smarter road trip.
>
> • A new look: warm, calm and easier to read in the sun. Green means charging, amber means food.
> • Every big network has its own mark, so you can tell a Tesla Supercharger (red T) from
>   Electrify America, EVgo, ChargePoint and others at a glance.
> • The app opens where you are, with bigger stops that are easier to tap.
> • Set your car and each stop says what the charge is good for: a coffee run, or a sit-down meal.
> • Places say whether they're open, and on a route, whether they'll be open when you get there.
> • Long drives suggest where to take a break, show each stop's mile on the drive, and warn you
>   about the longest stretch without a fast charger.
> • Search an interstate ("I-5 with Starbucks"), a food ("tacos", "pizza"), or ice cream:
>   ice cream shops are now built in, and work offline.
> • Dark and tinted app icons. The widget opens the stop it shows.
> • Lots of smaller fixes.

**Description** (about 1,100 of 4,000):
> Charging takes 30 minutes. Might as well spend it somewhere good.
>
> Charge & Chew finds DC fast chargers within a short walk of the restaurants and stores you'd
> actually stop at: IHOP, In-N-Out, Buc-ee's, Starbucks, Target, ice cream shops and 85 more.
> 14,000+ US chargers, every network, free, no account.
>
> • Search a chain, a food ("tacos"), a city, an interstate ("I-95 with Chick-fil-A"), or a whole
>   drive: type "LA to Las Vegas" and see every stop on the way with food a few minutes' walk from
>   the charger, where to take a break, and the longest gap between fast chargers.
> • Tap a stop for walk times to each place, whether it's open, and one-tap directions.
> • Set your car for plug compatibility and a rough charge time, matched to what's nearby: long
>   enough for coffee, or for a meal.
> • Tesla, Electrify America, EVgo, ChargePoint, IONNA, Rivian and more, each with its own mark.
> • Works offline: the charger database is on your phone. Only the map needs a signal.
> • Your location never leaves your device. No ads, no tracking.
>
> Charger data: US DOE / NREL. Places: OpenStreetMap. Not affiliated with Tesla, any charging
> network or any chain.

**Screenshots** (6.9", 1320×2868): `ios/screenshots/1.0.6/`, captions in
`ios/screenshots/README.md`. Upload in order: 1-route, 2-stop, 3-nearby.

**Build:** 35.

---

## Unchanged from 1.0.5

**Privacy policy URL:** https://chargeandchew.com/privacy/
**Support URL:** https://chargeandchew.com/support/

**App Privacy (nutrition label)**:
- Location → *Precise Location* → used for App Functionality → **not linked** to identity, not used for tracking.
- Usage Data → *Product Interaction* (anonymous page counts via GoatCounter) → Analytics → **not linked**, not tracking.
- Nothing else collected. No third-party SDKs.

**Review notes:**
> The app bundles its charger database and works without a network; the map tiles are the only
> remote asset. Location is native (CoreLocation) and optional: deny it and search a city instead.
> Directions open Apple Maps or the Google Maps app. The app asks for a rating at most once, through
> the system prompt, after real use. (1.0.6 sent a step-by-step "how to try what's new" list.)

---

## 1.0.5 (live text, for reference)

**Keywords:** `ev,charger,charging,tesla,supercharger,road trip,electric car,ihop,restaurants,map,route,walk`

The description said "13,000+ US chargers", "85 more chains" and used "tire shop" as the example
search. The What's New covered plug-based route planning, per-plug speeds, Level 2, speed and
readability, and the widget.
