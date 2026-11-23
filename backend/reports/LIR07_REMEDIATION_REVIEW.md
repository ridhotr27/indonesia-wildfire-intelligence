# LIR-07 remediation evidence

**Status:** IN_REVIEW  
**Date:** 2026-11-17  
**Scope:** development and shadow-validation partitions only; final holdout not consumed

## Outcome

The immutable 800-case candidate artifact is
`evaluation/lir07_semantic_lir01_dev_shadow_remediation_candidate_v9.json`. Compared with
the reproduced baseline, routing accuracy improved from 34.375% to 85.0%, macro-F1 from
0.3511 to 0.8850, analytics recall from 0.1056 to 0.6667, combined recall from 0.1667 to
1.0000, RAG recall from 0.6000 to 1.0000, and exact-operation accuracy from 0.2167 to
0.8000. Forbidden unsupported tool calls remained zero. Routing p50/p95 was 1.00/27.80 ms.

All 680 current-contract cases route and select operations exactly. All 120 remaining
errors are bounded-history cases: 40 single-province, 40 trend, and 40 multi-province
follow-ups. LIR-03 explicitly deferred the history request contract and requires these
requests to clarify. On the 480 supported single-turn cases, exact route and operation
accuracy is 100%; the all-corpus release gates still fail because the frozen labels expect
history execution. Labels and thresholds were not changed.

## Root causes and changes

- The original 32-example index did not cover broad bilingual paraphrase families and its
  B14 thresholds rejected most supported questions. A separate 196-example candidate uses
  reviewed development-only families, with disjoint development families for calibration.
- Deterministic precedence treated prose such as “satellite limitations” as a documentation
  request and treated generic `for ...` prose as an unsupported geography. Routing cues were
  narrowed to explicit requests and expanded for measured English, Indonesian, and mixed
  analytics/documentation phrasing.
- Indonesian prediction/injection/unsupported-measure denials were incomplete; they are now
  explicit and remain authoritative before similarity.
- Word-form ranking limits and cosine floating-point epsilon are normalized without relaxing
  LIR-04 validation.

Detailed confusion and per-intent/per-operation/language/source breakdowns are in
`evaluation/lir07_remediation_error_analysis_v1.json` (before) and
`evaluation/lir07_remediation_error_analysis_v3.json` (after). The family-separated example
set, calibration, and index remain versioned candidates; the existing default index and
deterministic rollback are unchanged.

## Remaining acceptance gap

Macro-F1 >= 0.90, analytics recall >= 0.80, and exact operation + required-entity accuracy
>= 0.95 cannot be reached across the frozen corpus without resolving history-dependent
entities. Doing so now would violate the approved LIR-03 no-history contract and executable
entity provenance rules. The next action is Tech Lead/API/privacy approval for the bounded
client history contract, followed by LIR-06/runtime integration and fresh contract tests;
otherwise acceptance criteria must explicitly score gated multi-turn cases separately.
