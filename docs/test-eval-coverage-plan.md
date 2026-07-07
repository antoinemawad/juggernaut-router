# Test and Eval Coverage Plan

Purpose: keep tests and evaluations expanding with the routing architecture. Any new routing feature must add measurable coverage.

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
- `risk_components`
- `output_constraints`
- `expected_route`
- `remote_mode_hint`
- `prompt`
- `expected_keywords`
- `expected_answer`
- `scoring_notes`

Validate scenario coverage with:

```bash
python3 scripts/check_eval_coverage.py
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
- errors.

## Required Test Types

- Unit tests for classifier risk components.
- Unit tests for validators.
- Unit tests for route decisions.
- Unit tests for answer normalization.
- Mock Fireworks tests for timeouts, HTTP errors, invalid JSON, and missing usage.
- Config sweep tests for conservative/balanced/aggressive modes.
- Coverage tests using `scripts/check_eval_coverage.py`.
- Docker fixture tests with mounted `/input` and `/output`.

## Promotion Rule

A router or eval change is not ready to become default unless:

1. `scripts/check_eval_coverage.py` passes.
2. Local smoke test passes.
3. Router config sweep produces a report.
4. Model matrix mock mode produces a report.
5. Any affected dimension has positive and adversarial coverage.
6. Logs contain enough fields to reproduce the routing decision.
