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

## 1.1.1 set (`1.1.1/`): captioned, meal plan first

Captured 2026-11-14 on "CC Shots 6.9" from build 46's code (main `ec4e03a37c`), status bar 9:41
(`simctl status_bar override`), location downtown Las Vegas, Tesla Model Y set, light theme forced
(`cc_theme=light` in the app's WebKit localStorage, since the page goes dark after sunset). Each
screen opened with a deep link (`ccapp://plan?from=Los%20Angeles&to=Las%20Vegas&leave=0800`,
`ccapp://x?q=thanksgiving%20drive%20la%20to%20sf`,
`ccapp://plan?from=Los%20Angeles&to=San%20Francisco&kids=1&leave=0800`,
`ccapp://x?at=36.1450,-115.1700&r=10`), then sheet drags and taps. Press HOME and relaunch from the
home screen before capturing, or iOS shows a "◀ <app>" back breadcrumb in the status bar.
Captions burned in: raw capture scaled to 1100 px in a rounded frame on charge green (#0f7a43),
Bricolage Grotesque headline + Inter subline, rendered by headless Chrome at 1320×2868
(Chrome's PNG has no alpha channel; checked with `sips -g hasAlpha`).

| file | shows | caption |
|---|---|---|
| `1-plan.png` | LA → Las Vegas, Suggested breaks: 10:05 am Barstow, 12:30 pm **Lunch** Primm (Carl's Jr.), Send plan, Add 2 stops to calendar | **Lunch, planned around your drive** |
| `2-rows.png` | route rows: Hesperia, Barstow ×2, Baker; food chips with walk times, restroom likely | **Food first, then the charger** |
| `3-stop.png` | Barstow Supercharger card: 23 min, quick meal at Taco Bell, walk lines, "Break ~10:05 am · on your plan · Add to calendar" | **Your charge, matched to a meal** |
| `4-search.png` | "thanksgiving drive la to sf": LA → SF, Leaving **Thanksgiving** 8:00 am, breaks | **Type it the way you'd say it** |
| `5-kids.png` | LA → SF with Good for kids: playground 3 min / 2 min on each break | **Good for kids** |
| `6-map.png` | Las Vegas, 53 stops within 10 mi, network marks | **Every fast charger, by what's next door** |
