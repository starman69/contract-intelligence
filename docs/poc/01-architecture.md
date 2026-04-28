# POC Architecture

> The full diagram catalog (data flows, state lifecycles, UI flows, human-in-the-loop modes) lives in [`10-diagrams.md`](10-diagrams.md). This file shows the high-level component view + naming conventions.

## Component Diagram

```mermaid
flowchart TD
    User([User]) -->|browser| SWA[Static Web App<br/>React + Entra ID auth]
    SWA -->|REST| FuncApi[Function App<br/>Python 3.11<br/>API + Router]

    Upload([az storage blob upload<br/>or portal]) --> Blob[(Blob Storage<br/>raw/processed/audit)]
    Blob -->|BlobCreated| EG[Event Grid<br/>System Topic]
    EG -->|Event Grid trigger| FuncIng[Function App<br/>Ingestion Orchestrator]

    FuncIng -->|REST| DI[Document Intelligence<br/>prebuilt-layout]
    FuncIng -->|REST| AOAI1[Azure OpenAI<br/>gpt-4o-mini extraction]
    FuncIng -->|REST| AOAI2[Azure OpenAI<br/>text-embedding-3-small]
    FuncIng --> SQL[(Azure SQL DB<br/>Serverless GP_S_Gen5_1)]
    FuncIng --> AIS[(Azure AI Search<br/>Basic, contracts + clauses indexes)]
    FuncIng --> Blob

    FuncApi -->|reporting| SQL
    FuncApi -->|RAG retrieval| AIS
    FuncApi -->|reasoning| AOAI3[Azure OpenAI<br/>gpt-4o]
    FuncApi -->|gold lookup| SQL

    KV[Key Vault] -.secrets via MI.-> FuncIng
    KV -.secrets via MI.-> FuncApi
    AI[App Insights] -.telemetry.- FuncIng
    AI -.telemetry.- FuncApi
    LAW[Log Analytics Workspace] --- AI

    classDef user      fill:#eceff1,stroke:#455a64,color:#263238;
    classDef ui        fill:#e3f2fd,stroke:#0d47a1,color:#0d47a1;
    classDef compute   fill:#ede7f6,stroke:#4527a0,color:#311b92;
    classDef eventing  fill:#fff8e1,stroke:#ef6c00,color:#e65100;
    classDef data      fill:#e8f5e9,stroke:#1b5e20,color:#1b5e20;
    classDef ai        fill:#fff3e0,stroke:#e65100,color:#bf360c;
    classDef identity  fill:#fce4ec,stroke:#880e4f,color:#880e4f;
    classDef ops       fill:#f3e5f5,stroke:#4a148c,color:#4a148c;
    class User,Upload user;
    class SWA ui;
    class FuncApi,FuncIng compute;
    class EG eventing;
    class Blob,SQL,AIS data;
    class DI,AOAI1,AOAI2,AOAI3 ai;
    class KV identity;
    class AI,LAW ops;
```

## Component Table

| Component | Azure Resource | SKU | Purpose |
|---|---|---|---|
| Landing zone | Storage Account (StorageV2 + HNS) | Standard LRS, Hot | Raw + processed artifacts |
| Event bus | Event Grid System Topic | (consumption) | BlobCreated → Function fanout |
| Ingestion compute | Function App (Linux Consumption) | Y1 | Event-triggered orchestrator |
| API compute | Function App (Linux Consumption) | Y1 | HTTP API for web UI |
| OCR / layout | Document Intelligence | S0 | prebuilt-layout |
| LLM | Azure OpenAI account | S0 | gpt-4o-mini, gpt-4o, text-embedding-3-small deployments |
| Source of truth | Azure SQL Database | GP_S_Gen5_1 (Serverless, 1 vCore, 60min autopause) | Contract metadata |
| Retrieval | Azure AI Search | Basic, 1 replica / 1 partition, semantic ranker | contracts-index + clauses-index |
| UI host | Static Web App | Standard | React SPA + auth |
| Secrets | Key Vault | Standard, RBAC | Connection strings, OpenAI keys (overridden by MI where possible) |
| Observability | Application Insights + Log Analytics | PAYG | Logs, traces, metrics |
| Identity | System-assigned MI on Function Apps | — | Auth to Storage, SQL, OpenAI, DI, Search, KV |

## Sequence: Ingestion

```mermaid
sequenceDiagram
    actor Op as Operator
    participant Blob
    participant EG as Event Grid
    participant Fn as Ingestion Func
    participant DI as Doc Intelligence
    participant AOAI as Azure OpenAI
    participant SQL
    participant AIS as AI Search

    Op->>Blob: az storage blob upload (raw/contracts/{id}.pdf)
    Blob->>EG: Microsoft.Storage.BlobCreated
    EG->>Fn: Event Grid trigger
    Fn->>SQL: INSERT IngestionJob (status=running)
    Fn->>DI: analyze prebuilt-layout
    DI-->>Fn: pages, lines, tables, sections, bounding boxes
    Fn->>Blob: write processed/layout/{id}.json
    Fn->>AOAI: gpt-4o-mini structured-output extraction
    AOAI-->>Fn: { contract_type, parties, dates, governing_law, clauses[] }
    Fn->>Blob: write processed/clauses/{id}.json + audit/{id}.json
    Fn->>AOAI: text-embedding-3-small (contract summary + contextual clauses)
    AOAI-->>Fn: vectors
    Fn->>SQL: UPSERT Contract, ContractClause, ContractObligation
    Fn->>AIS: index documents (contracts-index + clauses-index)
    Fn->>SQL: UPDATE IngestionJob (status=complete)
```

## Sequence: Query (Router)

```mermaid
sequenceDiagram
    actor U as User
    participant UI as Static Web App
    participant API as API Function
    participant SQL
    participant AIS as AI Search
    participant AOAI as Azure OpenAI

    U->>UI: question
    UI->>API: POST /query
    API->>API: classify intent (rules first; gpt-4o-mini fallback)
    alt reporting
        API->>SQL: parameterized SELECT
        SQL-->>API: rows
        API-->>UI: table + optional NL phrasing via gpt-4o-mini
    else clause comparison
        API->>SQL: lookup contract + gold clause
        API->>AIS: retrieve clause-index match
        API->>AOAI: gpt-4o reasoning prompt with citations
        AOAI-->>API: grounded comparison
        API-->>UI: answer + side-by-side + citations
    else RAG
        API->>AIS: hybrid + semantic search
        AIS-->>API: top-k chunks/clauses
        API->>AOAI: gpt-4o answer prompt
        AOAI-->>API: grounded answer
        API-->>UI: answer + citations
    end
```

## Resource Naming

```
rg-contracts-poc-{env}                            # resource group
st{env}contracts{rand}                            # storage account (3-24 lc alphanum)
kv-contracts-{env}-{rand}                         # key vault
sql-contracts-{env}-{rand}                        # sql server
sqldb-contracts                                   # sql database
di-contracts-{env}-{rand}                         # document intelligence
oai-contracts-{env}-{rand}                        # openai
srch-contracts-{env}-{rand}                       # ai search
func-contracts-ingest-{env}-{rand}                # ingestion function app
func-contracts-api-{env}-{rand}                   # api function app
swa-contracts-{env}                               # static web app
appi-contracts-{env}                              # application insights
log-contracts-{env}                               # log analytics workspace
```

`{env}` ∈ {`dev`, `test`, `prod`}; `{rand}` is a 6-char `uniqueString()` suffix.
