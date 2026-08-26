# Charge & Chew — brand

## The mark

A filled disc with a **bite** taken out of the top-right edge and a **charging bolt** knocked
out of the middle. One shape carrying both halves of the name. The bite is one deep crater
with two small tooth nicks at its rim — reworked 2026-08-25 after the first version (three
shallow spread scallops) read as a cog, not a bite. Depth is what sells the bite; the nicks
keep it from being the Apple silhouette.

Canonical file: `brand/logo.svg` (also `favicon.svg` at the site root).

## Colour

The gradient runs **electric green → amber**: charge on one side, food on the other.

| Token | Light | Dark | Notes |
|---|---|---|---|
| Logo gradient | `#16a34a` → `#f59e0b` | same | Decorative only — no contrast requirement |
| UI accent | `#15803d` | `#4ade80` | 5.0:1 on white / 10:1 on dark |
| Wordmark "Charge" | `#16a34a` | `#4ade80` | |
| Wordmark "Chew" | `#f59e0b` | `#fbbf24` | Display size only |

**The logo green is not the UI green.** `#16a34a` is only 3.30:1 on white, so it fails as
button or link colour. The UI uses the darker `#15803d`. Don't collapse them into one token.

Amber is decorative. `#f59e0b` is 2.15:1 on white — never use it for body text on a light
background; use `#b45309` if amber text is ever needed there.

## Typeface

Inter throughout — 800/900 for the wordmark and headings, 400–700 for UI. Numbers in tables
and badges use JetBrains Mono so columns line up.

## Assets

| File | Use |
|---|---|
| `brand/logo.svg` | Master |
| `favicon.svg` | Browser tab (modern) |
| `favicon.ico` | Browser tab fallback — 16/32/48 PNG-in-ICO, packed by the python snippet in git history |
| `icon-192.png` / `icon-512.png` | PWA install |
| `icon-maskable-512.png` | Android adaptive (no rounding — the OS masks it) |
| `apple-touch-icon.png` | iOS home screen |
| `og.png` | Link previews — rebuild from `data/og-source.html` |

Regenerate the OG image after a copy or stat change:

```
python3 -m http.server 8642   # from the repo root
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
  --screenshot=og.png --window-size=1200,630 --hide-scrollbars \
  http://127.0.0.1:8642/data/og-source.html
```

## Explorations

`brand/concepts.png`, `brand/refined.png`, `brand/color.png` record what was tried and
rejected: shallow scallop bites that read as a cog (`bite.png`/`bite2.png` compare the fixes), a fork/bolt hybrid that read as a whisk, a plain bolt-in-a-circle that looked like
every other EV app, a hard-split two-tone whose seam looked accidental at 16px, and
blue→amber / teal→orange gradients that went muddy through the middle.
