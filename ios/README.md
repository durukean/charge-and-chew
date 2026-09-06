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

- **`LocalServer.swift`** — static files over `http://127.0.0.1:<random port>`.
  A `file://` URL is not a trustworthy origin, so on that scheme WebKit kills service
  workers, gives the page an opaque origin that breaks `localStorage`, and blocks `fetch`
  between bundled files. Loopback is trustworthy by definition and gets all of it back.
  Pinned to the loopback interface with a fresh random port each launch; paths are
  `standardized` before a prefix check so a crafted request cannot escape the bundle.
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
