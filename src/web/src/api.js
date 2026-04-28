async function jsonOrThrow(res) {
    if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error ?? `HTTP ${res.status}`);
    }
    return (await res.json());
}
export async function queryApi(question, signal) {
    const res = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal,
    });
    return jsonOrThrow(res);
}
export async function listContracts(params = {}, signal) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== "")
            qs.set(k, String(v));
    }
    const url = qs.toString() ? `/api/contracts?${qs}` : "/api/contracts";
    return jsonOrThrow(await fetch(url, { signal }));
}
export async function getContract(id) {
    return jsonOrThrow(await fetch(`/api/contracts/${encodeURIComponent(id)}`));
}
export async function listGoldClauses() {
    return jsonOrThrow(await fetch("/api/gold-clauses"));
}
export async function compare(contract_id, clause_types) {
    const res = await fetch("/api/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contract_id, clause_types }),
    });
    return jsonOrThrow(res);
}
