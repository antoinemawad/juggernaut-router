# Configuration

Configuration is loaded by `app/config.py` and the `Dockerfile`. Runtime environment variables override defaults. If `ROUTER_RECOMMENDATION_PATH` points to a JSON recommendation file, supported exports are used only when the same variable is not already set in the environment.

## Runtime Environment Variables

| Name | Required | Default | Purpose | Example |
| --- | --- | --- | --- | --- |
| `INPUT_PATH` | no | `/input/tasks.json` | Task input path | `/input/tasks.json` |
| `OUTPUT_PATH` | no | `/output/results.json` | Result output path | `/output/results.json` |
| `ROUTER_LOG_PATH` | no | none | Optional JSONL telemetry output | `/output/router_log.jsonl` |
| `ROUTER_RECOMMENDATION_PATH` | no | none | Optional runtime export JSON | `eval_runs/final_runtime.json` |
| `FIREWORKS_API_KEY` | for remote | none | Fireworks API credential | placeholder only |
| `FIREWORKS_BASE_URL` | for remote | none | Fireworks-compatible base URL, normally injected by evaluator | `https://.../v1` |
| `ALLOWED_MODELS` | for remote | none | Comma-separated model aliases allowed at runtime | `minimax-m3,kimi-k2p7-code` |
| `FIREWORKS_TIMEOUT_SECONDS` | no | `25` in code and Docker | Per-call timeout, clamped by code | `25` |
| `FIREWORKS_MAX_RETRIES` | no | `0` in code, `1` in Docker | Remote retry count | `1` |
| `FIREWORKS_DISABLE_MAX_TOKENS` | no | `false` | Omit `max_tokens` from Fireworks payload when true | `false` |
| `FIREWORKS_MAX_TOKENS` | no | `256` | Default remote output token cap | `256` |
| `FIREWORKS_MAX_TOKENS_BY_CATEGORY` | no | Dockerfile category map | Per-category output token cap | `code_generation=512` |
| `ROUTER_PROFILE` | no | `accuracy_gate` in code, `token_competitive` in Docker | Runtime profile selector | `token_competitive` |
| `ROUTER_MODE` | no | profile-dependent in code, `balanced` in Docker | Routing mode | `balanced` |
| `LOCAL_CONFIDENCE_THRESHOLD` | no | `0.95` in code, `1.0` in Docker | Deterministic proof threshold | `1.0` |
| `LOCAL_PROOF_BUDGET_MS` | no | `100` | Local proof budget | `100` |
| `LOCAL_CROSS_CHECK_ENABLED` | no | `true` in code, `false` in Docker | Enables local cross-check layer where supported | `false` |
| `LOCAL_MODEL_ENABLED` | no | `false`, or build arg in Docker | Enables local GGUF/client path | `true` |
| `LOCAL_MODEL_COMMAND` | no | none | External local model command fallback | `python3 local_wrapper.py` |
| `LOCAL_MODEL_PATH` | no | `/app/models/local-model.gguf` in Docker | Default local GGUF path | `/app/models/local-model.gguf` |
| `LOCAL_MODEL_PATH_BY_CATEGORY` | no | none | Semicolon-separated category-to-GGUF map | `code_generation=/app/models/local-code.gguf` |
| `LOCAL_MODEL_CATEGORIES` | no | empty in code, Docker build arg default | Categories eligible for local model | `sentiment_classification,text_summarisation` |
| `LOCAL_MODEL_MAX_TOKENS` | no | `128` | Local output token cap before prompt-type bounding | `128` |
| `LOCAL_MODEL_BATCH_LIMIT` | no | `12` in code, `6` in Docker | Max local-model attempts per batch | `6` |
| `LOCAL_MODEL_CONTEXT` | no | `1024` | Local model context length | `1024` |
| `LOCAL_MODEL_THREADS` | no | `2` | Local model CPU threads | `2` |
| `LOCAL_MODEL_TEMPERATURE` | no | `0.0` | Local generation temperature | `0` |
| `LOCAL_MODEL_TIMEOUT_SECONDS` | no | `20` in code, `10` in Docker | Local model call timeout | `10` |
| `LOCAL_MODEL_MAX_CHARS` | no | `4096` | Maximum accepted local output characters | `4096` |
| `BATCH_DEADLINE_SECONDS` | no | `600` | Batch-level deadline | `600` |
| `DEADLINE_SAFETY_MARGIN_SECONDS` | no | `60` in code, `10` in Docker | Reserve time before deadline | `10` |
| `REMOTE_WORKER_COUNT` | no | `2` in code, `6` in Docker | Concurrent task workers | `6` |
| `REMOTE_VALIDATION_ESCALATION_ENABLED` | no | `true` | Allows second remote call when validation rejects first answer | `true` |
| `ROUTER_PROMPT_POLICY_REMOTE_ACCURACY` | no | `compact` in code, `answer_only` in Docker | Prompt policy for accuracy remote mode | `answer_only` |
| `ROUTER_PROMPT_POLICY_REMOTE_CODE` | no | `answer_only` | Prompt policy for code remote mode | `answer_only` |
| `ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT` | no | `answer_only` | Prompt policy for strict format mode | `answer_only` |
| `ROUTER_PROMPT_POLICY_REMOTE_CONCISE` | no | `compact` in code, `answer_only` in Docker | Prompt policy for concise mode | `answer_only` |
| `ROUTER_PROMPT_POLICY_BY_CATEGORY` | no | none or Dockerfile category map | Category-specific prompt policy | `mathematical_reasoning=final_only` |
| `ROUTER_MODELS_REMOTE_ACCURACY` | no | code/Docker defaults | Preferred models for accuracy mode | `gemma-4-31b-it,kimi-k2p7-code` |
| `ROUTER_MODELS_REMOTE_CODE` | no | code/Docker defaults | Preferred models for code mode | `kimi-k2p7-code,gemma-4-31b-it` |
| `ROUTER_MODELS_REMOTE_FORMAT_STRICT` | no | code/Docker defaults | Preferred models for format-strict mode | `gemma-4-31b-it,kimi-k2p7-code` |
| `ROUTER_MODELS_REMOTE_CONCISE` | no | code/Docker defaults | Preferred models for concise mode | `gemma-4-26b-a4b-it,gemma-4-31b-it` |
| `ROUTER_MODELS_REMOTE_ESCALATION` | no | code/Docker defaults | Preferred models for validation escalation | `gemma-4-31b-it,kimi-k2p7-code` |
| `ROUTER_MODELS_BY_CATEGORY` | no | none or Dockerfile category map | Category-specific remote model preferences | `code_generation=kimi-k2p7-code,gemma-4-31b-it` |

Prompt policy values are `original`, `compact`, `answer_only`, and `final_only`.

## Docker Build Arguments

| Name | Default | Purpose | Example |
| --- | --- | --- | --- |
| `ENABLE_LOCAL_MODEL` | `false` | Install local-model dependencies and bundle/download GGUF | `true` |
| `LOCAL_MODEL_URL` | Qwen2.5 3B GGUF URL | Download source used only when no bundled model exists | `https://huggingface.co/.../model.gguf` |
| `LOCAL_MODEL_FILENAME` | `local-model.gguf` | Runtime filename under `/app/models` | `local-model.gguf` |
| `LOCAL_MODEL_PATH_BY_CATEGORY` | empty | Bake category-to-GGUF map into image defaults | `text_summarisation=/app/models/local-model.gguf` |
| `LOCAL_MODEL_CATEGORIES` | `sentiment_classification,text_summarisation` | Bake local-model category allowlist into image defaults | `sentiment_classification,text_summarisation` |

## Development-Only Variables

| Name | Purpose |
| --- | --- |
| `FIREWORKS_DEV_MODEL_MAP` | Maps Track 1 aliases to accessible Fireworks model/deployment paths for local live testing. Do not use for official judging unless instructed. |
| `JUGGERNAUT_ALLOW_NORMAL_FIREWORKS_DEV` | Allows `scripts/check_live_eval_env.py` to accept the public Fireworks API host during development. |

## Security Notes

- Never commit real values for `FIREWORKS_API_KEY`.
- Do not hardcode `FIREWORKS_BASE_URL`.
- Do not commit `.env` files or GGUF weights.
- Keep local model files in the Docker build context only when intentionally building a local-model image.
