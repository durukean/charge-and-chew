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
run "sw_test.mjs"        node sw_test.mjs
run "publish.py"         python3 publish.py
rm -rf _site
echo "all suites passed"
