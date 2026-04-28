import type {
  CompareResponse,
  ContractDetail,
  ContractsListParams,
  ContractsListResponse,
  GoldClause,
  QueryResponse,
} from "./types";

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error((err as { error?: string }).error ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function queryApi(
  question: string,
  signal?: AbortSignal,
): Promise<QueryResponse> {
  const res = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });
  return jsonOrThrow<QueryResponse>(res);
}

export async function listContracts(
  params: ContractsListParams = {},
  signal?: AbortSignal,
): Promise<ContractsListResponse> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  }
  const url = qs.toString() ? `/api/contracts?${qs}` : "/api/contracts";
  return jsonOrThrow<ContractsListResponse>(await fetch(url, { signal }));
}

export async function getContract(id: string): Promise<ContractDetail> {
  return jsonOrThrow<ContractDetail>(
    await fetch(`/api/contracts/${encodeURIComponent(id)}`),
  );
}

export async function listGoldClauses(): Promise<GoldClause[]> {
  return jsonOrThrow<GoldClause[]>(await fetch("/api/gold-clauses"));
}

export async function compare(
  contract_id: string,
  clause_types: string[],
): Promise<CompareResponse> {
  const res = await fetch("/api/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contract_id, clause_types }),
  });
  return jsonOrThrow<CompareResponse>(res);
}
