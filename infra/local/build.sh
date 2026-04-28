#!/usr/bin/env bash
# Build the web frontend for the local docker-compose stack.
#
# (No more function bundling / pip install pre-step — the api and ingest
# services use a shared image built from Dockerfile.app and mount src/ live.)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "==> Building web (npm run build)"
(
  cd "$ROOT/src/web"
  if [ ! -d node_modules ]; then
    npm install --silent
  fi
  npm run build
)

echo
echo "Done. Now:"
echo "  cd $SCRIPT_DIR"
echo "  docker compose up -d"
echo "  docker compose logs -f bootstrap"
