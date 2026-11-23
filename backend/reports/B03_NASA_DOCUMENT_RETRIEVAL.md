# B03 — NASA documentation indexing and retrieval

**Status:** Technical implementation complete; `IN_REVIEW`; Tech Lead approval required  
**Validation date:** 2026-10-21 UTC

## Delivered

- A versioned manifest of four official NASA FIRMS/VIIRS sources.
- HTTPS-only source fetching restricted to approved NASA hosts, including post-redirect validation, response-size bounds, timeouts, content hashes, and extraction for HTML/PDF/plain text.
- LangChain recursive chunking with deterministic chunk IDs and complete citation metadata: document ID, title, URL, published/retrieved dates, version, section, source hash, and chunk hash.
- Qdrant dense-vector storage supporting in-memory tests, an on-disk local path, or a server URL.
- Stable-ID upserts for idempotent re-indexing.
- A bounded retriever returning at most ten typed passages and marking every passage as untrusted content.
- Deterministic, local feature-hashing embeddings for cost-free development and tests. They are not the approved production embedding model.
- Unit tests for fetching, allowlists, redirect/size rejection, deterministic chunks, idempotent upserts, citation preservation, untrusted prompt-injection-like text, retrieval relevance fixtures, and query bounds.

The implementation is intentionally isolated from `/chat`. Connecting retrieval to the one bounded runtime agent belongs to B04 and remains dependent on B02, A01, and G2.

## Live NASA smoke test

The allowlisted CLI fetched all four manifest sources, extracted and indexed 201 chunks into an in-memory Qdrant collection, and ran two smoke queries. Exact source byte counts, SHA-256 hashes, top chunk IDs, and limitations are recorded in `backend/reports/b03_nasa_rag_smoke.json`.

- “What does fire radiative power mean?” returned the NASA active-fire attributes document first; the top chunk contained the fire-radiative-power field.
- “What are VIIRS confidence classes?” returned the NASA FIRMS FAQ first; the top chunk contained confidence guidance.

This confirms the acquisition/index/retrieval/citation path, not a release metric. Recall@5 and approved embedding selection remain Q01/G2 work.

## Verification

```bash
cd backend
.venv/bin/pip install -e '.[dev,rag]'
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/python -m wildfire_api.rag.cli \
  --location :memory: \
  --query "What does fire radiative power mean?" \
  --query "What are VIIRS confidence classes?"
```

Observed after implementation: 27 backend tests passed, Ruff passed, and the live four-source smoke command completed successfully. No OpenAI key, paid model, remote Qdrant service, or LLM was used.

## Remaining decisions and limitations

1. G2 must approve the production embedding provider/model and Qdrant local-versus-hosted deployment.
2. B04 must add the bounded LangGraph retrieval tool and response composition; B03 does not change the draft API.
3. Q01 must create the reviewed documentation question set and report measured Recall@5/citation support.
4. Live content can change at a stable NASA URL. Every index run records the retrieved timestamp and source hash; changes must be reviewed rather than silently treated as the same corpus version.
5. PDF/HTML extraction preserves citation identity but does not promise perfect visual reading order for every document revision.
