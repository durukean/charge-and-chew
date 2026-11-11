#!/usr/bin/env bash
# Every test suite, stopping at the first failure. Use it as the gate before a commit:
#
#   ./check.sh && git commit ...
#
# A loop that printed each suite's result and carried on once let a failing run be committed
# and pushed; this exits non-zero instead.
set -euo pipefail
cd "$(dirname "$0")"
run() { printf '%-28s' "$1"; out=$("${@:2}" 2>&1) || { echo "FAIL"; echo "$out" | tail -25; exit 1; }; echo "ok  ($(echo "$out" | tail -1 | sed 's/^ *//'))"; }
run "verify.py"          python3 verify.py
run "verify_search.py"   python3 verify_search.py
run "verify_hours.py"    python3 verify_hours.py
run "verify_ui.py"       python3 verify_ui.py
# Where searches END UP (a located user, a remembered area, no location), offline. The full
# version needs the internet: node tools/search_audit.mjs
run "search_audit --quick" node tools/search_audit.mjs --quick
# The /trip/ pages' 8 am plan against the app's own breaks card on the same drive, offline
# (the route answered from data/trips.json). Every trip: node tools/trip_plan_check.mjs
run "trip_plan_check --quick" node tools/trip_plan_check.mjs --quick
# The route corridor (app and planner.py) against brute force, northern and southern drives
# at 5/10/25 mi, offline (~5 s).
run "corridor_check.mjs"  node tools/corridor_check.mjs
run "sw_test.mjs"        node sw_test.mjs
run "publish.py"         python3 publish.py
rm -rf _site
echo "all suites passed"
