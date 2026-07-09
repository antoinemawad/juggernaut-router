# Accuracy Gates

Purpose: prevent token optimization from weakening the accuracy gate. Passing accuracy comes first; token savings matter only after the gate is satisfied.

## Dataset Tiers

- `tier_1_smoke`: small local harness fixture in `local_test/input/tasks.json`; validates IO shape and basic batch execution.
- `tier_2_regression`: `eval/golden_tier_2_regression.jsonl`; category-balanced scenarios that should stay stable as the router changes.
- `tier_3_adversarial`: `eval/golden_tier_3_adversarial.jsonl`; ambiguity, exact-format, sarcasm, incomplete-information, and unsafe-local traps.
- `model_matrix_core`: `eval/model_matrix_scenarios.jsonl`; full metadata coverage for model, prompt-policy, remote-mode, and router-mode comparisons.

## Promotion Gates

A router configuration can be promoted only if:

1. IO validation passes and `/output/results.json` keeps the official shape.
2. Core eval coverage passes with `python3 scripts/check_eval_coverage.py`.
3. Tier eval coverage passes for regression and adversarial files.
4. The candidate equals or beats the baseline pass rate before token usage is considered.
5. The candidate uses fewer recorded tokens than always-Fireworks at the same or better score.
6. No tier 3 adversarial scenario is accepted locally unless the local verifier can prove the answer.
7. Every new failure is categorized in the failure taxonomy and converted into a validator, prompt, model-map, or route-rule decision.

## Initial Numeric Targets

These thresholds are local planning defaults, not official thresholds:

- tier 1 smoke: 100% valid output shape.
- tier 2 regression: at least 0.90 average score before final submission.
- tier 3 adversarial: no unsafe local acceptances; at least 0.80 average score before token tuning.
- router sweep: final candidate must beat always-Fireworks token usage while matching or improving score.
- live mini matrix: only run on selected high-value slices and promote settings by score first, token usage second.

Keep these configurable because the official accuracy threshold is not published in the current local guide material.

## A/B Promotion Rule

When comparing two configs:

- compare on the same dataset and same prompt policy set,
- change one major variable at a time,
- record JSONL report paths in `docs/experiments.md`,
- use `scripts/compare_eval_reports.py` for score/token deltas,
- promote only if the candidate has no new category regression or the regression is intentionally accepted and documented.

## Submission Feedback Rule

Official submissions are scarce but useful. Use them as measured feedback:

- submit only after local quality gate passes,
- record each attempt in `docs/official-submission-log.md`,
- change one major variable between attempts,
- roll back a candidate if official accuracy falls or token use rises without accuracy benefit,
- preserve the exact Docker tag and commit SHA for any strong result.
