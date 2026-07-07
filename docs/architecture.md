# Planned Architecture

This document defines the intended Track 1 implementation architecture. It is planning-only and should be updated before coding changes.

## Runtime Flow

`/input/tasks.json -> main.py -> agent.py -> classifier/local solver -> Fireworks fallback if needed -> /output/results.json`

## Planned Files

### `app/main.py`

- Entrypoint for the Docker container.
- Reads `/input/tasks.json`.
- Calls the agent for each task.
- Writes `/output/results.json`.
- Ensures valid JSON output even if individual tasks fail.
- Exits code 0 on successful batch completion.
- For local testing, `INPUT_PATH` and `OUTPUT_PATH` may override the default harness paths. Submission mode uses the same code path with the defaults.

### `app/classifier.py`

- Planned task classifier for the 8 Track 1 categories.
- Should use simple, inspectable heuristics first.
- Must return category and confidence.
- Should avoid overfitting to public examples because evaluation uses unseen variants. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### `app/solvers/result.py`

- Planned shared result object for local solvers.
- Should include `answer`, `confidence`, `needs_fireworks`, `failure_reason`, and optional validation metadata.

### `app/solvers/basic.py`

- Planned deterministic local solvers for high-confidence tasks.
- Candidate coverage: arithmetic, simple sentiment, obvious NER, simple formatting.
- Must never emit low-confidence guesses as final answers.

### `app/agent.py`

- Planned routing coordinator.
- Receives a task from `main.py`.
- Uses classifier and local solvers.
- Calls Fireworks fallback when local confidence is too low or validation fails.
- Uses a programmable/configurable accuracy-gate target in local evaluation so the threshold can change without architecture changes.
- Enforces English-only response policy. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.

### `app/fireworks_client.py`

- Planned Fireworks API wrapper.
- Must read `FIREWORKS_API_KEY`, `FIREWORKS_BASE_URL`, and `ALLOWED_MODELS` from the environment. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Must route all Fireworks calls through `FIREWORKS_BASE_URL`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Must build the chat completions URL from `FIREWORKS_BASE_URL`; hardcoding `https://api.fireworks.ai/...` is not allowed.
- Must select only from `ALLOWED_MODELS`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Current planning model set is `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, and `gemma-4-31b-it-nvfp4`; final behavior still validates against `ALLOWED_MODELS`.
- Must not hardcode any fixed model as mandatory.

### `tests/`

- Unit tests for classifier, local solvers, Fireworks client config, output JSON shape, and agent routing.
- Should include tests for malformed input, missing env vars, and mounted input/output paths.

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
