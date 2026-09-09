# Charge & Chew — iOS

A native iOS app around the same web app that runs chargeandchew.com. Not a browser pointed
at the site: the whole app is **bundled in the binary** and served from a loopback server, so
it opens and works with no network at all.

## Status — verified, not guessed

| | |
|---|---|
| Builds | ✅ `xcodebuild` clean, Xcode 26.6 |
| Runs on simulator | ✅ iPhone 17 Pro Max, launches to the real app |
| Data loads offline from bundle | ✅ 13,733 chargers, no network needed |
| Native location | ✅ permission sheet → CoreLocation fix → map moved, "420 stops within 25 mi of Los Angeles" |
| Run on a physical device | ❌ never tried — needs a signing team |
| Submitted to App Review | ❌ no |
| CarPlay | ❌ not built (see below) |

Anything not ticked above has not been done. Do not assume it works.

## Build and run

```bash
./sync-web.sh                                        # copy the web app into the bundle
xcodegen generate --spec project.yml --project .     # regenerate ChargeAndChew.xcodeproj
open ChargeAndChew.xcodeproj
```

`sync-web.sh` must be re-run after **every** change to `index.html`, `data.js` or `vendor/`.
Nothing does it automatically, and a stale bundle looks exactly like a working one.

## How it fits together

- **`AppSchemeHandler.swift`** — serves the bundle to WKWebView as `chargeandchew://app/…`
  through a `WKURLSchemeHandler`. No socket, no port. This replaced a loopback HTTP
  server, which worked until its fixed port was taken (two simulators on one Mac was
  enough): it fell back to a random port, the origin changed, and favourites, the saved
  car and every preference silently vanished — web storage is per-origin and the origin
  includes the port. A scheme has no port, so the origin is stable for the life of the
  install. Paths are `standardized` before a prefix check so a crafted request cannot
  escape the bundle. Custom schemes are not "secure contexts", but nothing here needs
  one: the service worker is skipped, geolocation and sharing are bridged natively.
- **`NativeBridge.swift`** — replaces `navigator.geolocation` at document start with a shim
  that calls CoreLocation. WKWebView has never given a page reliable geolocation without
  private API, and doing it natively also puts our own usage string on the system sheet at
  the moment the user taps locate.
- **`DataUpdater.swift`** — on launch, asks the site whether `data.js` is newer than the
  bundled copy and, if so, writes it to an overlay directory the server checks first. Every
  failure path is silent and leaves the bundled copy alone: an app that works offline must
  never be worse off for having tried the network.
- **`WebViewController.swift`** — hosts the web view, holds the splash until first paint,
  and sends every non-loopback URL to Safari.

## Audit findings, fixed (2026-09-06)

Found by using the app on the simulator, not by reading it:

- **Storage was wiped on every launch.** The server took a random port, the origin
  includes the port, and web storage is per-origin. First fix: a fixed port. Real fix
  (build 6): no port at all — see `AppSchemeHandler.swift`.
- **Share sent a loopback URL.** `location.href` inside the shell is `http://127.0.0.1:…`,
  which means nothing to anyone. The page now builds `https://chargeandchew.com/?…` and
  hands it to the native share sheet (`shareUrl()` / `native('share')`).
- **The popup fell off the right edge** on stops whose walkable places sit to the east.
  `fitBounds` pads 40 px a side while the popup is ~340 px wide. `keepPopupOnScreen()`
  measures the popup after the fit and pans by exactly the overflow.
- **The intro card was cut off by the results sheet.** It was `position:absolute` inside
  `#mapWrap` and only ever covered the map. Now `position:fixed`.
- **Keyboard accessory bar (▲ ▼ ✓)** — the most recognisable "web page in a box" tell.
  `AppWebView` swaps WebKit's content view for a runtime subclass whose
  `inputAccessoryView` is nil, the same technique Capacitor and Cordova ship.
- **Site pages 404'd.** `/near/…`, `/along/…`, `/trip/…` are not bundled; any main-frame
  navigation to a loopback path other than `/index.html` now opens the real site in an
  in-app `SFSafariViewController`.
- **Directions** hand off to the Google Maps app when installed; otherwise **Apple Maps**
  (`maps://?daddr=…&dirflg=w`), never Google's mobile-web "install our app" page.
- Status bar follows the page's solar theme (`native('theme')`), not the system setting —
  otherwise the clock is black-on-black every evening for anyone in light mode.
- Analytics script was protocol-relative and resolved to `http://` on the loopback origin,
  which ATS refuses, so the app was invisible in GoatCounter. Now `https://`.
- Service worker skipped (`!NATIVE`), install nudge suppressed (`installed()` is true),
  long-press text callouts disabled on UI chrome, haptic tick on state-changing taps.

## CarPlay (2026-09-09): built, entitlement pending

The one part of the product that had to be built twice, natively: CarPlay only renders
Apple's templates, so the web app cannot appear on the car screen.

- `CarPlaySceneDelegate.swift` — a `CPPointOfInterestTemplate` of the nearest fast
  chargers **that have somewhere to eat within a walk**, nearest first, re-queried when the
  driver pans the car map. Each POI: distance · kW · stalls, up to three walkable places
  with minutes, and a **Directions** button that hands off to Apple Maps.
- `ChargerStore.swift` — reads the *same* `data.js` the web view uses (overlay copy if a
  refresh landed, bundled otherwise), unescaping exactly the two things build_data.py
  escapes (`\` and `'`). The car never shows older chargers than the phone.
- Scenes came back for CarPlay's sake (`PhoneSceneDelegate`, `CarPlaySceneDelegate`), but
  the delegate classes are assigned **by type** in `AppDelegate.configurationForConnecting`
  — never by the Info.plist string lookup that silently failed earlier.
- `CarPlay.entitlements` (`com.apple.developer.carplay-charging`) is applied to **Debug
  (simulator) builds only** via project.yml. A Release build carrying an ungranted
  entitlement fails to sign, so TestFlight builds stay CarPlay-free until Apple grants it.

**To see it:** in Simulator.app, I/O → External Displays → CarPlay. The scene logs
`carplay: connected` and `carplay: N chargers with food near …` to the boot log; capture
the car screen with `xcrun simctl io <udid> screenshot --display=external out.png`.

**Entitlement request** (developer.apple.com/contact/carplay/, Apple account holder only):
category **EV Charging**; the app locates DC fast chargers and shows which have food or
shopping within a short walk, with directions handed to Apple Maps; no in-car video, no
messaging, no audio. Apple typically answers in days to a few weeks.

## Phone layout (2026-09-07): the sheet is the control surface

A real-phone screenshot showed the main screen still busy after the button cleanup: the
phone layout was the desktop layout squeezed — four rows of controls floating over a ~300 px
map. Phones now get what Apple Maps and Google Maps do: **one search pill on top, the map
full-bleed, everything else in the bottom sheet.**

- `relayout()` in index.html physically moves `#carBar`, `#chiprow` and `#centerCard` into
  the sheet head on narrow screens and back on wide ones (`#app.phone` scopes the CSS).
- The car reads as two chips at the head of the chip row (the desktop tag's `flex:1` +
  ellipsis collapsed it to a lone emoji inside a scrolling row — fixed with `flex:0 0 auto`).
- No legend button on phones; the same network list lives in Filters (`#filtNetList`).
- Peek height shows title + where + chips, so the chips are always one glance away.
- Map buttons: route + locate, bottom-right. Theme is in Filters; pin-drop is press-and-hold.

## Walkthrough findings, fixed (2026-09-06, second pass)

Every control, exercised on the simulator one at a time:

- **Return did nothing in the route fields.** The phone keyboard now says "next" / "go"
  (`enterkeyhint`) and does it. `autocorrect` is off on every place field — iOS rewrote
  "Barstow" as "Bar stow". Route fields show the geocoded name ("Los Angeles, CA"), not "la".
- **Sheet at full height:** the map is ~170 px and its floating controls landed on the search
  bar. Hidden at `sheet-full`. Resizing the sheet fired `moveend` and popped "Search this
  area"; suppressed for 900 ms after a sheet change.
- **FAB stack vs. overlay:** the stack was anchored to the map bottom and the overlay grew
  from the top (car bar, centre card, route panel); they met and the stack sat on the chip
  row. It now hangs off the overlay's bottom edge (`--ovh` from a ResizeObserver), clamped
  to the map. Two wrong attempts: the rule landed in the desktop media block; then the
  clamp used 46 px buttons when phones use 54 px.
- **Route panel open for editing:** FABs hidden (collision) — which removed the only way to
  close it, so the panel has its own close button.
- **Failed live lookup** was a three-second toast; the failure and a Try again button now
  sit where the results were going to be.
- **Location denied:** iOS never shows the sheet again, so the shell offers Open Settings on
  the *next* tap (not on the denial itself).
- **Network legend rows** looked tappable and did nothing; they now narrow to that network
  (the search's `netPick`), and the legend collapses after a pick.
- **Empty state** rendered its filter label as a block and "Show them" as an unstyled
  button; fixed.
- **"+ All 90 chains"** took four flings to reach; it is sticky at the row's right edge.
- **Clearing the area** left the map on an empty patch of desert under a list that now
  started in Illinois; the map refits to the new scope.
- **Phone-side log:** JS errors, unhandled rejections and every toast are posted to the
  shell and land in `Documents/cc-boot.log` (debug builds). That is how a "tire shop" miss
  was diagnosed as a transient Overpass non-answer rather than a bug.

## Traps already paid for

- **XcodeGen overwrites `Info.plist`.** `info.path` means "generate this file here". A
  hand-written plist was silently replaced, losing the scene manifest — the app then
  launched, stayed running, connected no scene, and showed a **black screen with not one
  line of our code executing and nothing in the log**. Every plist key lives in
  `project.yml` under `info.properties`. Never hand-edit `ChargeAndChew/Info.plist`.
- **No UIScene manifest, on purpose.** It resolves its delegate by string through the
  ObjC runtime, and under Xcode 26's debug-dylib layout that lookup silently failed here.
  One window, created in `AppDelegate`, removes a failure mode that is invisible when it
  happens.
- **`NSLog` and `print` were both unreadable** from outside the simulator, which turned a
  blank screen into guesswork. `Diag.swift` appends to `Documents/cc-boot.log`, readable via
  `xcrun simctl get_app_container <udid> com.durukean.chargeandchew data`. Debug builds only.
- **The app icon must have no alpha channel.** `icon-512.png` has one; the 1024 icon is
  flattened onto opaque white by rendering it in headless Chrome (there is no PIL or
  ImageMagick on this machine, and `sips` will not drop an alpha channel).

## Honest limits

- **Offline is not total.** Charger data, search, filters and the whole result list work with
  no signal. Basemap **tiles** come from Esri over the network, so offline you get the data
  on an empty background. Bundling tiles for the US is not feasible at any sane size.
- **Guideline 4.2 is a real risk.** Apple rejects apps that are a website in a web view.
  The offline bundle and native location are a genuine start, but the honest defence is
  **CarPlay** — Apple supports EV charging as a first-class CarPlay category
  (`com.apple.developer.carplay-charging`), which needs a separate entitlement request and
  native `CPPointOfInterestTemplate` UI. The web app cannot render on the car screen. That
  is the next real piece of work, and it is a project, not an afternoon.

## Shipping a build

```bash
./release.sh              # sync, generate, bump build, archive, export, verify, upload
./release.sh --no-upload  # stop at export/ChargeAndChew.ipa
```

- App Store Connect app **6809134093**, bundle `com.chargeandchew.app` (bundleId resource
  `ZHDTTDU73N`), SKU `chargeandchew001`, team `T37B6B6S7K`.
- **`POST /v1/apps` is refused** — "resource 'apps' does not allow CREATE". The first app
  record must be made in the web UI; everything after that is API-drivable.
- **Export must NOT pass `-authenticationKey*`.** With the ASC API key it fails "Cloud
  signing permission error / No profiles were found" — the logged-in Xcode session has
  signing rights the key does not. Archive is happy either way.
- **The ASC New App form is React-controlled**: programmatic field values are reset on the
  next render, and its native `<select>`s need click-then-type-ahead. Type it like a person.
- Internal beta groups **reject** `POST /betaGroups/{id}/relationships/builds` ("Builds
  cannot be assigned to this internal group"). Internal testers get every processed build
  automatically; the only gate that matters is export compliance, which
  `ITSAppUsesNonExemptEncryption: false` in project.yml now answers at build time.
