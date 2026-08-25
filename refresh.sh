#!/bin/bash
# Charge & Chew — monthly data refresh.
# Re-pulls Superchargers + chain locations, rebuilds pages, commits and pushes.
set -euo pipefail
cd "$(dirname "$0")"
echo "[$(date)] refresh starting"

# 1. fresh all-network charger list (chain POIs stay cached in data/pois.json)
python3 data/fetch_chargers.py

# 2. rematch + rebuild
python3 data/build_data.py
python3 build.py --base https://chargeandchew.com
python3 verify.py

# 3. publish only if something actually changed
if [[ -n "$(git status --porcelain)" ]]; then
  git add -A
  git -c user.name="durukan" -c user.email="bycixix@gmail.com" \
      commit -qm "Data refresh $(date +%Y-%m-%d)"
  git push -q origin main
  echo "[$(date)] pushed changes"
else
  echo "[$(date)] no changes"
fi
