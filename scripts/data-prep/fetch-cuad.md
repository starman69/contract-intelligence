# Fetch CUAD (Contract Understanding Atticus Dataset)

Primary corpus for the POC. ~510 commercial contracts with span-level legal labels. CC BY 4.0.

## Source

- Project: https://www.atticusprojectai.org/cuad
- Direct download (current at time of writing): https://zenodo.org/record/4595826 — `CUAD_v1.zip`
- License: CC BY 4.0. Attribution required (Atticus Project AI).

## Steps

```bash
mkdir -p samples/contracts/cuad
cd samples/contracts/cuad

# Adjust URL if Zenodo updates the artifact.
curl -L -o CUAD_v1.zip "https://zenodo.org/record/4595826/files/CUAD_v1.zip"
unzip CUAD_v1.zip
rm CUAD_v1.zip

# Preserve license + README in the directory for attribution.
ls -la CUAD_v1/
```

After unzipping you'll have:
- `CUAD_v1/full_contract_pdf/` — the source PDFs
- `CUAD_v1/full_contract_txt/` — extracted text equivalents
- `CUAD_v1/master_clauses.csv` — span-level labels for 41 categories
- `CUAD_v1/CUAD_v1.json` — structured QA-style annotations

## Mapping CUAD labels to our schema

| CUAD category | Our SQL field / clause type |
|---|---|
| "Effective Date" | `Contract.EffectiveDate` |
| "Expiration Date" | `Contract.ExpirationDate` |
| "Renewal Term" / "Auto Renewal" | `Contract.RenewalDate` / `Contract.AutoRenewalFlag` |
| "Governing Law" | `Contract.GoverningLaw` |
| "Parties" | `Contract.Counterparty` (filtered to non-Customer party) |
| "Indemnification" | `ContractClause.ClauseType = 'indemnity'` |
| "Cap on Liability" / "Liability Limit" | `ContractClause.ClauseType = 'limitation_of_liability'` |
| "Termination for Convenience" | `ContractClause.ClauseType = 'termination'` |
| "Confidentiality" / "Non-Disclosure" | `ContractClause.ClauseType = 'confidentiality'` |
| "Audit Rights" | `ContractClause.ClauseType = 'audit_rights'` |

The mapping is what we'll use as **ground truth** in the eval harness ([`../../docs/poc/10-evaluation.md`](../../docs/poc/10-evaluation.md)).

## Upload to Blob

After deploying the Bicep:

```bash
STORAGE_ACCOUNT=$(az deployment sub show --name <deployment-name> --query properties.outputs.storageAccountName.value -o tsv)

az storage blob upload-batch \
  --account-name "$STORAGE_ACCOUNT" \
  --auth-mode login \
  --destination raw \
  --destination-path contracts/cuad/ \
  --source CUAD_v1/full_contract_pdf/
```

Each upload triggers Event Grid → ingestion Function.

## Attribution Notice (for any redistribution)

> "This product includes contracts from the Contract Understanding Atticus Dataset (CUAD), licensed under CC BY 4.0 by The Atticus Project."

## Status

This file is **instructions only** — no fetch is run during the scaffolding pass.
