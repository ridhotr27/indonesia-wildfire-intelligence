# B08 — local Ollama grounded generation review

## Outcome

B08 is technically complete and `IN_REVIEW`. FastAPI now performs bounded local
generation after Qdrant retrieval and validates every model-supplied passage number
before constructing citations. The provider is disabled by default, accepts only HTTP
loopback URLs, and has no cloud fallback.

## Selected model and tested machine

- Model: `qwen2.5:1.5b`, Ollama ID `65ec06548149`, Q4_K_M, 986 MB.
- License: Apache-2.0. The Ollama model card advertises up to 128K context; this
  application intentionally bounds retrieved input to 3,000 characters and output to
  192 tokens.
- Ollama: 0.40.15.
- Tested host: Intel Core i5 MacBookPro15,2, four logical CPUs, 8 GB RAM, x86_64,
  CPU-only execution.
- Boundary: browser → FastAPI → loopback Ollama. Prompts, passages, and responses stay
  on the local machine and are not logged.

## Verification

- FRP live response: defined pixel-integrated fire radiative power, reported MW, one
  validated NASA citation, `usage.llm_calls=1`; observed cold request 19.25 s.
- VIIRS confidence live response: stated low, nominal, and high classes, one validated
  NASA citation, `usage.llm_calls=1`; observed warm request 8.20 s.
- The incomplete-output validator rejects the earlier weak-model result "fire
  radiative power" instead of displaying it as a grounded answer.
- Full backend suite passed with one opt-in skip; Ruff passed on 2026-11-06.

These are local observations, not production latency/capacity claims. Tech Lead review
is still required before `DONE`.
