# LIR-08 NASA RAG Optimization Review

**Status:** DONE  
**Date:** 2026-11-17

## Selected implementation

- Published `data/qdrant-lir08` as a separate 210-chunk, schema-v2 `ollama:all-minilm` index using `structure-title-1400-200-v1`; the B09 index remains unchanged at `data/qdrant` for rollback.
- Selected bounded dense+BM25 reciprocal-rank fusion over at most 20 candidates and 500 approved chunks. Lexical failure returns to dense retrieval.
- Added a reviewed NASA-topic/evidence floor, English/Indonesian term expansion, two-chunks-per-source diversity, and deterministic insufficient-evidence abstention.
- Added chunk-profile compatibility validation and manifest metadata. No online rebuild or arbitrary user-derived metadata filtering occurs.
- Preserved Ollama answer generation and added rejection when a model selects a supplied passage unrelated to its answer.

## Measured development evidence

The consumed Q01 ten-question documentation set was used only as development/regression data; the final holdout remained sealed.

| Profile | Recall@5 | MRR | nDCG@5 | Support terms | p50 / p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| B09 recursive dense | 90% | 0.7833 | 0.6543 | 100% | 9.87 / 11.62 ms |
| Structure/title dense | 100% | 0.8167 | 0.7657 | 100% | 10.01 / 11.30 ms |
| Selected structure/title hybrid | 100% | 1.0000 | 0.8671 | 100% | 41.78 / 47.87 ms |

All three insufficient-evidence probes changed from five dense passages to zero selected-profile passages. The selected-index evaluation recorded 111,681,536 bytes peak process RSS and a 1,299,805-byte index. A reranker was not added because hybrid retrieval removed the labeled miss without a new dependency. Metadata filtering was not adopted because the current query contract supplies no reviewed server-side document filter.

## Verification and rollback

- Focused RAG/citation tests: 27 passed.
- B03/B04/B06-B09/LIR-09/API regressions: 103 passed.
- Full backend suite: 469 passed, 1 existing opt-in skip.
- Ruff: passed.

Rollback sets `WILDFIRE_QDRANT_PATH=data/qdrant`, `WILDFIRE_RAG_CHUNKING_PROFILE=recursive-character-1400-200-v1`, and `WILDFIRE_RAG_RETRIEVAL_PROFILE=dense`.

## Limitations

The relevance set has only ten documentation questions; answer faithfulness was not inferred from retrieval metrics. Live NASA HTML changed since B09, so the new index records fresh source hashes. Deployment and release remain unauthorized.

## Tech Lead final acceptance — 2026-11-17

Approved `DONE`. The versioned profile, reproducible evaluation artifacts, citation
grounding, insufficient-evidence behavior, compatibility checks, and dense rollback meet
LIR-08 acceptance. Independent focused and full-suite reruns passed. The small consumed
development set remains a documented limitation; no answer-quality claim or final-holdout
result is inferred from it.
