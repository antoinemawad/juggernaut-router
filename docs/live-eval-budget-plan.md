# Live Eval Budget Plan

Purpose: spend Fireworks credits deliberately.

## Stage 0: No-Credit Checks

```bash
python3 scripts/run_local_quality_gate.py
```

## Stage 1: Tiny Live Smoke

Goal: verify env vars, proxy URL, response schema, token fields, and logs.

Recommended shape:

- 1 model,
- 1 scenario per category,
- `original` prompt policy,
- low but safe `max_tokens`.

Approximate calls: 8.

## Stage 2: Model Slice

Goal: compare all allowed models on a tiny representative set.

Recommended shape:

- 5 models,
- 1 scenario per category,
- 1 prompt policy.

Approximate calls: 40.

## Stage 3: Hard-Scenario Slice

Goal: focus live spend on categories that affect the accuracy gate.

Recommended shape:

- selected candidate models,
- adversarial/exact-format scenarios,
- original plus one candidate prompt policy.

Approximate calls: 40-120 depending on candidates.

## Stage 4: Final Confirmation

Goal: validate selected configuration before official submission.

Recommended shape:

- selected model map,
- selected prompt policies,
- all local scenarios,
- no exploratory variants.

Approximate calls: scenario count routed remote.

## Stop Rules

- Run `python3 scripts/check_live_eval_env.py --print-models` before spending live calls.
- Stop live expansion if response schema/token fields look wrong.
- Stop if calls are not going through `FIREWORKS_BASE_URL`.
- Stop if prompt policy reduces accuracy.
- Stop if `max_tokens` truncates answers.
