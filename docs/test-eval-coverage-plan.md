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

Assert planned routes for the current recommended config with:

```bash
python3 scripts/check_expected_routes.py --config strict_hybrid
```

This checks both `expected_route` and `remote_mode_hint`, then writes route, remote-mode, and prompt-policy evidence to `eval_runs/expected_routes_latest.json` and `eval_runs/expected_routes_latest.md`.

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
- local proof budget enforcement,
- local cross-check timeout/fallback behavior,
- batch deadline manager with fake-clock tests,
- near-deadline retry suppression,
- agent-level near-deadline fallback before Fireworks payload construction,
- valid output when deadline is almost exhausted,
- per-call remote timeout below the 30-second response ceiling,
- bounded remote worker count,
- static submission guard for forbidden Fireworks URL hardcoding, tracked secrets/env files, Dockerfile scope, and ignore rules,
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
- local proof layers passed/failed,
- local proof elapsed time,
- trap guard findings,
- cross-check result,
- router mode,
- prompt policy,
- selected model,
- `max_tokens`,
- task timing fields: `task_elapsed_ms`, `classification_elapsed_ms`, `constraint_extraction_elapsed_ms`, `local_solver_elapsed_ms`, `validation_elapsed_ms`, `local_proof_elapsed_ms`, `trap_guard_elapsed_ms`, `cross_check_elapsed_ms`, `remote_elapsed_ms`, and `normalization_elapsed_ms`,
- batch timing fields: `batch_elapsed_ms_at_start`, `batch_elapsed_ms_at_finish`, and `remaining_budget_ms`,
- token fields,
- size and token estimates: `prompt_char_count`, `prompt_token_estimate`, `remote_prompt_token_estimate`, `answer_char_count`, `answer_token_estimate`, `completion_tokens`, and `total_tokens` when available,
- pass/fail,
- score,
- elapsed batch time,
- deadline skips or retry suppression,
- errors.

## Required Test Types

- Current Phase 2 implementation includes `tests/test_phase2_router.py` for classifier coverage, risk components, local no-Fireworks routing, stable CPU/GPU local factual routing, risky remote routing, remote mode selection, preferred model selection, classifier-before-remote ordering, remote code/numeric/label/entity cleanup, proof-budget rejection, agent-level near-deadline fallback behavior before Fireworks payload construction, ambiguous NER rejection, exact-summary rejection, sarcasm rejection, multi-step math rejection, incomplete logic rejection, nontrivial-code rejection, NER/code/corrected-code cross-check failures, real-router sweep rows, full-fixture expected-route and remote-mode assertions, route-match checks, ranking-order checks, and verifier-aware eval scoring.
- Unit tests for classifier risk components.
- Unit tests for validators.
- Unit tests for constraint extraction.
- Unit tests for trap guards: sarcasm, mixed sentiment, incomplete logic, multi-step math, current/live factual claims, ambiguous entities, and nontrivial code.
- Unit tests for cheap cross-checkers: math recomputation, relation graph consistency, Python syntax, tiny code micro-tests, NER entity-count checks, and summary word counts where applicable.
- Unit tests for local proof budget enforcement.
- Unit tests for route decisions.
- Expected-route assertion tests: safe local candidates should not call Fireworks unless validation fails; risky, ambiguous, exact-format, current-fact, and code-risk tasks should route to the planned remote mode.
- Unit tests for answer normalization.
- Unit tests for input validation and batch continuation.
- Unit tests for config/env parsing.
- Unit tests for optional telemetry with no secrets.
- Unit tests that task-level telemetry includes timing metrics for local, remote, fallback, and error paths.
- Unit tests that telemetry overhead is optional and never changes official `/output/results.json`.
- Optional local model tests before implementation: disabled mode preserves current behavior, timeout/failure falls back safely, local-model advice cannot bypass proof gates, and Docker image/startup/runtime budgets remain valid.
- Local inference impact evals, if implemented: `no_local_inference_final_router`, `local_inference_for_development_only`, `local_inference_as_route_suggester`, `local_inference_as_format_checker`, and `local_inference_as_final_answer_generator`.
- Gemma-specific evals: selected/skipped/escalated counts, Gemma accuracy by category, Gemma token usage versus fallback models, and Gemma cheapest-sufficient categories.
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
