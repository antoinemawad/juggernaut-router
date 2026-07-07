# Implementation Phases

Purpose: define the exact implementation order for moving from planning/eval scaffolding to a competitive Track 1 runtime.

This document is intentionally operational. Each phase has deliverables, required checks, exit criteria, and explicit non-goals.

## Phase 0: Planning and Eval Foundation

Status: mostly complete.

Goal: make the strategy measurable before changing runtime behavior.

Deliverables:

- source-backed requirements docs,
- elite routing plan,
- test/eval coverage plan,
- model matrix harness,
- router config sweep harness,
- AMD Notebook checkpoint,
- local quality gate script.

Required checks:

```bash
python3 scripts/check_eval_coverage.py
python3 eval/model_matrix.py --prompt-policies all
python3 eval/router_config_sweep.py --accuracy-threshold 0.85
INPUT_PATH=local_test/input/tasks.json OUTPUT_PATH=local_test/output/results.json python3 -m app.main
python3 scripts/validate_submission_io.py local_test/output/results.json
```

Exit criteria:

- all required checks pass,
- scenario metadata covers all 8 categories,
- docs clearly separate implemented vs planned behavior,
- branch is pushed.

Non-goals:

- no live Fireworks matrix required,
- no real classifier required,
- no Docker push required.

## Phase 1: Production-Safe Runtime

Goal: make the submitted container hard to break before making the router smarter.

Deliverables:

- `app/config.py`
- `app/types.py`
- `app/normalization.py`
- `app/telemetry.py`
- hardened `app/main.py`
- hardened `app/fireworks_client.py`
- structured internal result from `app/agent.py`

Implementation requirements:

- validate `/input/tasks.json` is a JSON array,
- tolerate malformed task items without crashing the batch,
- always write valid `/output/results.json` for recoverable failures,
- keep final output objects limited to `task_id` and `answer`,
- support `ROUTER_MODE`,
- support `LOCAL_CONFIDENCE_THRESHOLD`,
- support `FIREWORKS_TIMEOUT_SECONDS`,
- support `FIREWORKS_MAX_RETRIES`,
- support optional `ROUTER_LOG_PATH`,
- never log secrets,
- handle missing Fireworks env vars gracefully when remote fallback is needed,
- handle Fireworks timeout, HTTP error, invalid JSON, missing `choices`, missing `usage`, and disallowed models.

Required tests/checks:

- malformed JSON input,
- non-array JSON input,
- missing `task_id`,
- missing `prompt`,
- non-string prompt,
- missing Fireworks env vars,
- Fireworks timeout mock,
- Fireworks invalid JSON mock,
- output normalization for empty/non-string answers,
- telemetry JSONL writes when `ROUTER_LOG_PATH` is set,
- telemetry excludes API keys/secrets,
- `python3 scripts/run_local_quality_gate.py`.

Exit criteria:

- all required tests/checks pass,
- no recoverable single-task failure can prevent valid final JSON,
- local quality gate passes,
- Docker smoke command is ready to run.

Non-goals:

- no full risk engine yet,
- no broad local proof system yet,
- no live Fireworks optimization yet.

## Phase 2: Real Local-First Router

Goal: replace solver-first routing with classifier/risk/validator routing.

Deliverables:

- `app/classifier.py`
- `app/validators.py`
- structured local solver results,
- intent and constraint extraction,
- answer-shape detection,
- local proof metadata,
- expected route assertions in eval/test fixtures.

Implementation requirements:

- classifier runs before any Fireworks call,
- classifier emits category, confidence, answer shape, constraints, and risk components,
- local solvers return structured results, not raw strings,
- validators check local answers before acceptance,
- local route is allowed only when category confidence, solver confidence, risk threshold, and validator all pass,
- risky or unsupported tasks route to Fireworks,
- final answer still passes normalization.

Required tests/checks:

- classifier category coverage for all 8 categories,
- risk component coverage,
- local high-confidence tasks do not call Fireworks,
- risky tasks call Fireworks wrapper,
- expected route assertions pass for scenario fixtures,
- validators reject weak local answers,
- local accepted answers include proof/evidence metadata,
- local quality gate passes.

Exit criteria:

- real router decisions are visible in logs,
- router config sweep uses actual router routes instead of only simulated routes,
- local acceptance is validator-gated,
- no regression in output JSON shape.

Non-goals:

- no need for every planned validator to be perfect,
- no need for full live model matrix,
- no official submission until Phase 1 remains stable.

## Phase 3: Remote Modes and Configurable Router Modes

Goal: make official submissions comparable and measurable.

Deliverables:

- `conservative`, `balanced`, and `aggressive` runtime modes,
- `remote_concise`,
- `remote_accuracy`,
- `remote_format_strict`,
- `remote_code`,
- category/model/prompt/`max_tokens` config map,
- one-retry policy for fixable format failures,
- post-Fireworks output verification.

Implementation requirements:

- every remote call selects only from runtime `ALLOWED_MODELS`,
- remote mode is selected from category, answer shape, constraints, and risk,
- retry count is capped by `FIREWORKS_MAX_RETRIES`,
- retry happens only for fixable verification failures,
- retry reason is logged,
- prompt policy is logged,
- selected model is logged,
- token usage is logged when available.

Required tests/checks:

- router mode comparison on identical scenarios,
- remote mode selection tests,
- format-strict retry test,
- no retry on non-fixable semantic failure,
- disallowed model test,
- missing `usage` fallback test,
- selected model is always in `ALLOWED_MODELS`,
- local quality gate passes.

Exit criteria:

- router config sweep compares real conservative/balanced/aggressive behavior,
- reports show local route rate, pass rate, and token estimates by config,
- remote mode logs are inspectable,
- one retry policy is bounded and tested.

Non-goals:

- no uncontrolled live spend,
- no official submission without Docker smoke.

## Phase 4: Live Evaluation and Submission Optimization

Goal: use Fireworks credits and official submissions as controlled feedback.

Deliverables:

- tiny live Fireworks smoke result,
- selected live model/prompt slices,
- Docker smoke proof,
- public linux/amd64 image,
- official submission attempt log,
- final selected router config.

Implementation requirements:

- all live calls go through `FIREWORKS_BASE_URL`,
- live runs use only `ALLOWED_MODELS`,
- no API keys in logs,
- official submissions change one major variable at a time,
- official result is recorded before another attempt.

Required checks:

```bash
python3 scripts/run_local_quality_gate.py
docker build -t juggernaut-router:local .
docker run --rm -v "$PWD/local_test/input:/input:ro" -v "$PWD/local_test/output:/output" juggernaut-router:local
python3 scripts/validate_submission_io.py local_test/output/results.json
```

Exit criteria:

- Docker image is public and pullable,
- image includes linux/amd64 manifest,
- final output JSON validates,
- selected router config has local evidence,
- official submission log is updated.

Non-goals:

- no broad live matrix unless credits/time justify it,
- no GPU-required final runtime unless organizers confirm final GPU access.

## MVP Cutoff Before First Official Submission

Must have:

- Phase 1 production-safe runtime,
- local smoke test,
- output validator,
- eval coverage checker,
- router config sweep,
- Docker run with mounted `/input` and `/output`,
- Fireworks base URL compliance,
- allowed model compliance,
- official submission decision tree reviewed.

Nice to have:

- Phase 2 local-first risk engine,
- Phase 3 remote modes,
- selected live model slices,
- broader adversarial scenario set.

Skip unless time remains:

- heavy local LLM dependency in final container,
- GPU-required final runtime,
- non-Track-1 product polish,
- generic process docs that do not affect scoring.
