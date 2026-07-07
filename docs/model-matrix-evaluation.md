# Model Matrix Evaluation

Purpose: test each allowed Track 1 model across all eight task categories, log results, and make model/category routing decisions showable.

## Allowed Models

- `minimax-m3`
- `kimi-k2p7-code`
- `gemma-4-31b-it`
- `gemma-4-26b-a4b-it`
- `gemma-4-31b-it-nvfp4`

Runtime rule: live experiments must still validate against `ALLOWED_MODELS` and all Fireworks calls must go through `FIREWORKS_BASE_URL`.

## Safe Mock Run

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
python3 eval/model_matrix.py --live
```

The script intentionally refuses `--live` unless all three env vars exist.

## What To Compare

- Pass rate by model.
- Average score by model.
- Total and average tokens by model.
- Pass rate and score by category.
- Token usage by category.
- Latency by model.
- Failure notes per task.

## Decision Rule

For each category:

1. Prefer models with the highest score/pass rate.
2. Break ties by lower average token usage.
3. Break remaining ties by lower latency.
4. Keep a safer Fireworks accuracy mode for high-risk categories even if it costs more tokens.

This is experiment infrastructure, not final runtime behavior. The final router should use the learned category/model preferences only after they are validated against official-style tasks.
