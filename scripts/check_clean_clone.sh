#!/bin/sh
# The pre-publication gate (DEFECTS #75): what a stranger's first ten
# minutes look like. Clones this repo into a scratch directory with no
# data/ and no .env, installs both toolchains, and runs every command the
# README names. Any test FAILURE fails the gate; skips are expected, and
# the honest ceiling for a repo whose data cannot be published.
#
# Run it before anything is made public:  sh scripts/check_clean_clone.sh
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
echo "clean clone into $WORK"
git clone -q "$ROOT" "$WORK/clone"
cd "$WORK/clone"
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
echo "--- make test (tiers 1 and 2, no data, no .env)"
make test
echo "--- make eval (tier 3)"
make eval
echo "--- viewer"
cd viewer && npm install --silent && npx vitest run --silent && npx tsc --noEmit
echo "CLEAN CLONE GATE PASSED"
