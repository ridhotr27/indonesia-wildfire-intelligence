# LIR-03 conversation-history decision

**Decision:** DEFER public history support  
**Status:** DONE  
**Decision date:** 2026-11-15  
**Decision owner:** Tech Lead

True references such as “What about Aceh?” cannot be resolved safely from the current request, which contains only one message and UI filters. History is therefore necessary for true conversational carry-over, but it is not necessary for single-turn semantic understanding.

| Option | Decision |
|---|---|
| No history | Safest and zero contract cost, but follow-ups must clarify. Selected for the current scope. |
| Bounded client-supplied history | Recommended future design: stateless, explicit, auditable, and compatible with horizontal scaling. Requires coordinated API/privacy/FE approval and tests. |
| Server-managed history | Rejected: persistence, identity, retention, deletion, cross-session leakage, and operational complexity are unnecessary. |

Until separately approved, LIR-06 is limited to the current message plus validated UI context. Multi-turn acceptance cases remain gated and `history_resolution_enabled` remains false. No implicit memory or assistant-derived executable value is allowed.

If follow-ups are later approved, propose an optional additive `history` request field with at most four chronologically ordered prior turns and 4,000 total characters; roles limited to `user` and `assistant`; current message overrides history; assistant content is context only, never numeric evidence or tool authority. Reject unknown roles, malformed ordering, and exceeded bounds with the standard validation error. Do not emit or log raw history. Rollback is omission of the optional field plus disabling history resolution. FE-reader/BE-writer compatibility, old-client behavior, privacy review, synthetic fixtures, OpenAPI, and matching contract tests are mandatory before activation.

This record does not change the public API contract or runtime behavior.
