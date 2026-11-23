# B09 — local semantic embedding review

## Outcome

B09 is technically complete and `IN_REVIEW`. The persisted Qdrant index uses local
Ollama `all-minilm`, records an embedding-compatible schema-v2 manifest, fails closed
on model/dimension mismatch, and is rebuilt atomically rather than mutated online.

## Model, index, and host

- Model: `all-minilm:latest`, Ollama ID `1b226e2802db`, 22.6M-parameter F16 model,
  local download 45 MB (model card rounds to 46 MB), Apache-2.0.
- Measured vector dimension: 384. Model input is passed directly without unsupported
  query/document prefixes.
- Index: four allowlisted NASA documents, 202 chunks, 2.1 MB local Qdrant directory,
  schema version 2, `embedding_name=ollama:all-minilm`.
- Rebuild observed in 23.0 s on the B08 8 GB Intel host. No embedding request left
  loopback.

## Q01 retrieval comparison

`evaluation/run_b09_retrieval.py` fetched one shared approved corpus and evaluated the
same ten labeled Q01 retrieval questions against both indexes. Results are stored in
`reports/b09_retrieval_evaluation.json`.

| Retriever | Recall@5 | Support terms | p50 | p95 | Miss |
| --- | ---: | ---: | ---: | ---: | --- |
| local hashing v1 | 90% | 80% | 1.66 ms | 2.78 ms | R08 |
| Ollama all-minilm | 90% | 100% | 10.05 ms | 12.17 ms | R08 |

Both exceed the approved 85% Recall@5 threshold after applying a bounded two-chunks-
per-source diversity policy to prevent one long FAQ from saturating all five results.
The semantic replacement improves evidence-term coverage, but R08 remains documented
and overall Q01 remains `IN_REVIEW` for its other unmeasured release criteria.

Full backend tests and Ruff passed on 2026-11-06. Tech Lead review is still required
before `DONE`.
