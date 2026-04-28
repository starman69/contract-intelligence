#!/usr/bin/env bash
# Bundle a Function App for deployment.
#
# Copies src/shared/ into the function folder so its modules are importable at
# runtime, then prints the path. Use the printed path with `func azure
# functionapp publish` or zip it for WEBSITE_RUN_FROM_PACKAGE.
#
# Usage:  scripts/package-functions.sh ingestion
set -euo pipefail

FN="${1:?missing function name (e.g. ingestion)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_FN="$ROOT/src/functions/$FN"
SHARED="$ROOT/src/shared"

[ -d "$SRC_FN" ] || { echo "no function at $SRC_FN" >&2; exit 1; }
[ -d "$SHARED" ] || { echo "no shared at $SHARED" >&2; exit 1; }

OUT="$(mktemp -d)/$FN"
mkdir -p "$OUT"
cp -R "$SRC_FN"/. "$OUT/"
cp -R "$SHARED" "$OUT/shared"

find "$OUT" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$OUT" -name 'local.settings.json' -delete

echo "Bundled function package: $OUT"
echo "Deploy:  cd '$OUT' && func azure functionapp publish <function-app-name>"
