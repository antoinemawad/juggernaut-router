# Planned Architecture

This document defines the intended Track 1 implementation architecture. It is planning-only and should be updated before coding changes.

## Runtime Flow

`/input/tasks.json -> main.py -> agent.py -> local classifier -> local solver/validator -> route decision -> Fireworks fallback only if needed -> /output/results.json`

## Local-First Routing Contract

The agent must not immediately forward every prompt to Fireworks. The planned control flow is:

1. `main.py` reads each task and passes only the task object/prompt to `agent.py`.
2. `agent.py` calls `classifier.py` locally to identify the task category and routing risk.
3. The classifier returns category, confidence, and risk flags without using Fireworks.
4. The agent asks local deterministic solvers whether they can produce a high-confidence answer.
5. The agent validates the local answer when available.
6. The agent accepts the local answer only if confidence and validation pass the configured threshold.
7. The agent calls Fireworks only when local classification says the task is risky, local solvers cannot answer, confidence is below threshold, or validation fails.
8. The Fireworks client selects an allowed model and sends the request through `FIREWORKS_BASE_URL`.

This preserves the rank #1 objective: spend zero remote tokens on safe tasks and reserve Fireworks tokens for tasks where accuracy risk is high.

## Elite Risk Engine

The router should be implemented as a risk engine, not only a category classifier. See `docs/elite-routing-plan.md` for the full design.

Core routing stages:

1. Category detection.
2. Risk scoring across ambiguity, reasoning depth, format strictness, code risk, factual freshness, and validator strength.
3. Local solvability check.
4. Local solver attempt with structured evidence.
5. Category-specific validation.
6. Route decision across local, concise Fireworks, accuracy Fireworks, format-strict Fireworks, and code Fireworks modes.
7. Answer normalization.
8. Router decision logging.

Local answers must earn trust. A local solver result should carry answer, confidence, category, evidence, validator status, risk flags, and failure reason. The agent should accept it only when category confidence, solver confidence, risk score, and validation all pass the selected router mode thresholds.

## Planned Files

### `app/main.py`

- Entrypoint for the Docker container.
- Reads `/input/tasks.json`.
- Validates that input is a JSON array and that each usable task has string-like `task_id` and `prompt`.
- Calls the agent for each task.
- Writes `/output/results.json`.
- Ensures valid JSON output even if individual tasks fail.
- Never lets one malformed task crash the whole batch.
- Exits code 0 on successful batch completion.
- For local testing, `INPUT_PATH` and `OUTPUT_PATH` may override the default harness paths. Submission mode uses the same code path with the defaults.

### `app/config.py`

- Planned runtime configuration loader.
- Reads `ROUTER_MODE`, `LOCAL_CONFIDENCE_THRESHOLD`, `FIREWORKS_TIMEOUT_SECONDS`, `FIREWORKS_MAX_RETRIES`, and optional `ROUTER_LOG_PATH`.
- Provides safe defaults for local/mock testing.
- Must not require `.env` in the final container.
- Must not log secrets.

### `app/types.py`

- Planned shared dataclasses or typed dictionaries.
- Should define structured agent/routing results with answer, route, category, confidence, risk, selected model, prompt policy, token metrics, error, and metadata.
- The submitted `/output/results.json` still contains only `task_id` and `answer`.

### `app/classifier.py`

- Planned task classifier for the 8 Track 1 categories.
- Should use simple, inspectable heuristics first.
- Must return category and confidence.
- Must run locally before any Fireworks call.
- Must expose risk flags such as `requires_reasoning`, `requires_code`, `requires_summary`, `requires_entities`, `likely_deterministic`, and `ambiguous`.
- Should contribute risk components for ambiguity, reasoning depth, format strictness, code risk, factual freshness, and local validator weakness.
- Should avoid overfitting to public examples because evaluation uses unseen variants. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### `app/solvers/result.py`

- Planned shared result object for local solvers.
- Should include `answer`, `confidence`, `needs_fireworks`, `failure_reason`, and optional validation metadata.
- Should include the classifier category and route reason so local-vs-Fireworks decisions can be audited.
- Should include evidence and risk flags so the router can prove why a local answer is safe.

### `app/validators.py`

- Planned category-specific validators for local and remote outputs.
- Should validate math recomputation, sentiment polarity strength, NER schema/labels, summary length/key terms, simple logic relation graphs, code syntax, and exact-format requirements.
- Must reject local answers that cannot be checked strongly enough for the selected router mode.

### `app/normalization.py`

- Planned final-answer normalizer.
- Should strip surrounding whitespace, convert non-string answers to strings, remove code fences when code-only output is requested, preserve exact requested formats, and provide a nonempty fallback answer when needed.
- Must run before writing `/output/results.json`.

### `app/telemetry.py`

- Planned optional local decision logger.
- Writes JSONL records only when `ROUTER_LOG_PATH` is set.
- Must never write secrets or API keys.
- Must not alter official `/output/results.json`.
- Should log route, category, risk, confidence, validator notes, selected model, remote mode, prompt policy, retry count, tokens, latency, and errors.

### `app/solvers/basic.py`

- Planned deterministic local solvers for high-confidence tasks.
- Candidate coverage: arithmetic, simple sentiment, obvious NER, simple formatting.
- Must never emit low-confidence guesses as final answers.

### `app/agent.py`

- Planned routing coordinator.
- Receives a task from `main.py`.
- Always classifies locally before deciding whether Fireworks is needed.
- Uses classifier output and local solvers to decide whether the task can stay local.
- Calls Fireworks fallback when local confidence is too low or validation fails.
- Must not call Fireworks for high-confidence deterministic/local answers.
- Uses a programmable/configurable accuracy-gate target in local evaluation so the threshold can change without architecture changes.
- Enforces English-only response policy. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- Should record a local router decision object for each task during experiments: `task_id`, category, classifier confidence, local solver confidence, validator result, route, selected model, prompt policy, `max_tokens`, token usage when available, latency, and route reason.
- Must normalize final answers before writing output: strip surrounding whitespace, avoid markdown unless requested, keep answers concise, and preserve exact requested formats.
- Must keep timeout and fallback behavior explicit: remote calls should have bounded timeouts, limited retry behavior, and a final local/error-safe answer path so one failed task does not crash the whole batch.
- Should support configurable router modes such as `conservative`, `balanced`, and `aggressive` so official submissions can compare clean hypotheses.
- Should select remote modes such as `remote_concise`, `remote_accuracy`, `remote_format_strict`, and `remote_code` based on risk.
- Should return a structured routing result internally, not only a raw string.
- Must keep the public answer path simple: callers can still retrieve the final answer string for `/output/results.json`.

### `app/fireworks_client.py`

- Planned Fireworks API wrapper.
- Must read `FIREWORKS_API_KEY`, `FIREWORKS_BASE_URL`, and `ALLOWED_MODELS` from the environment. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Must route all Fireworks calls through `FIREWORKS_BASE_URL`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Must build the chat completions URL from `FIREWORKS_BASE_URL`; hardcoding `https://api.fireworks.ai/...` is not allowed.
- Must select only from `ALLOWED_MODELS`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Current planning model set is `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, and `gemma-4-31b-it-nvfp4`; final behavior still validates against `ALLOWED_MODELS`.
- Must not hardcode any fixed model as mandatory.
- Must handle missing env vars, HTTP errors, timeouts, invalid JSON, missing `choices`, missing `usage`, and disallowed models without leaking secrets.
- Must bound timeout and retry behavior through config.

## Production Readiness Contract

The submitted runtime should fail soft and keep valid output whenever possible.

Required behavior:

- malformed input file: write valid JSON output for recoverable tasks or a safe empty result list if no tasks are usable.
- malformed task item: log locally when enabled and continue.
- local solver failure: route to Fireworks or safe fallback.
- Fireworks missing env: return safe fallback for affected task rather than crashing the batch.
- Fireworks timeout/HTTP/invalid JSON: retry only when configured and safe, then fallback.
- unsupported model: choose another allowed model or fallback.
- output normalization failure: return a safe nonempty answer.

Final output must always be a valid JSON array of `{ "task_id": ..., "answer": ... }` objects.

### `tests/`

- Unit tests for classifier, local solvers, Fireworks client config, output JSON shape, and agent routing.
- Should include tests for malformed input, missing env vars, and mounted input/output paths.
- Should include adversarial category examples that look locally solvable but require fallback when confidence or validation is weak.
- Should include tests for router decision logging, answer normalization, Fireworks timeout handling, and no batch crash on an individual task failure.
- Should verify every scenario logs category, risk score, risk components, route reason, remote mode, selected model, prompt policy, token metrics, latency, validator notes, and errors when present.
- Should include production-readiness tests for input validation, structured routing result shape, normalization, optional telemetry, Fireworks invalid responses, missing `usage`, disallowed models, missing env vars, and Docker fixture IO.

### `local_test/`

- Local fixtures for `/input/tasks.json` and `/output/results.json` testing.
- Must not be treated as cached answers or hidden benchmark assumptions.

### `docs/`

- Planning, compliance, source notes, experiment logs, and final submission checklist.
- Must separate facts, assumptions, decisions, and open questions.

## Container Constraints

- Final image must be public and `linux/amd64`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- Final compressed image must be 10GB or smaller. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Maximum runtime is 10 minutes. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Container must start and be ready within 60 seconds. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- Per-response time must be under 30 seconds. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.

## Security and Compliance

- No secrets in the repo.
- No committed `.env`.
- No `.env` bundled in the submitted image. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- No hardcoded answers or cached hidden-task responses. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- No hardcoded final model IDs; use `ALLOWED_MODELS`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Local deterministic logic and local model experimentation are allowed under the Track 1 local-token rule. Whenever the router chooses Fireworks, the request must be sent through `FIREWORKS_BASE_URL` so the judging proxy can record token usage. The final agent treats `FIREWORKS_BASE_URL` as the only valid remote inference base URL and selects models only from `ALLOWED_MODELS`.

## Local Runtime Policy

- Final container should remain CPU-safe by default.
- No heavy local LLM runtime dependency should be added unless explicitly justified by experiments and compatible with size/startup/runtime limits.
- Local deterministic solvers are preferred for zero-token savings.
- Final evaluator GPU access for local LLM inference inside the submitted Docker container is not confirmed. Therefore, the final image should remain CPU-safe and should not require a GPU to run correctly.
- Optional AMD/vLLM validation belongs in a separate documented path, not in the default final runtime, unless organizers confirm it is appropriate.

## AMD / vLLM Validation Path

- AMD Developer Cloud and AMD AI Notebooks can be used for validation, benchmarking, and evidence. Sources: `Guides/Hackathon Act II.txt`, `Guides/AMD Developer Hackathon Participant Guide.txt`.
- Any AMD/vLLM experiment should record environment, model, runtime, image-size implications, and whether it affects final container compliance.
