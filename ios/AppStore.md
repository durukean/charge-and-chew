# App Store listing

Everything App Store Connect asks for. 1.0.5 released 2026-10-19; 1.0.6 (build 35, the redesign)
released 2026-10-20; 1.0.7 (build 36) released 2026-10-22; **1.0.8** (build 39, search audit
fixes) approved 2026-10-26 and never released: it is folded into **1.1.0**. Listing, keywords and screenshots are
the 1.0.6 ones; release stays manual. The old-design preview video is gone and still needs
re-recording in the new design.

**Name** (30): `Charge & Chew: EV Stops`
**Subtitle** (30): `Fast chargers near good food`
**Category:** Navigation · secondary Travel · **Age:** 4+ · **Price:** Free

---

## Next (after 1.1.0): live on the web 2026-10-28, not yet in an iOS build

From two probes (93, then ~150 queries) the audit did not cover, and meal-timed breaks.
Draft What's New lines:
> • Meals on the way: pick when you leave and long drives suggest where to stop for breakfast, lunch and dinner, at local time, with a real meal a short walk from the charger.
> • "outlet", "casino", "brewery", "school" and other everyday words search near you instead of a town of that name in another state.
> • Cuisines: "sushi", "bbq in Austin", "thai food", "korean bbq near me" find that kind of restaurant.
> • "Directions to San Diego", "take me to Vegas" and "route to Tahoe" plan the drive from where you are.
> • Regions and downtowns: "bay area", "socal", "downtown LA".
> • State codes and street addresses: "chargers in CA", "123 Main St Boise".
> • Roads we can't follow yet (US-101, PCH) say so instead of doing nothing.
> • Landmarks: "Central Park", "Griffith Park", "Mall of America", "Bellagio hotel" go there.
> • Chains by their full or short names: "Chipotle Mexican Grill", "Pilot Travel Center", "mcd", "bdubs".
> • Chains we don't list yet, in a town: "P.F. Chang's in Phoenix", "7-Eleven in Reno".
> • Neighborhoods keep their names: Brooklyn, Harlem, East Los Angeles.
> • Misspelled cities find the city: "pheonix", "sacremento", "cincinatti", "san fransisco".
> • Nicknames and airport codes: "chi town", "atx", "mile high city", JFK, O'Hare (ORD).
> • More ways to plan a drive: "LA-SF", "SF from LA", "Vegas and back".

Also for the next build, from the 2026-11-10/11 app review (branch director/improve-2026-11-10).
Draft What's New lines, most important first:
> • Going somewhere? The app now opens on your drive: From, To, when you leave, and one tap to plan it. No location? Try LA → Vegas, Denver → SLC and more.
> • Planning at night? Your drive leaves at 8 am tomorrow by default, so the plan reads like a real day on the road ("now" is one tap away).
> • Meal stops that keep time: clocks count the time you spend at each stop, long drives say "next day" and "day 3", and late-night breaks go to places open late.
> • Share the plan, not just a link: "LA → Las Vegas · leaving 8:00 am, 12:30 pm lunch in Primm: Carl's Jr. 3 min from a 350 kW charger…", with a link to the trip guide.
> • Route lists show the best stop in each half hour of driving, with "Show all" one tap away. Stations split into one listing per plug now show as one stop.
> • Opening hours are checked at the stop's own time zone, for when you will actually get there.
> • Long cross-country routes no longer freeze for seconds while they plan.
> • Search: "Great Falls", "College Station TX", "Union Station" and "Penn Station LA" go where you mean; offline, a station search says it needs a signal.
> • Accessibility: VoiceOver announces messages and selected options, the results sheet handle is a real button, and the map respects Reduce Motion.
> • Polish: brand names never break mid-word, no hairline seams on the map, 44-point chips, one badge style.
> • After you plan a drive and tap Directions, the app may ask once (per version) for a rating; "Rate the app" is in About.

Smarter stops (batch 8, 2026-11-11, branch director/smarter-stops-2026-11-11). Draft What's New lines:
> • Open late: at night, stops say where food is likely still open (Taco Bell, Denny's, Wawa and other late chains, checked against the hours OpenStreetMap lists), and a night break says "open late" or "may be closed then".
> • Restroom likely: stops at a rest area, a travel stop like Buc-ee's or Love's, mapped public toilets, a 24-hour diner or a big store in store hours say so. Tap it for the reason. Always "likely", never a promise.
> • Good for kids: stops with a playground a short walk away show "playground 4 min", and a new filter shows only those.
> • Honest walk times: a place across a freeway or divided highway from the charger is marked "across hwy" and listed after the ones on your side; plans prefer food on your side of the road.

Take the plan with you (batch 9, 2026-11-12, branch director/calendar-2026-11-12). Draft What's New lines:
> • Add to calendar: put every stop of a planned drive in your calendar in one tap ("Charge + lunch: Carl's Jr., Primm NV"), at the right time in each stop's time zone, with the food there, what's likely open and a link back to the plan. Charge & Chew can only add events; it never sees your calendar.
> • One stop at a time: a stop on your plan says "Lunch on your plan · ~12:30 pm" with its own Add to calendar.

Audit batch A (2026-11-12/13, branch director/audit-2026-11-12). Draft What's New lines:
> • Pick the day you leave: Today, Tomorrow or any day in the next two weeks, Thanksgiving included. The plan, opening hours, calendar events and the plan you share all use that day.
> • A leaving time that has already passed today means tomorrow, and the app says so.
> • Thanksgiving and Sundays: chains that usually close then (Chick-fil-A on Sundays; Walmart, Target, Costco and others on Thanksgiving Day) are marked "usually closed", and plans pick somewhere open.
> • Directions is always one tap away on a stop, however much the stop has to say.
> • Faster: the app's fonts are built in, and long cross-country routes plan in about half the time.
> • iPad in portrait gets the proper layout; on small iPhones the welcome card fits.
> • Opening hours after midnight are read correctly: a place that closed at 11 pm is no longer "open until 3".
> • Picking one network no longer hides Tesla stops on later visits, and opening a shared link no longer changes your saved filters.
> • The map no longer goes blank for anyone who had picked the CARTO map style.

## 1.1.0 (build 45, submitted 2026-10-28, WAITING_FOR_REVIEW, manual release)

1.1.0 carries everything in 1.0.8 and in the 1.0.9 draft (build 42, never submitted). The
approved 1.0.8 was cancelled (Developer Rejected) and its version record renamed to 1.1.0.
Screenshots: the five in `ios/screenshots/1.1.0/`. No preview video.
**Promotional text:** Search that knows where you are: type a chain, a kind of place or a town and
get the fast chargers near it, even on a weak signal.
Apple's age rating gained a required "social media" question (2026): answered **No**.

**What's New:**
> Search, rebuilt to find what you mean, wherever you are.
>
> • Search a chain that isn't near the map (In-N-Out while looking at New York) and you get the ones near you, or the nearest ones, instead of an empty map.
> • A kind of place plus a town searches that town: "pharmacy in Denver", "coffee in Austin".
> • Towns that share a name pick the one near you: Pasadena from Dallas is Pasadena, Texas.
> • Landmarks and nicknames work: LAX, Yosemite, Disney World, Zion National Park, Philly, NOLA.
> • Plurals ("ihops"), common typos ("walmat") and town + state ("jackson ms") all work.
> • "From here to San Diego" starts the drive where you are, and adding a chain keeps your route.
> • Town searches work on a weak signal: any town with chargers is found without a connection.
> • A new search no longer keeps the last one's filters, and the x in the search box takes you back to where you were.
> • Dealership chargers come after public stations, under their own heading.
> • On long drives, the suggested breaks name the longest leg when a stretch has no good stop.
> • Walk times read the same everywhere ("5 min"), and station names and addresses are cleaner.

**Review notes** (replace the "what is new" steps):
> WHAT IS NEW IN 1.1.0 (search) — how to try it:
> 1. Allow location when asked (or decline: search a city instead).
> 2. Search:  pharmacy in denver   — the map goes to Denver and lists stops near pharmacies there.
> 3. Search:  in n out   — the stops nearest you, or the nearest ones in the country.
> 4. Search:  from here to san diego   — a route from your location.

---

## 1.0.8 (build 39, approved 2026-10-26, not released: folded into 1.1.0)

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
