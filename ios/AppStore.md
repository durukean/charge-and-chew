# App Store listing — draft

Everything App Store Connect will ask for, so submission is a copy-paste job once the CarPlay
entitlement lands (or earlier, if we decide to submit without it).

**Name** (30): `Charge & Chew: EV Stops`
**Subtitle** (30): `Fast chargers near good food`
**Category:** Navigation · secondary Travel · **Age:** 4+ · **Price:** Free

**Keywords** (100, comma-separated, no repeats of name/subtitle words):
`ev,charger,charging,tesla,supercharger,road trip,electric car,ihop,restaurants,map,route,walk`

**Description:**
> Charging takes 30 minutes. Might as well spend it somewhere good.
>
> Charge & Chew finds DC fast chargers within a short walk of the restaurants and stores you'd
> actually stop at — IHOP, In-N-Out, Buc-ee's, Starbucks, Target and 85 more chains. 13,000+ US
> chargers, every network, free, no account.
>
> • Search a chain, a place, a kind of shop ("tire shop"), or a whole drive: type "LA to Las Vegas"
>   and see every stop along the route with food a few minutes' walk from the charger.
> • Tap any stop for walk times to each place, hours where known, and one-tap directions.
> • Set your car for connector compatibility and a rough charge time at each stop.
> • Works offline: the charger database is on your phone. Only the map tiles need a signal.
> • Your location never leaves your device. No ads, no tracking.
>
> Charger data: US DOE / NREL. Places: OpenStreetMap. Not affiliated with Tesla or any chain.

**Privacy policy URL:** https://chargeandchew.com/privacy/
**Support URL:** https://chargeandchew.com/support/

**App Privacy (nutrition label)** — answer honestly:
- Location → *Precise Location* → used for App Functionality → **not linked** to identity, not used for tracking.
- Usage Data → *Product Interaction* (anonymous page counts via GoatCounter) → Analytics → **not linked**, not tracking.
- Nothing else collected. No third-party SDKs.

**Review notes:**
> The app bundles its charger database and works without a network; the map tiles are the only
> remote asset. Location is native (CoreLocation) and optional — deny it and search a city instead.
> Directions open Apple Maps or the Google Maps app. CarPlay (EV Charging category) is built and
> ships once the entitlement is granted.

**Screenshots** (6.9" 1320×2868 from an iPhone 17 Pro Max simulator): 1) LA→Las Vegas route with
IHOP stops, 2) a stop popup with walk times, 3) Las Vegas "Any food" list, 4) car set + charge times.
