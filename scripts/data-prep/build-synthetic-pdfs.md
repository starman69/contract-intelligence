# Building the Synthetic Contract PDFs

Document Intelligence (`prebuilt-layout`) accepts PDF, JPEG, PNG, BMP, TIFF, HEIF, DOCX, XLSX, PPTX, and HTML — but the corpus we ship in `samples/contracts-synthetic/` is Markdown, so it has to be converted before the ingestion Function will pick it up. This guide covers the WSL2 (Ubuntu/Debian) install path used by the wrapper script `build-synthetic-pdfs.sh`.

## Tooling

| Tool | Role | Why this one |
|---|---|---|
| **pandoc** | Markdown → HTML | Universal converter; deb package; handles our headings, tables, signature blocks cleanly |
| **WeasyPrint** | HTML → PDF | Pure-Python (CFFI bindings); produces print-quality output without a headless browser or LaTeX install; small footprint (~50 MB w/ deps); MIT-licensed |

Alternatives are listed at the end; for the POC corpus this combination is the smallest install that produces typographically correct output.

## WSL2 install (Ubuntu / Debian)

WSL2 distros use the upstream Ubuntu/Debian package archives, so the install is identical to bare-metal Ubuntu. Run inside the WSL2 shell, not PowerShell.

```bash
sudo apt update
sudo apt install -y \
  pandoc \
  pipx \
  libpango-1.0-0 libpangoft2-1.0-0 \
  libcairo2 libffi-dev libjpeg-dev \
  shared-mime-info fonts-dejavu-core
pipx ensurepath
exec "$SHELL" -l           # reload PATH so pipx-installed binaries are discoverable
pipx install weasyprint
```

**Notes**

- `libpango*` + `libcairo2` are WeasyPrint's native dependencies on Linux. WeasyPrint 60+ bundles some of this internally but the system libs make the install reliable across distros.
- `pipx` is preferred over a global `pip install` so WeasyPrint lives in its own venv and won't clash with system Python or the project's `requirements.txt`.
- `fonts-dejavu-core` ensures a consistent default font; without it WeasyPrint may fall back to a font that doesn't render some glyphs.
- If `pipx` isn't available in your distro's archive (older Ubuntu), `python3 -m pip install --user weasyprint` works as a fallback. You may need to add `~/.local/bin` to `PATH`.

## Verify

```bash
pandoc --version | head -n1       # expect: pandoc 2.x or 3.x
weasyprint --version              # expect: WeasyPrint 60+
```

If `weasyprint --version` reports missing libraries (e.g. `OSError: cannot load library 'libpango-1.0.so.0'`), re-check the apt install above.

## Run the build

From the repo root:

```bash
./scripts/data-prep/build-synthetic-pdfs.sh
```

The script iterates `samples/contracts-synthetic/*.md`, calls pandoc on each with `--pdf-engine=weasyprint`, and writes to `samples/contracts-synthetic/pdf/`. It exits non-zero on the first failure (so wrap in a `for` loop yourself if you want to keep going through errors).

Expected output:

```
→ samples/contracts-synthetic/pdf/clean-001-supplier-services.pdf
→ samples/contracts-synthetic/pdf/clean-002-saas-license.pdf
…
Built 12 PDFs in samples/contracts-synthetic/pdf
```

## Inspect

WSL2 can open the PDFs with the host Windows reader by path-translating with `wslview`:

```bash
sudo apt install -y wslu                      # one-time; provides wslview
wslview samples/contracts-synthetic/pdf/clean-001-supplier-services.pdf
```

Or open Explorer directly:

```bash
explorer.exe $(wslpath -w samples/contracts-synthetic/pdf)
```

Quick page-count sanity check (most contracts should be 2–3 pages):

```bash
sudo apt install -y poppler-utils             # one-time; provides pdfinfo
for pdf in samples/contracts-synthetic/pdf/*.pdf; do
  printf '%s\t%s\n' "$(basename "$pdf")" "$(pdfinfo "$pdf" | awk '/^Pages:/ {print $2}')"
done
```

## Upload to ingestion

Once Bicep is deployed and the storage account exists, the path layout in `docs/poc/02-data-model.md` is `raw/contracts/{contractId}/{version}/{filename}.pdf`. Use a stable contract id from the manifest (the manifest `id` field works for testing) and version `1`:

```bash
ACCOUNT="<storage-account-name>"
for pdf in samples/contracts-synthetic/pdf/*.pdf; do
  base=$(basename "$pdf" .pdf)
  az storage blob upload \
    --account-name "$ACCOUNT" --auth-mode login \
    --container-name raw \
    --name "contracts/syn-$base/1/$base.pdf" \
    --file "$pdf"
done
```

Each upload triggers Event Grid → IngestionTrigger.

## Alternatives

You don't have to use WeasyPrint. The script's `--pdf-engine` flag accepts any pandoc-supported engine.

| Engine | Install | Pros | Cons |
|---|---|---|---|
| **WeasyPrint** *(default)* | `pipx install weasyprint` + apt libs | Small (~50 MB), pure Python, fast | CSS-driven layout, less typographic finesse than LaTeX |
| **wkhtmltopdf** | `sudo apt install wkhtmltopdf` | Single binary, simple | Upstream archived; CSS support frozen at WebKit 2014 |
| **tectonic** (modern LaTeX) | `cargo install tectonic` *or* `curl -fsSL https://drop-sh.fullyjustified.net \| sh` | Self-bootstrapping LaTeX, downloads packages on demand | Bigger first run; LaTeX-styled output |
| **TeX Live (xelatex)** | `sudo apt install texlive-xetex` | Maximum typography control | ~3 GB install |
| **Headless Chrome via `md-to-pdf`** | `npm i -g md-to-pdf` | Identical to web rendering | Pulls Chromium; heavy |

To switch: edit one line in `build-synthetic-pdfs.sh`:

```bash
pandoc "$md" -o "$out" --pdf-engine=tectonic --metadata title="$base"
```

### Docker (no host install)

If you'd rather not install anything on WSL2:

```bash
docker run --rm -v "$PWD/samples/contracts-synthetic:/data" pandoc/latex:3.5 \
  /data/clean-001-supplier-services.md \
  -o /data/pdf/clean-001-supplier-services.pdf
```

The `pandoc/latex` image carries pdflatex, so styling differs from the WeasyPrint output but the content is identical. Loop in shell for batch:

```bash
mkdir -p samples/contracts-synthetic/pdf
for md in samples/contracts-synthetic/*.md; do
  base=$(basename "$md" .md)
  docker run --rm -v "$PWD/samples/contracts-synthetic:/data" pandoc/latex:3.5 \
    "/data/$base.md" -o "/data/pdf/$base.pdf"
done
```

WSL2 needs Docker Desktop (with WSL2 integration) or a native dockerd inside WSL2 for this to work.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `weasyprint: command not found` after `pipx install` | `~/.local/bin` not on `PATH` | `pipx ensurepath && exec "$SHELL" -l` |
| `OSError: cannot load library 'libpango-1.0.so.0'` | System libs missing | Re-run the `apt install` block above |
| PDF page is blank or table cells overflow | Wide tables (e.g. signature block) overflow A4 width | Edit the source markdown to use shorter labels, or pass `--variable=papersize:letter` to pandoc |
| Garbled glyphs (□ instead of letters) | Font not installed | `sudo apt install fonts-dejavu-core fonts-liberation` |
| `pdfinfo: command not found` | poppler-utils not installed | `sudo apt install poppler-utils` |
| WSL2 says "Permission denied" on `./build-synthetic-pdfs.sh` | Script lost +x bit (e.g. via NTFS share) | `chmod +x scripts/data-prep/build-synthetic-pdfs.sh` |
| Build script aborts on first bad file | `set -euo pipefail` in the script | Wrap the loop yourself with `\|\| continue` if you need to push past failures |
