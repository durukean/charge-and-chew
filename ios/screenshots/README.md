# App Store screenshots — 6.9" (1320×2868, iPhone 17 Pro Max)

Captured from the simulator on the real build, not mocked. Apple's only required iPhone size.

| file | shows | suggested caption |
|---|---|---|
| `1-route.png` | LA → Las Vegas, 40 stops near IHOP, route drawn | **Plan the drive around food** |
| `2-stop.png` | stop detail: 6 walkable places with times, Directions | **See exactly what's within a walk** |
| `3-overview.png` | national view, 13,798 chargers, Any food / Any store | **13,798 fast chargers. Every network.** |

Re-capture: boot iPhone 17 Pro Max, install a Debug build, `xcrun simctl io <udid> screenshot out.png`.
Captions are added in App Store Connect (or burned in with a `#capBand` overlay like PACK IT).
