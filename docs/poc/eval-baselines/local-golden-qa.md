# Eval run 20260428T060929Z

Intent accuracy: **23/25 = 92.0%**

| id | result | actual | expected | sources | conf | ms |
|---|---|---|---|---|---|---|
| q-r-001 | OK | reporting | reporting | sql | 0.95 | 23 |
| q-r-002 | OK | reporting | reporting | sql | 0.95 | 12 |
| q-r-003 | OK | reporting | reporting | sql | 0.95 | 25 |
| q-r-004 | OK | reporting | reporting | sql | 0.95 | 11 |
| q-r-005 | OK | reporting | reporting | sql | 0.95 | 12 |
| q-r-006 | OK | reporting | reporting | sql | 0.95 | 11 |
| q-r-007 | OK | reporting | reporting | sql | 0.95 | 11 |
| q-r-008 | OK | reporting | reporting | sql | 0.95 | 11 |
| q-s-001 | OK | search | search | embeddings,contracts_index,clauses_index,llm | 0.95 | 4992 |
| q-s-002 | OK | search | search | embeddings,contracts_index,clauses_index,llm | 0.95 | 2083 |
| q-s-003 | OK | search | search | embeddings,contracts_index,clauses_index,llm | 0.90 | 1840 |
| q-s-004 | OK | search | search | embeddings,contracts_index,clauses_index,llm | 0.85 | 2014 |
| q-s-005 | OK | search | search | embeddings,contracts_index,clauses_index,llm | 0.85 | 2332 |
| q-s-006 | OK | search | search | embeddings,contracts_index,clauses_index,llm | 1.00 | 1947 |
| q-s-007 | OK | search | search | embeddings,contracts_index,clauses_index,llm | 0.95 | 1861 |
| q-s-008 | OK | search | search | embeddings,contracts_index,clauses_index,llm | 0.85 | 6442 |
| q-c-001 | OK | clause_comparison | clause_comparison | sql,gold_clauses,llm | 0.95 | 1431 |
| q-c-002 | OK | clause_comparison | clause_comparison | sql,gold_clauses,llm | 0.95 | 1353 |
| q-c-003 | OK | clause_comparison | clause_comparison | sql,gold_clauses,llm | 1.00 | 1280 |
| q-c-004 | OK | mixed | mixed | sql,embeddings,contracts_index,clauses_index,llm | 0.85 | 1496 |
| q-c-005 | OK | clause_comparison | clause_comparison | sql,gold_clauses,llm | 1.00 | 4525 |
| q-g-001 | OK | relationship | relationship | graph | 0.95 | 1175 |
| q-g-002 | OK | relationship | relationship | graph | 0.85 | 1204 |
| q-amb-001 | FAIL | reporting | search | sql | 0.80 | 1029 |
| q-amb-002 | FAIL | reporting | search | sql | 0.80 | 1138 |