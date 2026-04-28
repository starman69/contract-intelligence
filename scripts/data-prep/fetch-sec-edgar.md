# Fetch SEC EDGAR Material Contracts

US public-company filings include material contracts as `EX-10` exhibits. Free, public records. Used to add counterparty and industry diversity beyond CUAD.

## Source

- EDGAR full-text search (Exhibit 10): https://efts.sec.gov/LATEST/search-index?q=&dateRange=custom&forms=8-K&type=10-K&startdt=2024-01-01&enddt=2024-12-31
- EDGAR API (preferred): https://data.sec.gov/submissions/CIK{cik}.json

## SEC fair-use note

SEC requires a `User-Agent` header identifying your contact when querying their API. Do not flood — they rate-limit at ~10 requests/sec.

## Selection criteria for the POC

Aim for ~80 documents distributed across:

| Type | Count | EDGAR phrasing |
|---|---|---|
| Supplier / supply | ~15 | "Supply Agreement", "Master Supply Agreement" |
| Services / consulting | ~15 | "Services Agreement", "Master Services Agreement", "MSA" |
| License / IP | ~15 | "License Agreement", "Patent License" |
| Lease | ~10 | "Lease", "Sublease" |
| Credit / loan | ~10 | "Credit Agreement", "Loan and Security Agreement" |
| Employment / executive | ~10 | "Employment Agreement", "Executive Employment Agreement" |
| Other | ~5 | Joint venture, distribution, settlement |

## Suggested fetch script (Python, not committed)

```python
# scripts/data-prep/fetch_edgar.py  -- reference; do not check in actual contracts
import requests, time, pathlib, csv

HEADERS = {"User-Agent": "Contract POC dpatten@example.com"}

def search_exhibit10(query: str, max_results: int = 15):
    url = "https://efts.sec.gov/LATEST/search-index"
    params = {"q": f'"{query}" exhibit 10', "forms": "10-K,10-Q,8-K"}
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()["hits"]["hits"][:max_results]

def download(hit, out_dir):
    accession = hit["_id"].split(":")[0].replace("-", "")
    cik = hit["_source"]["ciks"][0]
    file = hit["_source"]["display_names"][0]
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{file}"
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    out = pathlib.Path(out_dir) / f"{cik}_{accession}_{file}"
    out.write_bytes(r.content)
    time.sleep(0.15)  # be polite

# ... iterate the table above; write a manifest.csv with cik, accession, type
```

## Manifest

For audit trail, write `samples/contracts/edgar/manifest.csv`:

```
cik,accession,filer_name,form_type,exhibit,filename,downloaded_at
0000320193,0000320193-24-000001,Apple Inc,10-K,EX-10.1,apple_10k_ex10_1.htm,2026-04-24T...
```

## Conversion to PDF (optional)

EDGAR exhibits are typically `.htm`. The ingestion pipeline handles HTML directly via Document Intelligence, but if you want consistent PDFs:

```bash
# requires headless Chromium
for f in samples/contracts/edgar/*.htm; do
  chromium --headless --disable-gpu --print-to-pdf="${f%.htm}.pdf" "$f"
done
```

## Upload to Blob

```bash
az storage blob upload-batch \
  --account-name "$STORAGE_ACCOUNT" \
  --auth-mode login \
  --destination raw \
  --destination-path contracts/edgar/ \
  --source samples/contracts/edgar/
```

## Status

Instructions only. No fetch is run during scaffolding.
