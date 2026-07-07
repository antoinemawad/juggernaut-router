# Test and Eval Coverage Plan

Purpose: keep tests and evaluations expanding with the routing architecture. Any new routing feature must add measurable coverage.

Field definitions are maintained in `docs/eval-field-glossary.md`.

## Standing Rule

When the router gains a new decision dimension, the test/eval system must gain:

- scenario metadata for that dimension,
- at least one positive scenario,
- at least one adversarial or fail-safe scenario,
- JSONL log fields,
- markdown report aggregation or inspection path,
- checklist coverage before submission.

## Required Scenario Metadata

Every scenario should include:

- `task_id`
- `category`
- `difficulty`
- `scenario_class`
- `intent`
- `answer_shape`
- `constraints`
- `risk_components`
- `output_constraints`
- `expected_route`
- `remote_mode_hint`
- `verifier`
- `retry_policy`
- `failure_taxonomy`
- `prompt`
- `expected_keywords`
- `expected_answer`
- `scoring_notes`

Validate scenario coverage with:

```bash
python3 scripts/check_eval_coverage.py
python3 scripts/check_eval_coverage.py eval/golden_tier_2_regression.jsonl --profile tier
python3 scripts/check_eval_coverage.py eval/golden_tier_3_adversarial.jsonl --profile tier
```

Run all current local non-Docker quality checks with:

```bash
python3 scripts/run_local_quality_gate.py
```

## Coverage Dimensions

Required categories:

- factual knowledge
- mathematical reasoning
- sentiment classification
- text summarisation
- named entity recognition
- code debugging
- logical/deductive reasoning
- code generation

Required risk components:

- ambiguity
- reasoning depth
- format strictness
- code risk
- factual freshness
- local validator weakness

Required scenario classes:

- safe local candidate
- remote candidate
- adversarial
- exact format

Required remote modes:

- `remote_concise`
- `remote_accuracy`
- `remote_format_strict`
- `remote_code`

Required answer shapes:

- `label`
- `number`
- `short_text`
- `summary`
- `entity_list`
- `code`
- `corrected_code`

Required constraints:

- `answer_only`
- `no_explanation`
- `one_sentence`
- `exact_word_count`
- `code_only`
- `label_plus_reason`
- `entity_labels`
- `exact_numeric`
- `include_corrected_code`

Required verifiers:

- `label_set`
- `numeric_exact`
- `summary_constraints`
- `entity_labels`
- `python_syntax`
- `word_count`
- `keyword_coverage`

Required failure taxonomy coverage:

- `wrong_category`
- `local_overconfidence`
- `validator_too_weak`
- `remote_model_weak`
- `prompt_too_loose`
- `max_tokens_too_low`
- `output_format_failure`

Required production-readiness coverage:

- malformed input file,
- non-array input JSON,
- missing `task_id`,
- missing `prompt`,
- non-string prompt,
- missing Fireworks env vars,
- Fireworks timeout,
- Fireworks HTTP error,
- Fireworks invalid JSON response,
- Fireworks response missing `choices`,
- Fireworks response missing `usage`,
- disallowed model,
- normalization of empty/non-string answers,
- optional `ROUTER_LOG_PATH` JSONL telemetry,
- batch deadline manager with fake-clock tests,
- near-deadline retry suppression,
- valid output when deadline is almost exhausted,
- per-call remote timeout below the 30-second response ceiling,
- bounded remote worker count,
- Docker mounted `/input` and `/output`.

Required router modes:

- conservative
- balanced
- aggressive

## Required Logging Expansion

Every eval row should include scenario metadata plus runtime decision data when available:

- category,
- difficulty,
- scenario class,
- risk components,
- output constraints,
- expected route,
- remote mode hint,
- intent,
- answer shape,
- constraints,
- verifier,
- retry policy,
- failure taxonomy,
- actual route,
- route reason,
- router mode,
- prompt policy,
- selected model,
- `max_tokens`,
- latency,
- token fields,
- pass/fail,
- score,
- elapsed batch time,
- deadline skips or retry suppression,
- errors.

## Required Test Types

- Unit tests for classifier risk components.
- Unit tests for validators.
- Unit tests for route decisions.
- Expected-route assertion tests: safe local candidates should not call Fireworks unless validation fails; risky, ambiguous, exact-format, current-fact, and code-risk tasks should route to the planned remote mode.
- Unit tests for answer normalization.
- Unit tests for input validation and batch continuation.
- Unit tests for config/env parsing.
- Unit tests for optional telemetry with no secrets.
- Mock Fireworks tests for timeouts, HTTP errors, invalid JSON, and missing usage.
- Deadline tests for remaining time, safety margin, retry suppression, and valid output under near-timeout conditions.
- Bounded concurrency tests for remote-needed tasks.
- Config sweep tests for conservative/balanced/aggressive modes.
- Regression tier tests using `eval/golden_tier_2_regression.jsonl`.
- Adversarial tier tests using `eval/golden_tier_3_adversarial.jsonl`.
- Format-trap tests for exact numeric, exact word count, code-only, one-word, and entity-label outputs.
- Remote output simulation tests for verbose, truncated, malformed, and wrong-format Fireworks answers.
- Route stability tests that rerun the same dataset and flag unintended route changes.
- Baseline comparison tests with `scripts/compare_eval_reports.py`.
- Coverage tests using `scripts/check_eval_coverage.py`.
- Docker fixture tests with mounted `/input` and `/output`.

## Promotion Rule

A router or eval change is not ready to become default unless:

1. `scripts/check_eval_coverage.py` passes.
2. Tier coverage checks pass for regression and adversarial datasets.
3. Local smoke test passes.
4. Router config sweep produces a report.
5. Model matrix mock mode produces a report.
6. Any affected dimension has positive and adversarial coverage.
7. Logs contain enough fields to reproduce the routing decision.
8. Candidate reports are compared against the previous baseline before promotion.
9. Production-readiness failure modes pass or are explicitly documented as accepted risks.

Detailed category expectations live in `docs/category-playbooks.md`.
Accuracy and promotion gates live in `docs/accuracy-gates.md`.
