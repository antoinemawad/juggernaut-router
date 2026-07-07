# Elite Routing Plan

Purpose: define the highest-leverage routing architecture for Track 1 while keeping the submitted runtime simple, CPU-safe, and measurable.

## Core Principle

The router must prove a task is safe for local handling before spending zero remote tokens. If local proof is weak, the router should use Fireworks through `FIREWORKS_BASE_URL`.

This means the router is a risk engine, not just a category classifier.

## Multi-Stage Decision Flow

Every task should pass through these stages:

1. Prompt intent and constraint parsing.
2. Answer-shape detection.
3. Category detection.
4. Difficulty and risk scoring.
5. Local solvability check.
6. Local solver attempt.
7. Local proof generation.
8. Category-specific validation.
9. Route decision.
10. Minimal remote prompt construction when needed.
11. Fireworks mode/model/prompt selection when needed.
12. Local verification of remote output.
13. One bounded retry only when verification fails for fixable reasons.
14. Final answer normalization.
15. Router decision logging.

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
- `intent`
- `answer_shape`
- `constraints`
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
- `retry_count`
- `retry_reason`
- `verification_passed`
- `verification_notes`
- `failure_type`
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
- intent-parser examples for every answer shape.
- remote-verification examples: invalid JSON, invalid code, overlong answer, markdown when forbidden, empty answer, truncation.
- one-retry examples where the first answer fails format verification and the retry should fix it.
- failure-taxonomy examples for wrong category, local overconfidence, weak validator, weak remote model, loose prompt, low `max_tokens`, and output format failure.

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
- per-answer-shape breakdown,
- per-constraint breakdown,
- retry count and retry success rate,
- verification failure rate,
- failure taxonomy breakdown.

## Promotion Rule

A routing change can become a default only when:

1. It meets or improves the configured accuracy target.
2. It reduces tokens or improves safety/latency without accuracy loss.
3. It has scenario logs and a markdown report.
4. It passes adversarial routing tests.
5. `python3 scripts/check_eval_coverage.py` passes after any scenario or routing-dimension change.
6. It has intent/constraint/answer-shape coverage when the change touches parsing, prompting, verification, or normalization.
7. It preserves compliance with `FIREWORKS_BASE_URL`, `ALLOWED_MODELS`, Docker IO, and no-secret rules.

## Prompt Intent IR

The router should compile each prompt into a small internal representation before deciding where to send it.

Example:

```json
{
  "category": "mathematical_reasoning",
  "intent": "compute_final_price",
  "answer_shape": "number",
  "constraints": ["answer_only", "exact_numeric"],
  "entities": {"price": 80, "discount_percent": 25},
  "risk_score": 0.18
}
```

The IR is local-only implementation detail. It should not be written to `/output/results.json`, but it should appear in development/eval decision logs.

## Constraint Extraction

Constraints should be extracted before solving or prompting.

Required constraint types:

- `answer_only`
- `no_explanation`
- `one_sentence`
- `exact_word_count`
- `json_only`
- `code_only`
- `label_only`
- `label_plus_reason`
- `entity_labels`
- `exact_numeric`
- `rounding_required`
- `include_corrected_code`

Most remote prompt templates should be built from constraints, answer shape, category, and risk mode instead of a single generic wrapper.

## Answer Shapes

The router should classify expected answer shape:

- `label`
- `number`
- `short_text`
- `summary`
- `entity_list`
- `json`
- `code`
- `corrected_code`
- `reasoning_answer`

Answer shape controls local validators, remote mode, prompt policy, `max_tokens`, and output normalization.

## Local Proof System

Local solvers should attach proof metadata:

- math: parsed quantities, operations, recomputed result.
- NER: matched spans and labels.
- code: generated/corrected code plus `ast.parse` result when Python.
- summary: word count, sentence count, key terms kept.
- sentiment: polarity hits and polarity gap.
- logic: relation graph or supported puzzle pattern.

No proof, no local acceptance.

## Remote Prompt Builder

Remote prompts should be minimal but constraint-aware.

Inputs:

- original task text,
- category,
- answer shape,
- constraints,
- remote mode,
- risk score,
- `max_tokens`.

Rules:

- preserve the original task text unless metrics prove safe compaction.
- use the smallest wrapper that preserves accuracy.
- prefer answer-only instructions only when constraints and evals support them.
- use format-strict prompts for JSON, exact word count, labels, code-only, and no-explanation constraints.

## Remote Output Verification and Retry

After Fireworks returns, verify locally before final output.

Verification checks:

- JSON parses when `json_only`.
- Python code parses when answer shape is `code` or `corrected_code`.
- exact word count passes when requested.
- label is one of the allowed labels.
- entity labels are present when requested.
- no markdown fences when forbidden.
- answer is nonempty and not obviously truncated.

Retry policy:

- at most one retry.
- retry only for fixable output-shape failures: invalid JSON, invalid code syntax, exact-format failure, empty answer, truncation, or markdown fence violation.
- retry must use a stricter remote mode/prompt.
- retry metadata must be logged.

## Failure Taxonomy

Every failed eval row should be tagged with one or more failure types:

- `wrong_category`
- `local_overconfidence`
- `validator_too_weak`
- `remote_model_weak`
- `prompt_too_loose`
- `max_tokens_too_low`
- `output_format_failure`
- `timeout`
- `http_error`
- `invalid_remote_response`
- `normalization_error`
