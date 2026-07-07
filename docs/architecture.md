# Planned Architecture

This document defines the Track 1 implementation architecture. Sections marked as planned describe the target end-state; implemented sections describe code that now exists in the repository.

## Runtime Flow

`/input/tasks.json -> main.py -> agent.py -> local classifier -> local solver/validator -> route decision -> Fireworks fallback only if needed -> /output/results.json`

For a diagrammed view of this architecture, see `docs/planned-architecture-diagram.md`.

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
9. Eval sweep through the same router path with mocked Fireworks responses before live submissions.

Local answers must earn trust. A local solver result should carry answer, confidence, category, evidence, validator status, risk flags, and failure reason. The agent should accept it only when category confidence, solver confidence, risk score, and validation all pass the selected router mode thresholds.

## Local Acceptance Proof Ladder

Local tokens count as zero, so it is worth doing stronger local checks before spending Fireworks tokens. The constraint is wall-clock time: every local check still consumes part of the 10-minute container budget. Therefore, the router should use a staged proof ladder with cheap checks first and more expensive checks only for promising local candidates.

Planned local acceptance layers:

1. Input sanity: prompt is nonempty, English-like, and parseable enough to classify.
2. Category confidence: classifier identifies one of the 8 Track 1 categories above the selected router-mode threshold.
3. Constraint extraction: answer shape and hard constraints are detected, such as answer-only, exact numeric, one sentence, exact word count, entity labels, code-only, or corrected code.
4. Risk gate: ambiguity, reasoning depth, format strictness, code risk, factual freshness, and validator weakness are below the local-accept threshold.
5. Local solver evidence: a deterministic solver or template returns an answer with evidence, not only a raw string.
6. Independent validation: a category validator recomputes or checks the answer independently from the solver path.
7. Format validation: exact output constraints are verified after normalization.
8. Trap guard: known false-local patterns are checked, including sarcasm, mixed sentiment, incomplete logic, multi-step math, current/live factual claims, ambiguous entities, and nontrivial code.
9. Cheap cross-check: when available, run a second cheap verifier such as math recomputation, relation-graph consistency, Python syntax, tiny code micro-tests, NER entity-count checks, or summary word-count checks.
10. Deadline/value gate: accept locally only if the proof ladder completed inside the local proof budget; otherwise route to Fireworks if the deadline permits.

The proof ladder should be category-aware. Math may require exact recomputation, code may require syntax plus tiny tests, sentiment may require sarcasm/mixed-signal guards, and factual knowledge should reject current or unverifiable claims unless the answer is directly extractive from the prompt.

Performance rule: local verification must be bounded. A good default is a small per-task budget such as `LOCAL_PROOF_BUDGET_MS=50` to `200` for deterministic checks, with stricter limits when the batch is large or the deadline is near. If a local proof step is too expensive, the router should prefer Fireworks or a safe fallback rather than risk missing the global runtime deadline.

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
- Reads deadline-related settings such as `BATCH_DEADLINE_SECONDS`, `DEADLINE_SAFETY_MARGIN_SECONDS`, `REMOTE_WORKER_COUNT`, and optional per-mode timeout defaults.
- Reads local-proof settings such as `LOCAL_PROOF_BUDGET_MS`, `LOCAL_CROSS_CHECK_ENABLED`, and category-specific local acceptance thresholds.
- Provides safe defaults for local/mock testing.
- Must not require `.env` in the final container.
- Must not log secrets.

### `app/deadline.py`

- Planned runtime deadline manager for the 10-minute container limit.
- Starts a monotonic batch timer as early as possible in `main.py`.
- Exposes remaining batch time, remote-call budget, retry eligibility, and graceful-degradation decisions.
- Reserves a safety margin so the app can always write `/output/results.json` before the judge timeout.
- Must be deterministic, lightweight, and CPU-safe.
- Should make it easy to test "time almost exhausted" behavior without sleeping for real minutes.

### `app/types.py`

- Planned shared dataclasses or typed dictionaries.
- Should define structured agent/routing results with answer, route, category, confidence, risk, selected model, prompt policy, token metrics, error, and metadata.
- The submitted `/output/results.json` still contains only `task_id` and `answer`.

### `app/classifier.py`

- Implemented task classifier for the 8 Track 1 categories.
- Uses simple, inspectable heuristics first.
- Returns category, confidence, answer shape, constraints, risk components, and risk score.
- Runs locally before any Fireworks call.
- Contributes risk components for ambiguity, reasoning depth, format strictness, code risk, factual freshness, and local validator weakness.
- Should avoid overfitting to public examples because evaluation uses unseen variants. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### `app/solvers/result.py`

- Planned shared result object for local solvers.
- Should include `answer`, `confidence`, `needs_fireworks`, `failure_reason`, and optional validation metadata.
- Should include the classifier category and route reason so local-vs-Fireworks decisions can be audited.
- Should include evidence and risk flags so the router can prove why a local answer is safe.

### `app/validators.py`

- Implemented first category-aware validator/proof gate for local outputs.
- Checks category confidence, constraint extraction, risk threshold, solver confidence, category validation, format validation, trap guard, cheap cross-check, and proof-budget enforcement.
- Rejects local answers that cannot be checked strongly enough for the selected router mode.
- Planned expansion: richer relation graphs, tiny code micro-tests, summary key-term checks, and more adversarial trap guards.

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

## Task Timing Metrics Contract

Telemetry should make every task auditable for accuracy, token use, and wall-clock cost. When `ROUTER_LOG_PATH` is enabled, each task-level JSONL record should include timing fields measured with a monotonic clock.

Required task timing fields:

- `task_started_at`: ISO timestamp for human inspection.
- `task_finished_at`: ISO timestamp for human inspection.
- `task_elapsed_ms`: total task wall-clock duration.
- `batch_elapsed_ms_at_start`: batch elapsed time when the task started.
- `batch_elapsed_ms_at_finish`: batch elapsed time when the task finished.
- `remaining_budget_ms`: remaining batch budget after safety margin.
- `classification_elapsed_ms`: local classification time.
- `constraint_extraction_elapsed_ms`: answer-shape and output-constraint extraction time.
- `local_solver_elapsed_ms`: deterministic local solver time.
- `validation_elapsed_ms`: validator time.
- `local_proof_elapsed_ms`: total local proof ladder time.
- `trap_guard_elapsed_ms`: trap guard time.
- `cross_check_elapsed_ms`: cheap independent cross-check time.
- `remote_elapsed_ms`: Fireworks request time when used.
- `normalization_elapsed_ms`: final answer normalization time.
- `telemetry_elapsed_ms`: optional logger overhead when measurable.

Required task decision/cost fields:

- `task_id`
- `category`
- `route`
- `route_reason`
- `router_mode`
- `risk_components`
- `local_proof_layers_passed`
- `local_proof_layers_failed`
- `selected_model`
- `remote_mode`
- `prompt_policy`
- `max_tokens`
- `prompt_token_estimate`
- `completion_tokens`
- `total_tokens`
- `retry_count`
- `deadline_decision`
- `error`

Timing fields must never be written to the official `/output/results.json`. They belong only in optional telemetry and eval reports. The telemetry overhead itself should be small enough that enabling it during development does not distort routing decisions materially.

### `app/solvers/basic.py`

- Implemented deterministic local solvers with structured internal results.
- Current coverage: arithmetic, simple sentiment, first-sentence summary, obvious NER, simple logic, selected code templates, and stable factual template.
- `try_basic_solver()` remains available for legacy eval scripts, while `try_basic_solver_structured()` returns answer, confidence, solver name, and evidence for the router.
- Must never emit low-confidence guesses as final answers.

### `app/agent.py`

- Implemented routing coordinator with Phase 2 local-first skeleton.
- Receives a task from `main.py`.
- Always classifies locally before deciding whether Fireworks is needed.
- Uses classifier output, structured local solver results, and validator proof gates to decide whether the task can stay local.
- Calls Fireworks fallback when local confidence is too low or validation fails.
- Must not call Fireworks for high-confidence deterministic/local answers.
- Uses a programmable/configurable accuracy-gate target in local evaluation so the threshold can change without architecture changes.
- Enforces English-only response policy. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- Should record a local router decision object for each task during experiments: `task_id`, category, classifier confidence, local solver confidence, validator result, route, selected model, prompt policy, `max_tokens`, token usage when available, latency, and route reason.
- Must normalize final answers before writing output: strip surrounding whitespace, avoid markdown unless requested, keep answers concise, and preserve exact requested formats.
- Must keep timeout and fallback behavior explicit: remote calls should have bounded timeouts, limited retry behavior, and a final local/error-safe answer path so one failed task does not crash the whole batch.
- Must consult the batch deadline before remote calls and retries.
- Should degrade gracefully near the deadline: skip retries, prefer concise remote mode when safe, or return the best validated fallback instead of risking container timeout.
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
- Conservative interpretation: treat the 10-minute maximum runtime as total container wall-clock time, including Python startup, imports, configuration loading, input reading, task execution, output writing, and shutdown. Treat the 60-second startup rule as a stricter sub-budget inside that 10-minute total unless official harness behavior proves otherwise.

## Deadline Management Strategy

The 10-minute runtime limit is a hard ceiling, not a target. Budget it from process start, including startup/import time. The final container should finish comfortably under it and must prefer valid output over one extra remote retry.

Planned behavior:

- start a monotonic process timer as early as possible, before heavy imports or task reading when practical,
- keep startup/import/config/input-read work comfortably under the 60-second startup sub-budget,
- reserve a safety margin, initially 60 seconds, for normalization and writing `/output/results.json`,
- keep Fireworks per-call timeouts below the 30-second per-response limit,
- cap retries by both `FIREWORKS_MAX_RETRIES` and remaining batch time,
- classify all tasks locally first when practical, then run remote-needed tasks with a small bounded worker pool,
- avoid unbounded queues, unbounded retries, and slow startup work,
- write a valid answer for every usable task even when some remote calls fail or the deadline is near,
- log deadline skips, timeout fallbacks, retry suppression, and elapsed time when telemetry is enabled.

This turns the limit into a competitive advantage: local tasks finish immediately, remote calls are spent only where needed, and the router can use limited parallelism without increasing recorded token usage.

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
