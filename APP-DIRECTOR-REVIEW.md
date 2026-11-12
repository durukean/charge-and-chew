# Charge & Chew: app review, 2026-11-10

Three read-only audits run in parallel, merged here:
- **Bugs and performance** (`.director/bugs.md`): CDP-driven headless Chrome, phone emulation at 4x CPU, Fast 3G, offline.
- **UI and accessibility** (`.director/ui.md`): 5 viewports, light and dark, 33 screenshots in `.director/screens/`.
- **Product, market and growth** (`.director/design.md`): hands-on use, competitor research, user-pain evidence, all with sources.

Code audited: `795bb53a5`, which is live on chargeandchew.com. Line numbers in the audit files refer to that commit.

---

## First impressions

- **The idea is sound and differentiated.** Every competitor (PlugShare, ABRP, Tesla, Google Maps, Apple Maps, ChargePoint, Chargeway) stops at a "Dining nearby" checkbox. None answers "which stop has In-N-Out, how far a walk, and will it be lunchtime when I get there". The new meal-timed breaks are the one thing nobody else does.
- **The product is ahead of its distribution.**
  - Traffic is about 40 visits a day.
  - There's no Search Console and almost no inbound links.
  - The launch posts are unposted, and the app has 0 App Store ratings.
  - Recent effort has gone into search long-tail fixes.
- **The first run asks the wrong question.**
  - The welcome dialog leads with "Browse all chains", though typed chain searches are rare and routes are the fastest-growing action.
  - Without location, the user gets a random national list.
- **The route view buries its best part.**
  - Two or three smart breaks sit on top of 250 raw rows that start at "mile 0", including port-split duplicates (four "City_Of_Vernon 1850 E25Th-…" rows).
  - "Leaving now" at night produces a plan of "12:10 am Break, next day", which looks broken.
- **The craft is real.**
  - The colour grammar: green means charging, amber means food.
  - The network marks, the dark theme, and the stop card's line ("23 min here, time for a coffee run at Starbucks").
  - No crashes or console errors in any normal flow, and no memory growth over a long session.

## Research summary

- **Demand evidence.** A Mach-E owner built a "dining while charging" custom GPT (July 2026) because nothing did this well.
  - Road-trip complaints centre on restrooms, night closures, kids, and stops too short for a real meal.
  - Vendor surveys: 63% prefer chargers near dining.
  - Industry: stations near amenities see several times the use, and chains are launching charge-and-dine (Bojangles, Subway, Waffle House).
- **The threat.** Google Maps plus Gemini could ship "chargers with lunch" one day. The defence is chain-level, walk-timed, meal-timed depth, and being the source AI answers cite first.
- **Timing.** Thanksgiving is Nov 26, the heaviest road-trip week and exactly the "where do we eat on the drive" moment. Nov 17–25 is the window for a push.

## Scorecard (1–10)

| Lens | Score | Why |
|---|---|---|
| Value | 7 | A unique answer, now meal-timed, but needed mainly on infrequent long drives |
| UX | 6 | Excellent natural-language search and routing. The first run is chain-first, the raw route list buries the plan, and night plans look broken |
| Visual design | 7.5 | A coherent, warm system; small rough edges (broken brand names, tile seams, misaligned edges) |
| Accessibility | 6.5 | Good focus system and dialogs. Toasts and segmented controls are silent to screen readers, no headings, map motion ignores reduced motion |
| Performance | 7 | Boot is fine: ~530 ms main task at 4x, LCP 1.1 s, CLS 0. Taps take 50–60 ms. But a **2.4–3.7 s freeze** when changing the corridor on long routes, and the list takes 9.4 s on Fast 3G for a first visit (data.js is 1.08 MB gzipped) |
| Trust / data quality | 6 | Honest sourcing. Duplicate rows, straight-line walks, and opening hours judged in the phone's time zone |
| Growth readiness | 3 | No Search Console, no links, unposted drafts, 0 reviews, shares unfurl a generic card and lose the leaving time |

---

## Top 3 highest-leverage changes

1. **Make "Meals on the way" the product, and finish it.**
   - Fix its visible failures:
     - break taps that do nothing past 300 rows;
     - "next day" on day 3;
     - clocks with no time at stops;
     - hours checks that ignore the leaving time.
   - Default the leaving time sensibly at night, put it in the URL, collapse the route list to the best stop per stretch, and make "Plan a drive" the first-run hero.
   - It's the moat, and routes are already the growth action.
2. **A Thanksgiving distribution push (Nov 17–25).**
   - **You:** Search Console and Bing, the launch posts reframed as "where to eat on an EV road trip", and answering existing "where to stop between X and Y" threads.
   - **Me:**
     - trip pages v2, with meal-timed itineraries and Q&A, expanded from 44 to ~150 drives;
     - a share that sends the plan as text and links the trip page;
     - a review prompt that can actually fire.
3. **Remove the long-route freeze, then a quality pass.**
   - The corridor/route-planning loop is O(stops × route points): 2.4–3.7 s on a phone for LA→NY. Bucketing by grid cell should make it tens of ms.
   - Then:
     - one CSS rule for the map tile seams;
     - non-breaking brand names ("In-N-" / "Out");
     - a one-pass accessibility fix (live toasts, `aria-checked`, headings, reduced-motion map).

---

## Bug list

**S1: broken, or a confidently wrong answer**

| ID | Bug |
|---|---|
| BUG-01 | On routes with more than 300 stops, most break buttons do nothing when tapped. The handler looks for a list row, but only 300 rows render. LA→NY: 17 of 23 dead. |
| BUG-02 | Multi-day drives say only "next day" for day 3 and for the arrival (a 49 h drive "arrives ~1:55 am · next day"). |

**S2: wrong in specific cases, or a real barrier**

| ID | Bug |
|---|---|
| BUG-03 | Break clocks count driving time only. "Dinner 6:00 pm" on LA→Denver is really about 8 pm; arrival is 3+ h late. |
| BUG-04 | The stop card's open/closed check uses now + drive time, not the chosen leaving time, so it contradicts the breaks card. |
| BUG-05 | Opening hours are judged on the phone's clock. An East Coast place shows "Open until 23:00" at 12:25 am local. |
| BUG-06 | Your own location is written into the URL. Reload after moving and you're stuck on the old spot as a pin. |
| BUG-07 | "great falls" does nothing ("great" and "falls" are both stripped). The same applies to Great Bend and Great Neck. |
| BUG-08 / 09 | "college station tx" goes to the middle of Texas; "chargers in college station" searches universities near you. |
| BUG-10 | "union station" goes to Union County, IL; "penn station la" goes to New Orleans. |
| PERF-01 | Changing the corridor, or planning a long route, freezes the phone for 2.4–3.7 s (LA→NY) or 1.2–1.6 s (Seattle→San Diego). |
| UI-03 | The breaks card's key information is its smallest text: 10.5 px meal labels, "Break, next day" wrapping, "mile N" cut off, no chevron. |
| UI-04 | Two different "longest" figures (charger gap and break leg) are stacked and read as one. |
| UI-05 | Brand names break at the hyphen ("In-N-" / "Out"), in the app and on /near/ pages. |
| UI-06 | The chain picker clips "McDonald'" and "Whataburger" with no ellipsis. |
| UI-07 | Faint tile seams form a grid over every light map (fractional zoom). |
| A11Y-01 | Toasts are never announced (no live region). Segmented controls don't say which option is selected. |
| ~~UI-01/02~~ | **Fixed in 795bb53a5:** the Leaving picker is now 16 px and 44 px tall on touch (no iOS zoom) and keeps focus after a change. |

**S3: minor or cosmetic**

- **Breaks:**
  - BUG-11: filler breaks bunch up, 60 minutes apart.
  - BUG-12: 2:35 am breaks at Starbucks; nothing considers night hours.
  - BUG-13: the leaving time is not in share links, and the picker only offers 5 am–10 pm.
  - BUG-14: three interstate spots get the wrong time zone (Ontario OR, West Wendover NV, western Kansas).
  - UI-13: a break promises Wendy's, but the stop card hides it under "+14".
  - UI-22: the breaks card fills a small phone's whole sheet.
- **Routes:**
  - BUG-15: clearing a route drops you on the national view.
  - UI-17: on desktop in route mode, the chips sit above the route card.
- **Offline, storage and links:**
  - BUG-16: offline search says "OpenStreetMap is busy".
  - BUG-17: a full localStorage throws on save or filter change.
  - BUG-18: corrupted saved filters show "205 undefined chargers".
  - BUG-19: `c=-5` in a link is accepted as the corridor.
- **Service worker:**
  - BUG-20: it caches one ~418 KB index.html per distinct URL.
  - BUG-21: the tile cache has never stored a tile (opaque responses).
- **Layout and polish:**
  - UI-08: sheet left edges are off by 1–6 px.
  - UI-09: a sliced chip shows under "+ All chains".
  - UI-10: the radius control has no unit.
  - UI-11: tap targets under 44 pt (chips 40 px; the handle is 18 px and the only drag target).
  - UI-12: hover sticks on touch.
  - UI-14: five badge styles in one row.
  - UI-15: in dark mode, an off switch looks lit.
  - UI-16: About links are green.
  - UI-18: the tablet width stretches the phone layout.
  - UI-19: terminology drifts ("stops" vs "chargers"; "instant", "live", "brand" tags).
  - UI-20: static page lead text is quieter than the body.
  - UI-21: the 404's 🔌 is invisible in dark.
  - UI-23: two labels are just under AA contrast (gap note 4.47:1, mile label).
- **Suspects:**
  - UI-24: "Search this area" appears without the map moving.
  - UI-25: cancelling the share sheet shows the wrong toast.

---

## Prioritized backlog (impact ÷ effort; S1 first; duplicates merged)

`[needs-approval]` means it changes product behaviour, positioning, what Google indexes, or the release. The rest are fixes.

| # | Item | Covers | Effort | Tag |
|---|---|---|---|---|
| 1 | A break tap opens the stop even beyond 300 rows (same path as `?stop=`) | BUG-01 | S | fix |
| 2 | Day labels: "next day" / "day 3" / weekday, for stops and arrival | BUG-02 | S | fix |
| 3 | Bucket route points by grid cell in `applyCorridor` (seconds → tens of ms) | PERF-01 | S–M | fix |
| 4 | Time at stops in break clocks (~20 min per break, ~40 per meal); `fillHours` uses the leaving time; hours judged in the stop's own time zone | BUG-03/04/05 | M | fix |
| 5 | Breaks card polish: 12 px amber meal pill, day change marked once, mile under the clock, chevron, gap shown as a row in the timeline, break → stop card leads with the promised chain | UI-03/04/13, BUG-11/14 | S–M | fix |
| 6 | Leaving time in the URL (`leave=`) and share links; picker covers all hours | BUG-13 | S | fix |
| 7 | Search: "great falls", "college station tx", "chargers in college station", "union station" (whole-town match before stripping; stations as landmarks), with regression cases | BUG-07–10 | S–M | fix |
| 8 | Map tile seams (one CSS rule); non-breaking brand names (app + build.py); chain picker name layout | UI-05/06/07 | S | fix |
| 9 | Accessibility pass: toast live region, `aria-checked` segments, handle as a button, headings, `aria-hidden` emoji, reduced-motion map | A11Y-01, UI-11 | S–M | fix |
| 10 | Don't write your own location into the URL (only add it when sharing) | BUG-06 | S | fix |
| 11 | Robustness: guarded storage writes, validated saved filters and `c=`, offline message, route × restores the previous area | BUG-15–19 | S | fix |
| 12 | Service worker: one shell cache entry (`ignoreSearch`); make tiles cacheable (`crossOrigin`) or delete the dead branch | BUG-20/21 | S | fix |
| 13 | Sheet rhythm: one 16 px gutter, chip fade, 44 px chips, one badge style, unit on radius, hover only on hover devices, dark switch | UI-08–12/14/15 | M | fix |
| 14 | **Smart departure default**: at night, plan for tomorrow 8 am (with "now" one tap away) | design #1 | S | needs-approval |
| 15 | **Route list collapsed** to the best stop per stretch, "Show all 250" below; merge port-split duplicate stations in `build_data.py` | design #1 | M | needs-approval |
| 16 | **First run route-first**: "Going somewhere? From → To, leaving 8 am" as the hero; chain grid below; no random national list without location (example trips instead) | design #1 | M | needs-approval |
| 17 | **Share the plan**: itinerary text ("leaving 8:00 · 12:10 lunch Primm, Carl's Jr. 3 min…"), link the /trip/ page when one exists, `ref=share` | growth #10 | S–M | needs-approval |
| 18 | **Review prompt that can fire**: after a planned route + Directions, not "5 opens on 2 days"; "Rate the app" in About | growth #6 | S | needs-approval (iOS build) |
| 19 | **Trip pages v2**: meal-timed itinerary ("leave at 8 am: breakfast in Hesperia…") + Q&A with FAQ markup; expand 44 → ~150 drives | growth #9 | M–L | needs-approval |
| 20 | Captioned App Store screenshots, meal plan first | growth #8 | S–M | needs-approval |
| 21 | "Road Food Index" data page for press (chain and interstate rankings, longest gaps) + `llms.txt` | growth #5/17 | M | needs-approval |
| 22 | City pages `/in/<metro>/` for the top ~100 metros | growth #11 | M–L | needs-approval |
| 23 | Noindex thin chain×state pages, **after** Search Console shows which earn impressions | growth #12 | S | needs-approval |
| 24 | 1.1.1 iOS build carrying all of the above (1.1.0 is still in review) | release | M | needs-approval |

**Only you can do these** (no code):
- Set up Google Search Console and Bing Webmaster Tools, and submit the sitemap. This is a DNS TXT record at GoDaddy, which I can add in your Chrome once you sign in and approve.
- Post the launch post, reframed for Thanksgiving, one community at a time: r/electricvehicles, TMC, macheforum (reply in the custom-GPT thread), Rivian and IONIQ/EV9 forums.
- Do a Show HN, and pitch the data story to Electrek, InsideEVs and food trade press.
- Create an App Store In-App Event ("Thanksgiving road trip: plan your meal stops") and submit a featuring nomination.
- Reach out to EV clubs and YouTube road-trippers.

## Next-level ideas (proposals only)

1. **Stop signals:**
   - "food open late", from hours plus a 24h chain list;
   - "restroom likely", rule-based and labelled "likely";
   - "good for kids", from playgrounds within 300 m.

   These answer the top road-trip complaints.
2. **Add to Calendar** for each meal stop (`.ics` on web, EventKit on iOS): an exportable plan with no backend.
3. **iOS Live Activity / widget: "Next meal stop".** Driven by elapsed time, with no background location. Build it after trips prove out.
4. **Honest walk times:** a detour factor, and flagging pairs that cross a freeway (the data build has motorway geometry).
5. **Monetization, after ~1,000 visits/day:**
   - Fits: a tip jar or one-time Supporter purchase, a hotel affiliate for overnight stops on multi-day drives, a B2B "Road Food Index" dataset.
   - Avoid: display ads, paywalls, paid placement.

## What not to change

- Zero backend, no account, free; the privacy posture (location never leaves the device).
- No charge-state routing and no live availability. "Where the good stops are", not "when you must charge".
- The colour grammar (green = charging, amber = food, ink = selection), the network marks (style, not logos), the flat hairline rows, and Bricolage + Inter.
- The dark theme, the stop card and its dwell line, the empty state with one action, and the Filters sheet footer.
- The 16 px touch inputs, the focus-visible system, the dialog focus trap, safe areas, and the 40% sheet framing.
- Offline bundled data. It works in dead zones where competitors don't.

## Note on the "freeze search work" advice

The product review recommends pausing search long-tail work for distribution. That conflicts with your earlier goal of search working for any query. It's your call. My suggestion: fix the four confirmed search bugs (item 7), keep the audit suites as a regression net, and move new effort to items 1–6 and the Thanksgiving push.

---

## Changes made: batch 4 (2026-11-11, approved product items 14–18)

Each change: gate `./check.sh` green before its commit, a guard in `verify.py` / `verify_ui.py` / `tools/breaks_check.mjs`, every guard mutation-tested (break the code, confirm the guard fails, restore). Screenshots at 375 px and 1280 px, light and dark, before and after.

| Item | What changed | Why | Verified by |
|---|---|---|---|
| 0a | The fade beside "+ All chains": the chip sits in a sticky `.moreend` whose backing runs under the whole chip and past the row's top and bottom (clipped by the row), fading out over 40 px; none at the scroll end | The fade was a box with hard edges, and chips showed past the chip's round corners | Close-up crops at 375 light/dark and desktop; `verify.py` (markup and CSS) |
| 0b | `r=` is one of 10/25/50 (from a link or a saved area), else 25 | `r=-5` searched within −5 mi and lit no button | Browser: −5, 7, abc → 25; `verify.py` |
| 0c | Offline, a station or landmark search says it needs a signal | "union station" went to Union, NJ with no signal | `search_audit` `@nosignal` cases (run by `--quick`) |
| 14 | Between 8 pm and 5 am at the drive's start, Leaving defaults to "tomorrow 8:00 am" ("this morning 8:00 am" after midnight), right under "now". A short evening drive done by 11 pm stays "now". `leave=` always wins; `leave=now` holds at night; the default is not written to the link | "12:10 am Break, next day" was the first plan anyone saw at night | `breaks_check`: 7 cases with a moved clock; node-run rule in `verify.py` |
| 15 | The route list shows the best stop per ~30-min stretch, ranked like the breaks, with "Show all N stops" below and a way back. `build_data.py` merges port-split listings: 397 into 326 sites, stalls summed, plugs unioned. Rebuilt offline from the committed caches, pages regenerated; 21 chain×state pages fell under the index threshold | 250 raw rows, four "City_Of_Vernon …-N" rows first | `breaks_check` (short list, one per stretch, show all, back, break taps); `?stop=` for a stop that is not listed; `verify.py` re-runs the merge rule on data.js |
| 16 | The welcome card leads with "Going somewhere?": From (your location when known), To, Leaving, Plan. Without a location, four example drives that have /trip/ guides. The chain grid stays below | The first run asked a chain question few people have | `verify_ui` rendered check; CDP walk of the example, typed and located paths |
| 17 | Share on a drive sends the itinerary text plus the /trip/ guide (or the app link with its leaving time), with `ref=share`. Uses `navigator.share`, the native sheet (text + link), or the clipboard with a toast; a cancel is silent; `share-plan` event. `build.py` writes `TRIP_PAGES` | Trips are planned in group chats, and a bare link lost the plan | `breaks_check` (text lines match the card, trip link, app link); `verify.py` checks that TRIP_PAGES equals trip/ on disk |
| 18 | The rating ask fires after a planned drive plus a Directions tap. The shell asks once per app version, after the return from Maps (`requestReview(in:)`). "Rate the app" in About, iOS only, opens the App Store write-review page. `ios/AppStore.md` "Next" draft updated | "5 opens on 2 days" never fired: 0 ratings | `breaks_check` with the shell stubbed; Swift guards in `verify.py`; Debug build on CC Shots 6.9, launched, About checked |

## Changes made: batch 5 (2026-11-11, item 19: trip pages v2)

Each change: gate `./check.sh` green before its commit, guards in `verify.py` / `verify_ui.py` / `tools/trip_plan_check.mjs` (now in `check.sh`), every guard mutation-tested. Screenshots at 375 px and 1280 px, light and dark.

| Item | What changed | Why | Verified by |
|---|---|---|---|
| 0 | Dialogs take focus themselves when they open (`tabindex=-1`, no outline), not their first control; Tab goes to the first control, Shift+Tab to the last, Escape still closes. The welcome card's × draws its keyboard ring inside the button, rounded. A `?stop=` link opens its row as a tap, so the stop card no longer opens with the ☆ ringed | On first load the × showed the keyboard ring as a square sticking out past the card's round corner, for everyone | CDP: focus on open, Tab, Shift+Tab, Escape, the Filters sheet; screenshots; `verify.py` + `verify_ui.py` (rendered `tabindex`) |
| 19a | Every `/trip/` page leads with the drive leaving at 8:00 am where it starts: a sentence ("Leave Los Angeles at 8:00 am, take a break in Barstow at 10:05 am, stop for lunch in Primm at 12:30 pm and arrive in Las Vegas around 1:55 pm", as the app says), then a table of the stops (clock, meal or break, mile, place, charger, the promised chain first), the charger-gap row and the arrival. `planner.py` is a line-by-line port of the app's corridor, `sortByKey`, `breakPicks` and `breaksCard`; the meal rules and constants are read from `index.html`. Each stop links to the app at that stop (`?from&to&c=5&leave=0800&stop=`), and so does each card's "Show on map"; the main button is "Open this drive in the app". `?stop=` now waits for the route and leads with the plan's chain. Six data-derived questions with FAQPage markup built from the same strings: where to eat, how many chargers, the longest gap (the app's rule), which chains, the app's own 10–80% estimate for three cars at the plan's stops, drive time with stops. The legs table is gone (the plan replaces it) | Search and LLM answers want "where do I stop for lunch between X and Y"; the page and the app now give the same answer | `tools/trip_plan_check.mjs`: the real app on each trip's stored route (network answered offline) against the page, every row, plus every stop link: 152/152 trips, 328 rows identical; `--quick` (12 trips) in `check.sh`. `verify.py`: plans equal `planner.py` now, sane rows, FAQ JSON-LD = visible text, JSON-LD parses |
| 19b | 43 → 152 drives. `tools/add_trips.py` holds the list; end points are looked up once the way the app's search does it (`data/trip_places.json`), routes come from OSRM with unrounded time and distance (`data/trips.json`, sequential, paced). All 43 old routes were re-fetched from those end points. 2 dropped as too thin (Kansas City → Branson, San Antonio → Corpus Christi: 14 and 15 chargers with food). Trip pages link 10 related drives (the way back, same start or end, onward, nearest) instead of all of them; the index is grouped by region; 2,659 chain pages list the drives that pass that chain (in that state); 152 trip social cards; sitemap +109 | Thanksgiving (Nov 26) and the long tail of "X to Y EV charging" | `verify.py`: pages = cached routes = index entries, related lists, no placeholder left, ≥1,000 chain pages linking drives; live check below |

**Live agreement** (`node tools/trip_plan_check.mjs --live`, the real Nominatim and OSRM, all 152): 88 identical. 61 differ only by a mile (the stored line keeps a point every ~450 m) or a clock by one 5-minute step; 3 pick a different stop or one more break (San Francisco → Yosemite Valley, Salt Lake City → West Yellowstone, New York → Burlington), where the plan sits on a threshold. Before re-fetching the 43 old routes from the app's own end points, 11 of the 12 sampled differed.

**Final runs** on a snapshot of the last commit: `node tools/breaks_check.mjs` 25/25, `node tools/search_audit.mjs` 272/272 (no retries needed). `node tools/trip_plan_check.mjs` (offline, all trips) 152/152.

## Changes made: batch 6 (2026-11-11, open issues from the verify pass)

Each change: gate `./check.sh` green before its commit, a guard (`verify.py`, `tools/breaks_check.mjs`, `tools/search_audit.mjs`, `tools/trip_plan_check.mjs`, `sw_test.mjs` or the new `tools/corridor_check.mjs`), every guard mutation-tested with `tools/mutate.py`. Visible changes screenshotted at 375 px and 1280 px, light and dark.

| # | What changed | Why | Verified by |
|---|---|---|---|
| 1 | A drive from "Your location" (welcome card, the route form's location button, "on my way to …") writes `from=me`, not its coordinates. A reload locates you and plans from where you are now; with no location it asks for a start and keeps the destination. `shareUrl()` puts the coordinates back into a link you send (the itinerary link too). A typed start is never "Your location". No new URL parameter (the iOS allow-list already has `from`) | `from=34.050,-118.250` in the address bar; a reload after moving showed "Dropped pin" at the old spot | Headless Chrome with a faked location: card "Your location → Las Vegas, NV", URL `from=me`, share link carries the start; moved to Bakersfield, reloaded, the drive starts there; location denied: "Type where you're starting from". `breaks_check` case `me -> Bakersfield`; `verify.py` |
| 2 | Each "emoji chain N min" in a trip plan's food cell is one nowrap unit (the brand's own `bn()` span kept inside). 141 trip pages regenerated; the diff is only the added span | "Denny's 3 / min," and emojis stranded at line ends at 375 px | Before/after screenshots; `verify.py` (page and `build.py` mutations) |
| 3 | Trip pages take their stops from the plan's corridor (`planner.corridor`, the app's port) and count every DC fast charger, as the app does: "about 235 DC fast chargers" on LA → Las Vegas. The lists still keep to 50 kW and up and say so; the FAQ gives both ("about 235, 228 of them 50 kW or more") | The page said 228 (50 kW+, and its own grid narrower than the corridor), the app 236 | The residual is geometry: on the stored line the app shows exactly the page's number (`trip_plan_check` now compares it, 152/152); the live OSRM line moved it by 0–2 on 11 sampled drives, hence "about". No list changed on any page. `verify.py` |
| 4 | `applyCorridor`'s cell sweep uses the same longitude bound as its per-stop search (from `hav()`, at the cell's poleward edge); `planner.py` mirrors it | 1–2 edge stops lost north of ~43.5° at 25 mi | New `tools/corridor_check.mjs` (in `check.sh`, ~4 s): the app's own `applyCorridor` and `planner.corridor` against brute force, 10 northern and southern drives plus an 8x-dense line (every-third-point path), 5/10/25 mi: 6 of 33 differed before, 33/33 after. LA → New York at 4x CPU, corridor taps: 152–317 ms (HEAD 149–355 ms). Trip pages unchanged |
| 5 | A category search nothing bundled answers clears the chains the last search left, and writes the URL, before its lookup | Offline "gym" after "bakery in denver" said "Couldn't look up gym" with `chain=Dunkin'` still in the state and URL | `search_audit` `@nosignal` case (in `--quick`): no chain, clean URL, the title; both halves mutation-tested |
| 6 | The page knows its shell version (`SW_VER` = `sw.js` `VERSION`) and asks the installing worker for its own; only a page older than its worker is offered "New version — tap to reload" | Network-first: the first visit after a deploy already is the new page and still got the toast | Local "deploys" in headless Chrome: v52 page + worker, first visit: toast before, none now; worker v53 under a v52 page: toast. `verify.py` (versions equal, the call), `sw_test` (the worker's answer) |
| 7 | About's title and × are one sticky header on the sheet's background, with a hairline once text is under it | The lone sticky × floated over the body text (web and iOS) | Screenshots scrolled and not, 375/1280, light/dark, and on CC Shots 6.9; `verify.py` |
| 8 | Opened from a break or meal, the stop card's tip leads with the plan's chain ("time for a quick meal at Taco Bell"), no slack for it; if it cannot fit, the tip says the charge is tight for that chain | "Break · Taco Bell", then "time for a coffee run at Starbucks" | Seen on the simulator before; `breaks_check` (car set: every break's tip names its chain); `verify.py` |
| 9 | iOS share: for Copy, the plan text carries the link and the link item steps aside (one pasteboard item); other activities unchanged | Copy left two pasteboard items and a paste took only the text | CC Shots 6.9 Debug build: `pbinfo` before two items / `pbpaste` text only; after one item with the link. `verify.py` |

Done differently: item 3 counts every DC fast charger (the app's way) with "about" for the live-route residual, rather than making the app count 50 kW and up. Item 1 leaves the route form's Edit view showing coordinates for a "Your location" start, as before; only the URL and reload changed. Item 6 needs `SW_VER` bumped with `VERSION` from now on (`verify.py` fails otherwise).

**Final runs** on an rsync snapshot of a3d402fb1: `node tools/breaks_check.mjs` 26/26, `node tools/search_audit.mjs` 272/273, the one miss "the woodlands" on Nominatim's "That service is slow right now" (timed out), passing when run again (1/1). `node tools/trip_plan_check.mjs` (all trips, offline) 152/152 after item 3; `tools/corridor_check.mjs` 33/33.

## Changes made: batch 7 (2026-11-11, growth before Thanksgiving: backlog 21–22, growth #5/#11/#17)

Each change: gate `./check.sh` green before its commit, `verify.py` guards mutation-tested with `tools/mutate.py` (generated outputs and `build.py`, rebuilt where the mutation was in the generator). Pages screenshotted with headless Chrome (CDP) at 375 px and 1280 px, light and dark; no horizontal overflow, no console errors.

| # | What changed | Why | Verified by |
|---|---|---|---|
| 1 | **`/road-food-index/`**: five findings chosen by the data (whoever is first or last), then chains next to the most fast chargers (top 25 of 90), chains with a charger at the most of their own locations (top 15, chains with 50+ locations; one location = a chain's OSM entries within 250 m), all 30 interstates ranked by share of chargers with food (the `/along/` corridor: 50 kW+, 3 mi; per-100-mi density; longest gap, blank for I-24/I-35/I-74 whose mapped line is not continuous), the 10 longest gaps on the 152 drives (planner.py, the trip pages' own figure), 49 states ranked (25+ sites), a "Driving for Thanksgiving" table of the 12 longest drives with the 8 am lunch stop (heading only in November up to the 4th Thursday; computed, not hard-coded), method, data date, sources, how to cite. Four CSVs (`chains`, `interstates`, `states`, `drives`), Dataset JSON-LD (name, description, date, distribution) matching the page, OG card. `tools/road_food_index.py` computes everything; `build.py` passes it its trip plans | Press and answer engines link and quote data pages, not apps | `verify.py` recomputes independently and requires: the CSVs byte-equal, every finding sentence in the page text, every shown chain/interstate/state row, each interstate's count = its `/along/` page, each drive's gap = its `/trip/` page, Dataset name = h1, description = meta, dateModified = data date, distributions exist, sitemap, publish.py. 11 mutations caught |
| 2 | **`/llms.txt`**, generated by `build.py`: what the app does (and does not: no charge modelling, no live availability), key pages, data sources and limits, privacy, the index's findings and a citation line. In publish.py FILES; linked from nowhere | AI answer-engine hygiene (growth #17) | `verify.py`: counts and findings equal the recomputed index, every link resolves, published; 4 mutations caught |
| 3 | **`/in/<city>/`** for `data/metros.json` (118 curated metros: roughly the 2020 Census ranking plus a few trip destinations; downtown coordinates checked against the data's own city centroids). The chargers within 25 mi counted as the app's area view counts them (`planner.hav` ≤ 25 × `MI`; the app opened at `?at=…&r=25` says "79 stops" for Austin, as the page does), the 12 fastest with food a walk away (stop links open the app at the stop in that area), chains, trips starting/ending there, nearby cities, 5–6 data-derived FAQs with FAQPage markup from the same strings. **106 published, 12 skipped**: 9 below 12 stops with food (New Orleans 8, El Paso 8, Myrtle Beach 8, Anchorage 2, Santa Barbara 10, Baton Rouge, Wichita, Fayetteville, Lexington 11) and 3 within 25 mi of a larger metro (New Haven, Springfield MA, Durham). Index `/in/` by region; 2,369 chain×state pages list their state's cities; all 152 trip pages link their end cities; one shared OG card | People search "[city] EV chargers", not chain×state (growth #11) | `verify.py` recounts every city from metros.json + data.js: counts, map link, first card is the fastest, in index and sitemap, not noindexed, FAQ markup = visible FAQ, skipped metros have no page, near/trip links. 10 mutations caught |
| 4 | Footer of every generated page links Road Food Index and Cities; About (web only) links both; trip, along and near indexes link them; each `/along/` page states its index rank ("I-5 ranks 1st of 30 interstates for food: 90.4%…"). robots.txt unchanged | Discoverability and internal links to the new pages | `verify.py`: footer on all ~3,100 generated pages, About links, each index's own link (not the footer's), along rank = recomputed rank; 9 mutations caught |

Sitemap 1,993 → 2,101 URLs (+1 index, +106 cities, +1 city index), every one with lastmod. Build 9 s → ~12 s; `verify.py` +~4 s.

Not done / noted: no per-city OG cards (106 × ~150 KB; one shared card instead). Dataset JSON-LD carries no `license` (OSM-derived data is ODbL; the page and llms.txt credit it, but choosing a license for the CSVs is the owner's call). Found in passing, not changed: the shared stylesheet has a stray `}` after `h2+p,h2+.lead{…}` and an unclosed `@media(max-width:520px){` at its end (in `build.py` CSS), so the `table.trip{…}` rule after the stray brace is dropped by the CSS parser (measured on a trip page at 1280 px: `border-collapse: separate`, `min-width: 0px` instead of `collapse`/`460px`). Fixing it changes every trip table's look, so it is left for a decision; the new styles sit before it and are unaffected.
