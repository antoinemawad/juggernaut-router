# Judge Interview Prep

Purpose: prepare answers that match the actual implementation and documented evidence.

Do not overclaim planned features. Label features as implemented, tested, planned, or rejected.

## Core Questions

### Why this architecture?

Answer using:

- accuracy gate first,
- token ranking second,
- local-first classification,
- validator-gated local answers,
- Fireworks fallback through the judging proxy,
- model/prompt choices backed by reports.

Evidence:

- `docs/architecture.md`
- `docs/elite-routing-plan.md`
- latest `eval_runs/*.md`

### Why this model?

Answer using:

- allowed model matrix,
- best accuracy model by category,
- cheapest passing model by category,
- runtime validation against `ALLOWED_MODELS`.

Evidence:

- `docs/model-matrix-evaluation.md`
- latest model matrix report.

### What alternatives were tested?

Use:

- always-Fireworks baseline,
- strict/balanced/aggressive hybrid configs,
- prompt policies: original, compact, answer-only,
- per-category model choices.

Evidence:

- `eval/router_config_sweep.py`
- `eval/model_matrix.py`
- `docs/experiments.md`

### What failed?

Prepare concrete examples from reports:

- local overconfidence,
- weak validator,
- output format failure,
- max_tokens too low,
- prompt too loose,
- model weak for category.

Evidence:

- JSONL notes/errors,
- `docs/manual-verification-log.md`,
- final failure analysis section in presentation.

### What is innovative?

Answer:

- risk-engine routing,
- local proof before zero-token answers,
- remote modes by output shape and risk,
- submission optimization loop using official feedback carefully.

### What is the biggest risk?

Answer:

- hidden benchmark variants may expose unsupported local cases,
- exact official accuracy threshold unknown,
- final GPU access for local LLM inference not confirmed,
- token savings are useful only after accuracy gate passes.

### What would you improve with more time?

Answer:

- broader adversarial scenario set,
- stronger validators,
- live model matrix across more scenarios,
- optional CPU-safe tiny local classifier/model if it fits image/runtime constraints,
- richer post-Fireworks verification.

### What role did AI tools play?

Answer honestly:

- used for architecture planning, code scaffolding, documentation, and test design,
- final behavior is controlled by code, env vars, validation, and reproducible evals.

## Claim Discipline

Before the interview/demo, mark each major claim:

| Claim | Status | Evidence |
| --- | --- | --- |
| Local-first routing | planned / implemented | TBD |
| Fireworks base URL compliance | implemented | `app/fireworks_client.py` |
| Model matrix comparison | implemented | latest report |
| Router config sweep | implemented | latest report |
| Risk engine | planned / partial | `docs/elite-routing-plan.md` |
| Local proof validators | planned / partial | TBD |
