#!/usr/bin/env bash
# Convert samples/contracts-synthetic/*.md to PDF for ingestion testing.
#
# Output: samples/contracts-synthetic/pdf/*.pdf
#
# Requires: pandoc (>= 2.x) and either weasyprint or wkhtmltopdf as a PDF
# engine. Install via:
#   macOS:  brew install pandoc weasyprint
#   Debian: apt install pandoc weasyprint
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC="$ROOT/samples/contracts-synthetic"
OUT="$SRC/pdf"

command -v pandoc >/dev/null || { echo "pandoc not installed" >&2; exit 1; }

mkdir -p "$OUT"
count=0
for md in "$SRC"/*.md; do
  base=$(basename "$md" .md)
  out="$OUT/$base.pdf"
  echo "→ $out"
  pandoc "$md" \
    -o "$out" \
    --pdf-engine=weasyprint \
    --metadata title="$base"
  count=$((count + 1))
done

echo "Built $count PDFs in $OUT"
