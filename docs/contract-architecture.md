Below is an Azure-native reference architecture for a legal-contract intelligence platform that ingests contracts from SharePoint, extracts high-fidelity metadata and text, supports structured reporting, semantic search, graph-style relationship queries, and LLM-based legal reasoning with citations.

## **1\. Recommended target architecture**

SharePoint Contract Libraries  
       |  
       | Microsoft Graph / SharePoint Webhooks / Logic Apps  
       v  
Landing Zone: Azure Blob Storage / ADLS Gen2  
       |  
       | Event Grid  
       v  
Ingestion Orchestrator  
Azure Functions / Durable Functions / Logic Apps / Data Factory  
       |  
       \+--\> Virus scan / DLP / file validation  
       |  
       \+--\> Azure AI Document Intelligence  
       |       \- OCR  
       |       \- layout extraction  
       |       \- tables  
       |       \- key-value pairs  
       |       \- custom extraction models  
       |  
       \+--\> Azure OpenAI / Azure AI Foundry  
       |       \- clause extraction  
       |       \- contract type classification  
       |       \- expiration date normalization  
       |       \- party extraction  
       |       \- risk flags  
       |       \- standard-clause comparison  
       |  
       \+--\> Human review workflow  
       |       \- required for low-confidence extraction  
       |       \- legal approval of critical metadata  
       |  
       v  
System of Record Metadata Store  
Azure SQL Database / SQL Managed Instance  
       |  
       \+--\> Azure AI Search  
       |       \- chunks  
       |       \- embeddings  
       |       \- document metadata filters  
       |       \- citations  
       |       \- semantic ranking  
       |  
       \+--\> Graph Store  
       |       \- Azure Cosmos DB Gremlin API, Neo4j on Azure, or SQL graph tables  
       |  
       \+--\> Blob / ADLS  
       |       \- original document  
       |       \- normalized text  
       |       \- OCR JSON  
       |       \- extracted clause JSON  
       |  
       v  
Question Router / Reasoning Orchestrator  
Azure Functions / Container Apps / AKS \+ Semantic Kernel / LangChain  
       |  
       \+--\> Structured SQL path  
       \+--\> AI Search RAG path  
       \+--\> Graph query path  
       \+--\> Hybrid multi-step reasoning path  
       |  
       v  
User Interfaces  
Web app \+ Teams app / Bot Framework / Copilot Studio

The important design choice is this: **do not treat Azure AI Search as the system of record.** Use SQL or another governed metadata store as the source of truth for contract metadata, extracted fields, lifecycle status, review state, and confidence scores. Use Azure AI Search as the optimized retrieval layer for conversational and semantic access.

---

## **2\. Should you move documents from SharePoint to Blob?**

For your use case, **yes, for the pro-code production architecture, copy the documents to Azure Blob Storage or ADLS Gen2 as part of ingestion**.

SharePoint can remain the business-facing repository, but Blob or ADLS should become the AI processing landing zone.

### **Why copy to Blob / ADLS?**

Because you need:

1. Durable processing snapshots.  
2. Better control over versioning and reprocessing.  
3. Event-driven pipelines.  
4. Easier integration with Azure AI Document Intelligence.  
5. Easier indexing into Azure AI Search.  
6. Storage of OCR/layout JSON, normalized text, extracted clauses, and audit artifacts.  
7. Scalable processing for 100,000 documents.  
8. Separation between SharePoint collaboration and AI/data workloads.

Microsoft’s own Azure AI Search guidance notes that for production RAG over SharePoint, the SharePoint indexer is still preview and recommends either Copilot Studio or a custom connector using SharePoint webhooks, Microsoft Graph export to Blob, then Azure Blob indexing for incremental indexing. It also notes the SharePoint indexer is public preview and not recommended for production workloads.

So the practical recommendation is:

SharePoint \= source collaboration system  
Blob / ADLS \= AI processing and immutable document snapshot layer  
SQL \= metadata source of truth  
AI Search \= retrieval and conversational search index

You can store the SharePoint URL, drive item ID, site ID, library ID, version, ETag, permissions snapshot, and hash in SQL so every AI artifact traces back to the originating SharePoint item.

---

## **3\. Core data stores**

### **A. Azure SQL Database: contract metadata source of truth**

Use SQL for structured and governed metadata:

Contract  
\- ContractId  
\- SharePointDriveItemId  
\- SharePointSiteId  
\- SharePointUrl  
\- BlobUri  
\- FileHash  
\- FileVersion  
\- ContractTitle  
\- ContractType  
\- Counterparty  
\- EffectiveDate  
\- ExpirationDate  
\- RenewalDate  
\- AutoRenewalFlag  
\- GoverningLaw  
\- Jurisdiction  
\- ContractValue  
\- Currency  
\- BusinessOwner  
\- LegalOwner  
\- Status  
\- ExtractionConfidence  
\- ReviewStatus  
\- CreatedAt  
\- UpdatedAt

Clause table:

ContractClause  
\- ClauseId  
\- ContractId  
\- ClauseType  
\- ClauseText  
\- PageNumber  
\- BoundingBox  
\- StandardClauseId  
\- DeviationScore  
\- RiskLevel  
\- ExtractionConfidence  
\- ReviewedBy  
\- ReviewStatus

Obligation table:

ContractObligation  
\- ObligationId  
\- ContractId  
\- Party  
\- ObligationText  
\- DueDate  
\- Frequency  
\- TriggerEvent  
\- RiskLevel

This enables accurate queries like:

Show me the contracts expiring in the next 6 months.

That should be answered from SQL, not from an LLM.

---

### **B. Azure Blob Storage / ADLS Gen2: document and extraction artifacts**

Use containers like:

/raw/contracts/  
   original PDFs and DOCX snapshots

/processed/text/  
   normalized extracted text

/processed/layout/  
   Document Intelligence JSON

/processed/chunks/  
   chunked text with page references

/processed/clauses/  
   extracted clause JSON

/processed/embeddings/  
   optional embedding artifacts

/audit/  
   extraction logs, model versions, prompts, outputs

For legal accuracy, preserve every intermediate artifact.

---

### **C. Azure AI Search: conversational retrieval index**

Use Azure AI Search for:

1. Full-text search.  
2. Vector search.  
3. Hybrid search.  
4. Semantic ranking.  
5. Metadata filtering.  
6. Retrieval for LLM reasoning.  
7. Document-level and clause-level citations.

Recommended indexes:

contracts-index  
\- ContractId  
\- Title  
\- Counterparty  
\- ContractType  
\- EffectiveDate  
\- ExpirationDate  
\- Status  
\- LegalOwner  
\- BusinessUnit  
\- Permissions  
\- Summary  
\- SearchableText  
\- Embedding

clauses-index  
\- ClauseId  
\- ContractId  
\- ClauseType  
\- ClauseText  
\- PageNumber  
\- SectionHeading  
\- RiskLevel  
\- StandardClauseId  
\- DeviationScore  
\- Embedding

For high fidelity, I would separate **document-level retrieval** and **clause-level retrieval**. Clause comparison becomes much better when clauses are indexed as first-class records.

---

### **D. Graph store: relationship and network queries**

Use graph capabilities when users ask about relationships:

Examples:

Which suppliers have contracts governed by New York law and include non-standard indemnity clauses?

Show all contracts connected to Acme Corp subsidiaries.

Which contracts inherit terms from a master agreement?

Graph model:

(:Counterparty)-\[:PARTY\_TO\]-\>(:Contract)  
(:Contract)-\[:HAS\_CLAUSE\]-\>(:Clause)  
(:Contract)-\[:GOVERNED\_BY\]-\>(:Jurisdiction)  
(:Contract)-\[:AMENDS\]-\>(:Contract)  
(:Contract)-\[:UNDER\_MASTER\]-\>(:MasterAgreement)  
(:Counterparty)-\[:SUBSIDIARY\_OF\]-\>(:Counterparty)  
(:Contract)-\[:HAS\_OBLIGATION\]-\>(:Obligation)

Options:

1. **Azure Cosmos DB for Gremlin** if you want Azure-native graph.  
2. **Neo4j on Azure Marketplace** if legal relationship queries become central.  
3. **Azure SQL graph tables** if you want simpler governance and SQL-centric operations.

For a POC, I would avoid graph unless you already know you need it. For production, graph is useful for master agreements, amendments, subsidiaries, obligations, and clause dependency networks.

---

## **4\. Ingestion pipeline**

### **Step 1: Detect changes in SharePoint**

Options:

#### **Low-code**

Use **Power Automate** or **Logic Apps**:

When file is created or modified in SharePoint  
   \-\> copy file to Blob  
   \-\> enqueue processing message

#### **Pro-code**

Use:

SharePoint Webhooks  
Microsoft Graph delta queries  
Azure Functions / Durable Functions  
Event Grid  
Service Bus

For production, use **Graph delta queries** plus webhooks. Webhooks notify you something changed; delta queries reliably reconcile what changed.

---

### **Step 2: Copy document to Blob / ADLS**

Store:

raw/contracts/{siteId}/{driveId}/{itemId}/{version}/filename.pdf

Record in SQL:

SharePoint ID  
Blob URI  
ETag  
Version  
Hash  
Ingestion status  
Timestamp  
---

### **Step 3: Extract text, OCR, layout, and tables**

Use **Azure AI Document Intelligence**.

For legal contracts, use:

1. Read model for OCR.  
2. Layout model for paragraphs, tables, selection marks, sections.  
3. Custom extraction models for recurring contract types.  
4. Optional classifier to identify contract type before extraction.

This matters because your documents include:

PDF  
DOCX  
scanned PDFs  
embedded images  
mixed digital/scanned pages

For DOCX, you can extract native text directly, but I would still normalize through a common document model. For PDFs with scans/images, use Document Intelligence OCR.

Store:

Full text  
Page-level text  
Paragraphs  
Tables  
Bounding boxes  
Confidence scores  
---

### **Step 4: Extract structured legal metadata**

Use a combination of deterministic extraction and LLM extraction.

For critical fields like expiration date, effective date, counterparty, governing law, renewal term, and auto-renewal flag, use a validation pipeline:

Document Intelligence text  
   \-\> candidate extraction  
   \-\> Azure OpenAI structured output  
   \-\> rules validation  
   \-\> confidence scoring  
   \-\> SQL write  
   \-\> human review if low confidence

Example:

ExpirationDate extracted from clause text  
Normalize date  
Check if clause type \= Term / Renewal  
Check if date is explicit or derived  
Store:  
   ExpirationDate  
   ExpirationDateSourceClauseId  
   Confidence  
   Reasoning  
   PageNumber

For high-fidelity legal use, every extracted field should include:

value  
source text  
page number  
confidence  
extraction method  
model version  
review status  
---

### **Step 5: Clause extraction and standard-clause comparison**

Create a “gold clause set”:

StandardClause  
\- StandardClauseId  
\- ClauseType  
\- Version  
\- ApprovedText  
\- Jurisdiction  
\- BusinessUnit  
\- EffectiveFrom  
\- EffectiveTo  
\- RiskPolicy

For each contract:

Extract clauses  
Classify clause type  
Compare to standard clause  
Compute deviation  
Generate risk explanation  
Store result in SQL  
Index clause in AI Search

Do not rely only on vector similarity for legal comparison. Use a layered approach:

1\. Clause type classifier  
2\. Exact / near-exact text comparison  
3\. Semantic similarity  
4\. LLM legal-difference analysis  
5\. Rules-based policy checks  
6\. Optional human approval

For example:

Compare the limitation of liability clause to our gold standard.

The system should retrieve:

1. The contract’s limitation of liability clause.  
2. The correct gold clause version.  
3. Any policy rules.  
4. Prior approved deviations if relevant.

Then the LLM produces a grounded comparison with citations.

---

## **5\. Question reasoning router**

You called this a “query router.” Architecturally, this is an **intent router / query planner / reasoning orchestrator**.

It decides whether a question should go to:

A. Structured SQL reporting  
B. Azure AI Search RAG  
C. Graph query  
D. Hybrid multi-step workflow  
E. Human escalation

### **Example routing**

#### **Query 1**

Show me the contracts expiring in the next 6 months.

Route:

SQL structured query

Reason:

Expiration date should be a reviewed structured field.

Output:

List of contracts  
Expiration date  
Counterparty  
Owner  
Status  
Link to SharePoint / viewer  
Optional export

No LLM is needed except maybe to phrase the response.

---

#### **Query 2**

Which supplier agreements have non-standard termination clauses?

Route:

SQL \+ clause index

Process:

SQL filter ContractType \= Supplier Agreement  
SQL or AI Search filter ClauseType \= Termination  
DeviationScore \> threshold  
Return clause list with risk level  
---

#### **Query 3**

Compare the indemnity clause in Acme MSA to our standard.

Route:

Hybrid RAG \+ SQL

Process:

Resolve Acme MSA from SQL  
Retrieve indemnity clause from clauses-index  
Retrieve gold indemnity clause from SQL  
Ask LLM to compare  
Return differences, risk rating, citations  
---

#### **Query 4**

Are any contracts with Acme subsidiaries affected by the parent company change of control?

Route:

Graph \+ RAG \+ SQL

Process:

Graph resolves Acme corporate family  
SQL retrieves active contracts  
AI Search retrieves change-of-control clauses  
LLM analyzes applicability  
---

#### **Query 5**

What does this contract say about audit rights?

Route:

AI Search RAG

Process:

Retrieve audit-related chunks and clauses  
Generate answer with citations  
---

## **6\. Router implementation pattern**

The router should be deterministic where possible.

User question  
   |  
   v  
Query classifier  
   |  
   \+--\> Reporting intent  
   |       \-\> SQL  
   |  
   \+--\> Document lookup intent  
   |       \-\> SQL \+ AI Search  
   |  
   \+--\> Clause comparison intent  
   |       \-\> SQL \+ clause index \+ gold set  
   |  
   \+--\> Relationship intent  
   |       \-\> Graph  
   |  
   \+--\> Open-ended legal reasoning intent  
           \-\> RAG \+ LLM

Use Azure OpenAI only for intent classification when necessary. Many questions can be routed with rules and keywords.

For production, return a **query plan** internally:

{  
 "intent": "clause\_comparison",  
 "data\_sources": \["sql", "ai\_search"\],  
 "requires\_llm": true,  
 "requires\_citations": true,  
 "requires\_human\_review": false  
}

For legal users, the UI can optionally show:

Answer type: Clause comparison  
Sources used: Contract clause, Gold standard clause, Legal policy  
Confidence: High  
---

## **7\. Accuracy and fidelity controls**

For legal contracts, accuracy depends more on pipeline design than on the model.

### **Recommended controls**

1. **Structured fields from SQL, not LLM memory.**  
2. **Every answer must cite document, page, and clause.**  
3. **LLM cannot answer without retrieved evidence.**  
4. **Confidence thresholds trigger human review.**  
5. **Critical metadata requires review status.**  
6. **Prompt and model version are logged.**  
7. **Gold clause set is versioned.**  
8. **Document version is preserved.**  
9. **Permission trimming is enforced.**  
10. **Users can open the source document at the cited page.**

For questions like:

Show me contracts expiring in the next 6 months.

The LLM should not “search and reason” over raw text. It should call the SQL path.

For questions like:

Is the indemnity clause more favorable than our standard?

The LLM can reason, but only over retrieved clause text and approved standard text.

---

## **8\. Security and permissions**

You must decide whether your AI system respects SharePoint permissions directly or uses its own app-level authorization model.

### **Recommended production approach**

Copy SharePoint ACL metadata during ingestion and enforce it at query time.

Store:

Document permissions  
Allowed users  
Allowed groups  
Sensitivity labels  
Confidentiality classification

Then filter:

SQL WHERE user has access  
AI Search filter on allowed principals

Microsoft has SharePoint ACL ingestion support for Azure AI Search, but it is currently described as public preview in the SharePoint indexer path. For production, I would not rely on the preview SharePoint indexer as the core ingestion method. Use Microsoft Graph to copy files and permission metadata, then write your own normalized permission model.

Also integrate:

Microsoft Entra ID  
Managed identities  
Key Vault  
Private Endpoints  
VNet integration  
Microsoft Purview  
Azure Monitor  
Defender for Cloud  
---

## **9\. UI architecture**

You need two user experiences:

1. Web app.  
2. Microsoft Teams extension.

### **Web app**

Recommended stack:

Azure Static Web Apps or App Service  
React / Angular / Blazor  
Azure Functions / Container Apps API  
Microsoft Entra ID auth  
Azure AI Search  
Azure SQL  
Azure OpenAI

UI capabilities:

Document list  
Filters  
Saved views  
Contract detail page  
Clause viewer  
Chat panel  
Source citations  
Side-by-side clause comparison  
Open in SharePoint  
Open in document viewer  
Export to Excel / PDF  
Feedback buttons  
Human review queue

The document-list UI should use SQL for filtering/sorting, not AI Search. AI Search can support keyword/semantic search within the list.

---

### **Teams interface**

Options:

#### **Low-code**

Use **Copilot Studio** and publish to Teams.

Good for:

POC  
Simple Q\&A  
SharePoint grounding  
Basic workflows  
Teams deployment

Limitations:

Less control over router  
Less control over custom metadata pipeline  
Less control over citations and clause comparison logic  
Harder to implement strict legal-grade workflows

#### **Pro-code**

Use:

Teams Toolkit  
Azure Bot Service  
Bot Framework SDK  
Microsoft Graph  
Azure Functions / Container Apps backend

Good for:

Custom router  
Complex SQL \+ Search \+ Graph orchestration  
Legal-specific UI cards  
Document lists  
Adaptive Cards  
Approval workflows  
Clause comparison output

For your use case, I would use **Copilot Studio for early exploration** and **a pro-code Teams app for production** if high fidelity and custom routing are required.

---

## **10\. Low-code / no-code path**

This is the fastest way to validate value.

### **Option A: Copilot Studio \+ SharePoint knowledge source**

Architecture:

SharePoint  
   \-\> Copilot Studio knowledge source  
   \-\> Teams / Web chat

Pros:

Fastest POC  
Minimal engineering  
Teams publishing is easy  
Uses Microsoft 365 identity  
Good for simple natural language Q\&A

Cons:

Limited control over extraction  
Limited structured metadata quality  
Limited clause comparison pipeline  
Limited custom routing  
Not ideal for legal-grade reporting

Microsoft’s Copilot Studio guidance supports SharePoint as a knowledge source and Teams/web channels. It also documents limits and notes that SharePoint knowledge sources support Word, PowerPoint, and PDF files.

### **Option B: Power Automate \+ AI Builder \+ Document Intelligence \+ Dataverse**

Architecture:

SharePoint trigger  
   \-\> Power Automate  
   \-\> AI Builder / Document Intelligence  
   \-\> Dataverse  
   \-\> Copilot Studio  
   \-\> Power BI

Pros:

Low-code extraction workflow  
Good for metadata capture  
Easy business-user review  
Works well for POC

Cons:

Can become expensive or hard to govern at 100,000 docs  
Less flexible for complex RAG and graph routing  
May hit connector/payload limits

Best for:

500-document POC  
Metadata extraction validation  
Legal review workflow prototype  
---

## **11\. Pro-code path**

This is the recommended production architecture.

### **Services**

Microsoft Graph API  
SharePoint Webhooks  
Azure Functions or Durable Functions  
Azure Service Bus  
Azure Blob Storage / ADLS Gen2  
Azure AI Document Intelligence  
Azure OpenAI / Azure AI Foundry  
Azure SQL Database  
Azure AI Search  
Azure Cosmos DB / Neo4j / SQL graph  
Azure App Service / Container Apps / AKS  
Azure Bot Service  
Teams Toolkit  
Application Insights  
Key Vault  
Microsoft Purview

### **Why pro-code?**

Because you need:

Accurate metadata extraction  
Custom confidence thresholds  
Human-in-the-loop review  
Gold clause comparison  
Document versioning  
Permission trimming  
Multi-source query planning  
SQL \+ Search \+ Graph orchestration  
Detailed audit logs  
Production-scale ingestion  
---

## **12\. POC architecture for 500 documents**

For 500 docs averaging 5 MB:

SharePoint  
   \-\> Logic Apps or Power Automate  
   \-\> Blob Storage  
   \-\> Document Intelligence  
   \-\> Azure SQL  
   \-\> Azure AI Search  
   \-\> Azure OpenAI  
   \-\> Simple web app or Copilot Studio/Teams bot

Do not overbuild graph at the POC stage unless graph questions are mandatory.

POC goals:

1. Extract metadata from 500 contracts.  
2. Validate expiration date accuracy.  
3. Extract 5–10 important clause types.  
4. Build clause comparison against gold standard.  
5. Build router for 4–5 query types.  
6. Return citations with page references.  
7. Build legal review workflow for low-confidence fields.  
8. Validate permission model.

POC query types:

1\. Show contracts expiring in next 6 months.  
2\. Find contracts with auto-renewal.  
3\. Compare indemnity clause to gold standard.  
4\. Summarize termination rights for this contract.  
5\. Find non-standard limitation of liability clauses.  
---

## **13\. Production architecture for 100,000 documents**

For 100,000 docs averaging 5 MB, raw files are about:

100,000 x 5 MB \= \~500 GB

But processed artifacts can be much larger when you include:

OCR JSON  
layout JSON  
normalized text  
chunks  
embeddings  
clause extraction  
audit logs  
versions

Plan for multiple terabytes over time, especially with versioning.

### **Production considerations**

#### **Ingestion scale**

Use:

Service Bus queues  
Durable Functions fan-out/fan-in  
Retry policies  
Dead-letter queues  
Idempotent processing  
Document hash checks  
Backpressure controls

#### **Processing scale**

Separate stages:

1\. Copy file  
2\. OCR/layout extraction  
3\. Text normalization  
4\. Metadata extraction  
5\. Clause extraction  
6\. Human review  
7\. SQL update  
8\. AI Search indexing  
9\. Graph update

Each stage should be independently retryable.

#### **Index scale**

Use separate indexes for:

contracts  
clauses  
chunks  
gold clauses

Chunking strategy:

Chunk by legal section / clause where possible  
Preserve page number  
Preserve heading  
Preserve contract ID  
Preserve clause type  
Avoid arbitrary token-only chunks for clauses

#### **Query latency**

For common reporting queries, SQL should return results quickly.

For LLM reasoning queries:

Target:  
SQL/AI Search retrieval: sub-second to few seconds  
LLM answer: depends on model and prompt size

Use caching for:

Contract summaries  
Clause extraction  
Gold clause comparisons  
Popular reports  
---

## **14\. Indexing strategy**

You asked whether metadata can be stored in SQL and also the index during ingest, or whether it should be another task.

Best practice:

Write metadata to SQL first.  
Then publish to AI Search as a downstream indexing step.

Use an event:

MetadataUpdated event  
   \-\> indexer function  
   \-\> update Azure AI Search

This avoids the index becoming inconsistent with the source of truth.

### **Recommended flow**

Document processed  
   \-\> SQL transaction commits metadata  
   \-\> emit event  
   \-\> AI Search index updated  
   \-\> graph updated if needed

For accuracy, include a field like:

SearchIndexVersion  
MetadataVersion  
DocumentVersion  
ExtractionVersion

Then the query layer can detect stale index records.

---

## **15\. Handling scanned PDFs and images**

Because not all contracts are native digital, assume every file may need OCR.

Recommended approach:

PDF/DOCX detected  
   |  
   \+--\> Extract native text if available  
   \+--\> Run Document Intelligence layout/OCR  
   \+--\> Compare text coverage  
   \+--\> Use best combined normalized text

For scanned PDFs:

Document Intelligence OCR  
Page-level confidence  
Table extraction  
Layout extraction

For embedded images inside DOCX:

Extract images  
Run OCR on embedded images if needed  
Merge text back into page/section context

For legal fidelity, keep page references and bounding boxes.

---

## **16\. Gold set clause comparison design**

Gold set should be treated like governed legal content.

Gold Clause Repository  
   \- approved by Legal  
   \- versioned  
   \- jurisdiction-specific  
   \- contract-type-specific  
   \- effective dates  
   \- fallback hierarchy

Comparison flow:

User asks comparison question  
   |  
   v  
Resolve contract  
   |  
   v  
Find relevant extracted clause  
   |  
   v  
Find correct gold clause version  
   |  
   v  
Run deterministic diff  
   |  
   v  
Run semantic comparison  
   |  
   v  
Run LLM legal reasoning  
   |  
   v  
Return:  
   \- matched clause  
   \- gold clause  
   \- differences  
   \- risk rating  
   \- cited source pages  
   \- recommended action

The answer should say things like:

The contract clause differs from the approved standard in three material ways:  
1\. It removes the liability cap exception for confidentiality breaches.  
2\. It extends indemnity to indirect losses.  
3\. It changes the notice period from 30 days to 10 days.

But every point should map to cited text.

---

## **17\. Reporting versus LLM reasoning**

This distinction is critical.

### **Reporting questions**

Use SQL:

show  
list  
count  
filter  
contracts expiring  
contracts by owner  
contracts with renewal date  
contracts missing metadata  
contracts by jurisdiction

### **Search questions**

Use Azure AI Search:

find contracts mentioning audit rights  
find clauses similar to this  
search for change of control language

### **Reasoning questions**

Use RAG \+ LLM:

summarize termination rights  
compare clause to standard  
explain risk  
what obligations does vendor have

### **Relationship questions**

Use graph:

contracts under a master agreement  
contracts connected to subsidiaries  
amendments affecting parent contracts  
obligations tied to counterparties  
---

## **18\. Suggested Azure-native implementation stack**

### **POC stack**

Power Automate or Logic Apps  
Blob Storage  
Azure AI Document Intelligence  
Azure SQL Database  
Azure AI Search  
Azure OpenAI  
Copilot Studio or simple React app  
Teams publishing through Copilot Studio or Teams Toolkit

### **Production stack**

Microsoft Graph API  
SharePoint Webhooks \+ Delta Queries  
Azure Functions / Durable Functions  
Azure Service Bus  
Blob Storage / ADLS Gen2  
Azure AI Document Intelligence  
Azure OpenAI / Azure AI Foundry  
Azure SQL Database  
Azure AI Search  
Cosmos DB Gremlin or Neo4j if graph is required  
Container Apps or AKS for orchestration APIs  
React web app  
Azure Bot Service \+ Teams Toolkit  
Application Insights  
Key Vault  
Private Link  
Microsoft Purview  
---

## **19\. Accelerators and guides to start from**

The most relevant Microsoft starting points are:

1. **Azure AI Search SharePoint indexing guidance**  
    Useful for understanding SharePoint ingestion, ACLs, and why the SharePoint indexer is not ideal as a production dependency yet.  
2. **Azure AI Search \+ RAG samples**  
    Look for Microsoft’s “Chat with your data” / Azure OpenAI on your data / AI Search RAG samples.  
3. **Azure AI Document Intelligence samples**  
    Useful for OCR, layout extraction, custom extraction, and contract-like document processing.  
4. **Copilot Studio architecture guidance**  
    Useful for low-code chatbot and Teams/web channel deployment.  
5. **Teams Toolkit samples**  
    Useful for a pro-code Teams app with bot, tabs, adaptive cards, and Entra auth.  
6. **Semantic Kernel planners / agents**  
    Useful for implementing the query router and tool-calling orchestration.  
7. **Azure Architecture Center document processing examples**  
    Useful for Power Automate, AI Builder, Document Intelligence, Functions, and storage patterns.

---

## **20\. Final recommendation**

For your requirements, I would build this in two phases.

### **Phase 1: POC**

Use:

SharePoint  
Logic Apps or Power Automate  
Blob Storage  
Document Intelligence  
Azure SQL  
Azure AI Search  
Azure OpenAI  
Simple web app or Copilot Studio

Implement only these router paths:

1\. SQL reporting  
2\. AI Search RAG  
3\. Clause comparison against gold set

Skip graph unless required.

### **Phase 2: Production**

Move to:

Graph webhooks \+ delta sync  
Durable Functions  
Service Bus  
Blob / ADLS  
SQL source of truth  
AI Search retrieval layer  
Clause-level indexing  
Human review workflow  
Teams Toolkit / Bot Framework app  
Optional graph database

The key architectural principle is:

SQL decides facts.  
AI Search retrieves evidence.  
Graph resolves relationships.  
LLM explains and compares, grounded only in approved evidence.  
SharePoint remains the collaboration source.  
Blob/ADLS becomes the AI processing source.

That gives you the best balance of legal accuracy, auditability, scalability, and Azure-native implementation.

