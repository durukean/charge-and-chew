#!/usr/bin/env bash
# Build, sign and upload a TestFlight build.
#
#   ./release.sh              # archive + export + upload
#   ./release.sh --no-upload  # stop after producing export/ChargeAndChew.ipa
#
# Prerequisite that this script CANNOT do for you: the app record must already exist in
# App Store Connect. `POST /v1/apps` is rejected ("resource 'apps' does not allow CREATE"),
# so the first one has to be made in the web UI. Without it the upload fails with
# "Cannot determine the Apple ID from Bundle ID".
set -euo pipefail
cd "$(dirname "$0")"

TEAM=T37B6B6S7K
KEY_ID=63U8C63MW7
ISSUER=b8ade631-2e77-4eb4-81f9-2bd3c20ca355

./sync-web.sh
xcodegen generate --spec project.yml --project .

# Bump the build number every run: App Store Connect rejects a duplicate CFBundleVersion,
# and finding that out at the end of an upload is a slow way to learn it.
BUILD=$(( $(grep -o 'CURRENT_PROJECT_VERSION: "[0-9]*"' project.yml | grep -o '[0-9]*') + 1 ))
sed -i '' "s/CURRENT_PROJECT_VERSION: \"[0-9]*\"/CURRENT_PROJECT_VERSION: \"$BUILD\"/" project.yml
xcodegen generate --spec project.yml --project .
echo "==> build $BUILD"

rm -rf ChargeAndChew.xcarchive export
xcodebuild -project ChargeAndChew.xcodeproj -scheme ChargeAndChew \
  -sdk iphoneos -configuration Release -archivePath ChargeAndChew.xcarchive \
  -allowProvisioningUpdates archive

# Deliberately NO -authenticationKey* on export. With the API key, export fails with
# "Cloud signing permission error / No profiles for 'com.chargeandchew.app' were found";
# the logged-in Xcode session has the signing rights the key does not.
xcodebuild -exportArchive -archivePath ChargeAndChew.xcarchive \
  -exportOptionsPlist ExportOptions.plist -exportPath export -allowProvisioningUpdates

# The web app is the whole product; an IPA missing it builds, signs and installs fine and
# is then a blank screen on the device.
unzip -l export/ChargeAndChew.ipa | grep -q 'Web/data.js' || { echo "FATAL: data.js missing from IPA"; exit 1; }
unzip -l export/ChargeAndChew.ipa | grep -q 'Web/index.html' || { echo "FATAL: index.html missing from IPA"; exit 1; }
echo "==> IPA ok: $(du -h export/ChargeAndChew.ipa | cut -f1)"

[ "${1:-}" = "--no-upload" ] && { echo "stopping before upload"; exit 0; }

xcrun altool --upload-app -f export/ChargeAndChew.ipa -t ios \
  --apiKey "$KEY_ID" --apiIssuer "$ISSUER"
echo "==> uploaded build $BUILD; it appears in TestFlight after Apple finishes processing"
