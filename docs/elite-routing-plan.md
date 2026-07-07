# Elite Routing Plan

Purpose: define the highest-leverage routing architecture for Track 1 while keeping the submitted runtime simple, CPU-safe, and measurable.

## Core Principle

The router must prove a task is safe for local handling before spending zero remote tokens. If local proof is weak, the router should use Fireworks through `FIREWORKS_BASE_URL`.

This means the router is a risk engine, not just a category classifier.

## Multi-Stage Decision Flow

Every task should pass through these stages:

1. Category detection.
2. Difficulty and risk scoring.
3. Local solvability check.
4. Local solver attempt.
5. Category-specific validation.
6. Route decision.
7. Fireworks mode/model/prompt selection when needed.
8. Final answer normalization.
9. Router decision logging.

The final answer path must remain:

`/input/tasks.json -> local risk engine -> local answer or Fireworks fallback -> normalized answer -> /output/results.json`

## Risk Score

Each task receives a composite risk score. The exact weights should remain configurable and tuned through tests.

Risk components:

- ambiguity: unclear intent, mixed labels, underspecified output.
- reasoning_depth: multi-step math, logic chains, hidden constraints.
- format_strictness: JSON-only, exact word count, exact label schema, no explanation.
- code_risk: code generation, debugging, hidden tests, subtle syntax/runtime behavior.
- factual_freshness: current facts, niche facts, or facts not in local stable rules.
- local_validator_weakness: solver answer cannot be independently checked.

Routing policy:

- low risk plus strong validator: local.
- medium risk: conservative local only if validator is strong; otherwise concise Fireworks.
- high risk: Fireworks accuracy mode.

## Local Answer Contract

Local solvers should return structured evidence, not plain strings.

Required fields:

- `answer`
- `confidence`
- `category`
- `evidence`
- `validator_passed`
- `risk_flags`
- `failure_reason`

The agent may accept a local answer only when:

- category confidence passes the configured threshold,
- solver confidence passes the configured threshold,
- validator passes,
- risk score is below the selected router mode threshold,
- output normalization preserves requested format.

## Category Validators

Validators are the main defense against dangerous zero-token answers.

| Category | Validator Goals | Local Acceptance Rule |
| --- | --- | --- |
| Factual knowledge | Stable known facts only; reject freshness/niche/ambiguous facts | Local only for explicitly supported stable facts |
| Mathematical reasoning | Parse expression, recompute result, detect multi-step wording | Local only when all operations are parsed and checked |
| Sentiment classification | Detect clear polarity; reject sarcasm, mixed sentiment, or explanation-heavy requests | Local only for strong polarity gap |
| Text summarisation | Check word/sentence limits and key-term preservation | Local only for simple extractive or validated constrained summaries |
| Named entity recognition | Validate requested labels, entity spans, dates, and schema | Local only when all required entities are found confidently |
| Code debugging | Syntax-check corrected code when possible; reject subtle/semantic bugs | Local only for tiny deterministic patterns |
| Logical reasoning | Validate relation graph or supported puzzle type | Local only for simple supported relation patterns |
| Code generation | Syntax-check generated code and enforce exact requested function name | Local only for tiny templates |

## Fireworks Modes

Fireworks is not one fallback. The router should choose a mode.

| Mode | Use When | Token Posture |
| --- | --- | --- |
| `remote_concise` | Low/medium risk, simple answer expected | Minimal wrapper, tight `max_tokens` |
| `remote_accuracy` | Hard math, logic, factual ambiguity, judge-risky tasks | Stronger instructions, higher `max_tokens` |
| `remote_format_strict` | JSON-only, labels, exact word count, no explanation | Format-focused prompt, strict normalization |
| `remote_code` | Code generation/debugging | Code-specific prompt/model, syntax-aware post-check |

Each mode must select only from runtime `ALLOWED_MODELS`.

## Router Modes for Submissions

Multiple official submissions become meaningful when the router mode is configurable.

| Router Mode | Local Threshold | Fireworks Bias | Purpose |
| --- | ---: | --- | --- |
| `conservative` | highest | more Fireworks | Protect accuracy gate |
| `balanced` | medium-high | measured hybrid | Main candidate |
| `aggressive` | lower but still validator-gated | fewer Fireworks | Token-saving probe |

Each submission should change one major variable at a time: router mode, category model map, prompt policy, `max_tokens`, or local solver coverage.

## Required Decision Log Fields

Every local experiment and Docker fixture run should produce inspectable router decisions. Logs must never include secrets.

Required fields:

- `task_id`
- `category`
- `category_confidence`
- `risk_score`
- `risk_components`
- `local_answer_present`
- `local_confidence`
- `validator_passed`
- `validator_notes`
- `route`
- `route_reason`
- `remote_mode`
- `selected_model`
- `prompt_policy`
- `max_tokens`
- `latency_ms`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `final_answer_length`
- `error`

## Testing Matrix

All routing scenarios must be testable with metrics.

The canonical scenario coverage rule is maintained in `docs/test-eval-coverage-plan.md`.

Minimum scenario classes:

- simple safe local examples for all 8 categories where local coverage is intended.
- adversarial examples for all 8 categories.
- exact-format examples: JSON-only, one-word answer, exact word count, no explanation.
- failure-mode examples: timeout, HTTP error, invalid Fireworks response, missing env vars.
- prompt-policy examples: original vs compact vs answer-only.
- router-mode examples: conservative vs balanced vs aggressive.
- model-map examples across all allowed models.

Minimum metrics:

- pass rate,
- average score,
- total and average remote tokens,
- local route rate,
- Fireworks route rate,
- fallback/error rate,
- latency,
- per-category breakdown,
- per-router-mode breakdown,
- per-prompt-policy breakdown.

## Promotion Rule

A routing change can become a default only when:

1. It meets or improves the configured accuracy target.
2. It reduces tokens or improves safety/latency without accuracy loss.
3. It has scenario logs and a markdown report.
4. It passes adversarial routing tests.
5. `python3 scripts/check_eval_coverage.py` passes after any scenario or routing-dimension change.
6. It preserves compliance with `FIREWORKS_BASE_URL`, `ALLOWED_MODELS`, Docker IO, and no-secret rules.
