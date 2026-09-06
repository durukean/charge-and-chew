#!/usr/bin/env bash
# Copy the shipping web app into the iOS bundle. No build step does this automatically --
# run it after every change to index.html, data.js or vendor/, and before any Xcode build.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
DEST="$HERE/ChargeAndChew/Web"
rm -rf "$DEST"; mkdir -p "$DEST"
# Only what the app itself needs at runtime. The 2,978 SEO pages are for Google, not the
# app, and bundling them would add megabytes nobody opens.
cp "$ROOT/index.html" "$ROOT/data.js" "$ROOT/manifest.json" "$DEST/"
cp "$ROOT/favicon.svg" "$ROOT/icon-192.png" "$ROOT/icon-512.png" "$ROOT/apple-touch-icon.png" "$DEST/"
cp -R "$ROOT/vendor" "$DEST/vendor"
# The service worker is pointless here: every asset is already local, and a stale SW cache
# on top of a bundled app is a way to serve last month's data forever.
echo "synced -> $DEST ($(du -sh "$DEST" | cut -f1))"
