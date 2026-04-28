export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  embedding_tokens: number;
  estimated_cost_usd: number;
  calls?: Array<{
    kind: "chat" | "embedding";
    model: string;
    prompt_tokens: number;
    completion_tokens: number;
    embedding_tokens: number;
    cost_usd: number;
  }>;
}

export interface Citation {
  contract_id: string;
  contract_title: string | null;
  page: number | null;
  quote: string;
}

export interface QueryResponse {
  correlation_id: string;
  intent: string;
  data_sources: string[];
  confidence: number;
  filters: Record<string, unknown>;
  fallback_reason: string | null;
  answer: string;
  citations: Citation[];
  rows: Record<string, unknown>[] | null;
  subject_contracts?: Record<string, unknown>[] | null;
  token_usage?: TokenUsage | null;
  query_sql?: string | null;
  query_sql_params?: unknown[] | null;
  out_of_scope: boolean;
  elapsed_ms: number;
}

// Snake/Pascal mix mirrors what SQL columns serialize as today.
export interface ContractSummary {
  ContractId: string;
  ContractTitle: string | null;
  Counterparty: string | null;
  ContractType: string | null;
  EffectiveDate: string | null;
  ExpirationDate: string | null;
  GoverningLaw: string | null;
  Status: string;
}

export interface ContractClauseRow {
  ClauseId: string;
  ClauseType: string | null;
  ClauseText: string;
  PageNumber: number | null;
  SectionHeading: string | null;
  StandardClauseId: string | null;
  DeviationScore: number | null;
  RiskLevel: string | null;
  ReviewStatus: string;
}

export interface ContractObligationRow {
  ObligationId: string;
  Party: string | null;
  ObligationText: string;
  DueDate: string | null;
  Frequency: string | null;
  TriggerEvent: string | null;
  RiskLevel: string | null;
}

export interface ContractAuditRow {
  AuditId: string;
  FieldName: string;
  FieldValue: string | null;
  Confidence: number | null;
  ExtractionMethod: string | null;
  ModelName: string | null;
  PromptVersion: string | null;
  CreatedAt: string;
}

export interface ContractDetail extends ContractSummary {
  RenewalDate: string | null;
  AutoRenewalFlag: boolean | null;
  Jurisdiction: string | null;
  ContractValue: number | null;
  Currency: string | null;
  BusinessOwner: string | null;
  LegalOwner: string | null;
  ReviewStatus: string;
  BlobUri: string;
  // Browser-friendly proxy URL added by the api server. Hits
  // /api/contracts/{id}/file which streams the source bytes through
  // clients.blob_service — works against Azurite locally and Azure Blob (with
  // managed identity) in production without exposing storage hostnames or
  // auth to the browser. MIME type is derived from the filename extension so
  // PDFs render inline and DOCX/RTF/etc. download as attachments.
  FileUrl?: string | null;
  ExtractionConfidence: number | null;
  Clauses: ContractClauseRow[];
  Obligations: ContractObligationRow[];
  Audit: ContractAuditRow[];
  // Display-time inheritance: when a sub-document has a null metadata field
  // that a sibling contract (same Counterparty) has set, the inherited value
  // is surfaced here keyed by field name. The literal extracted null stays
  // on the top-level field. See docs/poc/02-data-model.md.
  Inherited?: Record<string, InheritedFieldValue> | null;
}

export interface InheritedFieldValue {
  value: string | number | boolean | null;
  source_contract_id: string;
  source_contract_title: string | null;
}

export interface GoldClause {
  StandardClauseId: string;
  ClauseType: string;
  Version: number;
  ApprovedText: string;
  Jurisdiction: string | null;
  BusinessUnit: string | null;
  EffectiveFrom: string;
  EffectiveTo: string | null;
  RiskPolicy: string | null;
  ReviewOwner: string | null;
}

export interface ComparisonResult {
  clause_type: string;
  // applicable=false → clause type isn't typical for this contract_type
  // (e.g., NDA + indemnity); UI should render neutral, not as a missing-but-
  // expected gap. Backend defaults to true for backwards compat when omitted.
  applicable?: boolean;
  available: boolean;
  reason?: string;
  contract_clause_text?: string;
  contract_page?: number | null;
  gold_clause_id?: string;
  gold_version?: number;
  gold_text?: string;
  diff?: string;
}

export interface CompareResponse {
  contract_id: string;
  contract_title?: string | null;
  elapsed_ms?: number;
  token_usage?: TokenUsage | null;
  comparisons: ComparisonResult[];
}

export interface ContractsListResponse {
  rows: ContractSummary[];
  total: number;
}

export interface ContractsListParams {
  q?: string;
  status?: string;
  contract_type?: string;
  expires_before?: string;
  expires_after?: string;
  sort?: string;
  dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface ChatMessage {
  question: string;
  response?: QueryResponse;
  error?: string;
  busy: boolean;
  cancelled?: boolean;
}

export type Tab = "chat" | "contracts" | "gold";
