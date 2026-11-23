# B14 semantic intent routing implementation plan

Date: 2026-11-15

## Authorization and baseline

The Tech Lead's direct instruction to implement B14 authorizes work to proceed while B12 and
B13 remain independently `IN_REVIEW`; it does not approve those tickets. The frozen comparison
baseline is the current deterministic B11/B12/B13 router and its committed corpora.

## Bounded design

1. Keep the existing single LangGraph runtime and deterministic denial/exact-route precedence.
2. Add a separate, versioned Qdrant collection of reviewed intent examples using the already
   approved local `ollama:all-minilm` embedding profile. Never share the NASA-document collection.
3. Invoke semantic matching only for otherwise-unrecognized messages. Return one allowlisted
   intent candidate or no candidate; the existing resolver must still validate province/date slots.
4. Permit only fixed existing analytics, NASA RAG, combined, or abstention paths. Never derive SQL,
   numeric values, provinces, dates, or arbitrary tool arguments from embeddings.
5. Ship disabled by default with `shadow` and `guarded` modes. Fail closed on a missing or
   incompatible intent index while preserving safe deterministic routes.
6. Add offline index tooling, compatibility manifests, reviewed examples, evaluation tooling,
   focused security/integration tests, and rollback instructions.

## Evaluation gates

- Preserve 100% deterministic denial and existing B11/B13 corpus agreement.
- Measure semantic intent accuracy, per-intent precision/recall/F1, unsupported false accepts,
  generic-fallback reduction, slot/operation correlation, and English/Indonesian subsets.
- Measure match and end-to-end routing p50/p95 latency using the available local profile.
- Do not claim the 95% release threshold, live all-minilm performance, Q01 completion, or `DONE`
  unless the required local model/index and held-out evaluation actually run and pass.

## Rollback

Set semantic routing to `disabled`; deterministic routing remains unchanged. Index rollback selects
a previously compatible versioned manifest and never mutates the NASA RAG collection.
