# App Store screenshots — 6.9" (1320×2868, iPhone 17 Pro Max)

Captured from the simulator on the real build, not mocked. Apple's only required iPhone size.

| file | shows | suggested caption |
|---|---|---|
| `1-route.png` | LA → Las Vegas, 40 stops near IHOP, route drawn | **Plan the drive around food** |
| `2-stop.png` | stop detail: 6 walkable places with times, Directions | **See exactly what's within a walk** |
| `3-overview.png` | national view, 13,798 chargers, Any food / Any store | **13,798 fast chargers. Every network.** |

Re-capture: boot iPhone 17 Pro Max, install a Debug build, `xcrun simctl io <udid> screenshot out.png`.
Captions are added in App Store Connect (or burned in with a `#capBand` overlay like PACK IT).

## 1.0.6 set (`1.0.6/`, new design) — attach when the 1.0.6 App Store version exists

Captured 2026-10-17 on a dedicated iPhone 17 Pro Max simulator ("CC Shots 6.9"), status bar
overridden to 9:41, location Las Vegas, Tesla Model Y set.

| file | shows | suggested caption |
|---|---|---|
| `1-route.png` | LA → Las Vegas route with Suggested breaks (Hesperia mile 74, Baker mile 176) | **Know where to stop on the drive** |
| `2-stop.png` | a Supercharger's card: "23 min here — time for a coffee run at Starbucks" | **Your charge, matched to a meal** |
| `3-nearby.png` | opens on your location: 68 stops in Las Vegas, network marks on the map | **Every fast charger, by what's next door** |

## 1.1.0 set (`1.1.0/`) — on the App Store from 1.1.0

Captured 2026-10-28 on "CC Shots 6.9" from build 45's code, status bar 9:41, location downtown
Las Vegas (36.1672,-115.1485), Tesla Model Y set. Each screen opened with a deep link, not by
typing (simulator text input drops letters): `xcrun simctl openurl <udid> "ccapp://x?q=..."`,
the stop with `ccapp://stop?at=36.1672,-115.1485&stop=166933`.

| file | shows | suggested caption |
|---|---|---|
| `1-route.png` | LA → Las Vegas, 269 mi, Suggested breaks (Hesperia mile 74, Baker mile 176) | **Know where to stop on the drive** |
| `2-stop.png` | Grand Central Parkway Supercharger: "23 min here — time for a coffee run at Starbucks", walk lines | **Your charge, matched to a meal** |
| `3-search.png` | "pharmacy in denver": 43 stops near Walgreens / CVS in Denver | **Search what you need, where you're going** |
| `4-chain.png` | "in n out": 8 stops near In-N-Out around you | **Find your favorite, near you** |
| `5-nearby.png` | opens on your location: 69 stops in Las Vegas | **Every fast charger, by what's next door** |
