# Model Matrix Evaluation

Purpose: test each allowed Track 1 model across all eight task categories, log results, and make model/category routing decisions showable.

## Allowed Models

- `minimax-m3`
- `kimi-k2p7-code`
- `gemma-4-31b-it`
- `gemma-4-26b-a4b-it`
- `gemma-4-31b-it-nvfp4`

Runtime rule: live experiments must still validate against `ALLOWED_MODELS` and all Fireworks calls must go through `FIREWORKS_BASE_URL`.

## Goal

Build an evidence table that answers:

- Which model is best for each task category?
- Which model is cheapest among models that meet the accuracy target?
- Which categories need Fireworks accuracy mode?
- Which categories can be safely handled locally before Fireworks?
- Which prompt and `max_tokens` settings reduce tokens without hurting correctness?
- Which prompt policy is best: original, compact, or answer-only?

The output should be easy to show in the README, slides, and final submission explanation.

## Test Matrix

Each live matrix run should cover:

- 5 allowed models.
- 8 Track 1 categories.
- Multiple scenarios per category.
- At least one easy, medium, and hard prompt per category before final tuning.
- At least one formatting-constrained example per relevant category.
- At least one adversarial/ambiguous example per risky category.

Minimum useful matrix:

`5 models * 8 categories * 3 scenarios = 120 Fireworks calls`

Recommended final matrix:

`5 models * 8 categories * 8-12 scenarios = 320-480 Fireworks calls`

Because credits are limited, start with mock and small live runs, then expand only after the harness is stable.

## Scenario Dataset Requirements

Each scenario should include:

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
- `expected_answer` when deterministic
- `expected_keywords` for approximate scoring
- `scoring_notes`
- optional difficulty metadata: `easy`, `medium`, `hard`
- optional output constraint metadata: `json`, `one_sentence`, `code_only`, `label_plus_reason`, etc.

Scenario categories must match Track 1:

- `factual_knowledge`
- `mathematical_reasoning`
- `sentiment_classification`
- `text_summarisation`
- `named_entity_recognition`
- `code_debugging`
- `logical_deductive_reasoning`
- `code_generation`

## Required Log Fields

Every model/scenario row should be JSONL and include:

- `run_id`
- `timestamp`
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
- `model`
- `prompt_policy`
- `prompt_chars`
- `prompt_tokens`
- `completion_tokens`
- `total_tokens`
- `latency_ms`
- `passed`
- `score`
- `answer`
- `expected_answer`
- `notes`
- `error`

Future live runs should also add when available:

- `finish_reason`
- `http_status`
- `retry_count`
- `max_tokens`
- `temperature`
- `mode` such as `concise` or `accuracy`

## Safe Mock Run

Validate scenario coverage first:

```bash
python3 scripts/check_eval_coverage.py
```

Use this before spending credits:

```bash
python3 eval/model_matrix.py
```

It writes:

- `eval_runs/<run_id>.jsonl`
- `eval_runs/<run_id>.md`

## Live Fireworks Run

Use only after local `.env` values are loaded into the shell:

```bash
export FIREWORKS_API_KEY=...
export FIREWORKS_BASE_URL=...
export ALLOWED_MODELS=minimax-m3,kimi-k2p7-code,gemma-4-31b-it,gemma-4-26b-a4b-it,gemma-4-31b-it-nvfp4
python3 scripts/check_live_eval_env.py --print-models
python3 eval/model_matrix.py --live --limit 2 --models minimax-m3 --prompt-policies original
```

Run the env check first so live calls only use the judging proxy and Track 1 model allowlist.
Use the limited command as the first live smoke test before spending a full matrix.

If the AMD notebook has no judging proxy yet, use the normal Fireworks endpoint only as a
development-only model behavior test. These results are useful for prompt/model tuning, but
they are not official judging-proxy token data:

```bash
export FIREWORKS_BASE_URL=https://api.fireworks.ai/inference/v1
python3 scripts/check_live_eval_env.py --print-models --allow-normal-fireworks-dev
python3 eval/model_matrix.py --live --allow-normal-fireworks-dev --limit 2 --models minimax-m3 --prompt-policies original
```

Remove the dev override and restore the injected `FIREWORKS_BASE_URL` before any official
submission or judging-proxy validation.

After the smoke test succeeds:

```bash
python3 eval/model_matrix.py --live --prompt-policies all
```

## Prompt Policy Testing

Uncertain prompt-shaping decisions must be tested with metrics instead of guessed.

Supported prompt policies:

- `original`: send the scenario prompt as written.
- `compact`: add a short accuracy/constraint wrapper.
- `answer_only`: ask for final answer only while preserving requested format.

Run all prompt policies in mock mode:

```bash
python3 eval/model_matrix.py --prompt-policies all
```

Run all prompt policies live only after env vars are loaded:

```bash
python3 eval/model_matrix.py --live --prompt-policies all
```

Use prompt-policy results to decide:

- whether prompt wrappers improve accuracy,
- whether answer-only mode saves completion tokens safely,
- which categories must preserve original wording,
- which categories can use compact prompts without losing score.

## What To Compare

- Pass rate by model.
- Average score by model.
- Total and average tokens by model.
- Pass rate and score by category.
- Token usage by category.
- Latency by model.
- Pass rate and token usage by prompt policy.
- Failure notes per task.
- Best model per category under accuracy-first ranking.
- Cheapest passing model per category.
- Cases where the cheapest model fails but a larger model passes.
- Cases where all models fail and prompt/category strategy needs work.

## Decision Rule

For each category:

1. Prefer models with the highest score/pass rate.
2. Break ties by lower average token usage.
3. Break remaining ties by lower latency.
4. Keep a safer Fireworks accuracy mode for high-risk categories even if it costs more tokens.

This is experiment infrastructure, not final runtime behavior. The final router should use the learned category/model preferences only after they are validated against official-style tasks.

## Model Selection Outputs

After each serious run, produce a table like:

| Category | Best Accuracy Model | Cheapest Passing Model | Recommended Default | Accuracy Mode? | Notes |
| --- | --- | --- | --- | --- | --- |
| factual_knowledge | TBD | TBD | TBD | TBD | TBD |
| mathematical_reasoning | TBD | TBD | TBD | TBD | TBD |
| sentiment_classification | TBD | TBD | TBD | TBD | TBD |
| text_summarisation | TBD | TBD | TBD | TBD | TBD |
| named_entity_recognition | TBD | TBD | TBD | TBD | TBD |
| code_debugging | TBD | TBD | TBD | TBD | TBD |
| logical_deductive_reasoning | TBD | TBD | TBD | TBD | TBD |
| code_generation | TBD | TBD | TBD | TBD | TBD |

The final router should eventually consume these decisions through configuration, not hardcoded one-off conditionals.

## Run Protocol

1. Run mock mode.
2. Inspect report formatting and JSONL schema.
3. Run a tiny live smoke test with one or two scenarios per category.
4. Verify all calls go through `FIREWORKS_BASE_URL`.
5. Verify token fields are present and sensible.
6. Expand scenario coverage.
7. Run full model matrix.
8. Review failures by category.
9. Tune prompt templates and `max_tokens`.
10. Compare `original`, `compact`, and `answer_only` prompt policies.
11. Re-run only affected categories to save credits.
12. Promote category/model/prompt-policy decisions into router configuration.

## Safety Rules

- Do not run live experiments without explicitly passing `--live`.
- Do not paste or commit API keys.
- Do not use personal Fireworks URLs in code.
- Do not interpret mock results as real model performance.
- Do not optimize only for token count before confirming accuracy.
- Do not overfit to exact scenario wording; hidden prompts use variants.
