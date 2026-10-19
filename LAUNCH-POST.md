# Launch post drafts

Numbers are from the 2026-10-19 data. Mention the iPhone app only after 1.0.5 is released.

Post these yourself from your own account — communities react badly to posts that
read as marketing, and they react well to "I built this because it annoyed me."

---

## r/TeslaMotors · r/electricvehicles · r/TeslaLounge

**Title:** I mapped every US EV fast charger — all networks — against 90 restaurant and store chains

**Body:**

Planning a road trip, I kept hitting the same wall: I can see where the Superchargers
are, but not which ones have something I actually want next to them. The Tesla app shows
amenities one pin at a time, and every other tool filters by category ("dining nearby"),
never by the thing I'm actually thinking — "is there an IHOP at this stop?"

So I built the reverse lookup: pick a chain, see only the Superchargers within a
10-minute walk of it.

https://chargeandchew.com

A few things that surprised me once the data was in:

- 11,757 of 14,239 US public DC fast chargers (83%) — Tesla, Electrify America, EVgo,
  ChargePoint, IONNA, Rivian and more — have at least one of these 90 chains within an 800 m walk
- Set your car and it shows connector compatibility (native / adapter) and an estimated
  charge time at each stop, so you can match the stop to how long you'll actually be there
- 4,611 chargers have a Starbucks that close; only 68 have a Buc-ee's
- Long drives suggest where to break and flag the longest stretch without a fast charger

You can also drop a pin anywhere to see what's around that area, or put in a route
(say Dallas → Houston) and it lists every matching stop in driving order — that one
turned up the two Buc-ee's on I-45 (Ennis and Madisonville) that have Superchargers.

It's free, no ads, no login. Works in the browser (including the car's), and there's an iPhone app. Charger data is the US DOE / NREL public database and
chain locations are from OpenStreetMap, so coverage is roughly 90-95% per chain — a missing chain
doesn't guarantee it isn't there. Walk times are straight-line estimates, so check the
real walk before trusting them.

Happy to add chains people actually want. What am I missing?

---

## Tesla Motors Club (forum)

**Title:** Built a free tool: find Superchargers by the chain next to them (IHOP, Buc-ee's, Walmart…)

**Body:**

There are threads here going back years of people cross-referencing supercharge.info
against Google Maps to figure out which stops have real food nearby. I finally just
built the lookup:

https://chargeandchew.com

Pick one or more of 90 chains and the map shows only DC fast chargers (any network) with that chain
within a 10-minute walk, with the walk time, stall count and power for each. There's a
route mode that lists matching stops in driving order, and you can drop a pin to search
any area.

Data: US DOE / NREL for chargers (all networks), OpenStreetMap for chain locations, rematched
weekly. Free, no account, no ads. Tell me which chains to add.

---

## Short version (X / Bluesky / Threads)

Every US EV fast charger — all networks — matched against 90 restaurant & store chains within a 10-minute walk.

Want a stop with an IHOP? A Buc-ee's? A Walmart to kill 20 minutes in? Pick the chain,
get the chargers.

83% have at least one. Set your car for charge-time + connector fit. Free, no login:
https://chargeandchew.com

---

## Notes on posting

- Post to ONE subreddit first and see how it lands before doing the rest; simultaneous
  cross-posting looks like spam.
- Reply to comments quickly for the first couple of hours — that's what drives ranking.
- Requests for new chains are the best kind of feedback: adding one is a one-line change
  in `data/fetch_pois.py`.
- Don't editorialize about Tesla; keep it about the tool.
