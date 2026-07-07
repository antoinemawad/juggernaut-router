# Implementation Phases

Purpose: define the exact implementation order for moving from planning/eval scaffolding to a competitive Track 1 runtime.

This is the execution spine for the project. Each phase has a clear objective, dependencies, deliverables, tests, exit criteria, quality bar, trace artifacts, and non-goals.

## Global Engineering Rules

- Keep the submitted runtime CPU-safe unless organizers explicitly confirm final GPU access.
- Keep `/output/results.json` minimal: only `task_id` and `answer`.
- Keep all remote inference behind `FIREWORKS_BASE_URL`.
- Keep model selection constrained to runtime `ALLOWED_MODELS`.
- Prefer accuracy over token reduction until the accuracy gate is safe.
- Treat the 10-minute container runtime as total wall-clock time from process start, including startup/import/input/output time, and reserve safety time for writing valid output.
- Treat the 60-second startup rule as a stricter sub-budget inside the 10-minute total unless official harness behavior proves otherwise.
- Do not promote a router behavior unless it has a test, a scenario, and a log/report path.
- Do not expand live Fireworks spend until the local quality gate passes.

## Global Quality Gates

Every implementation phase must preserve these checks:

```bash
python3 scripts/run_local_quality_gate.py
python3 scripts/validate_submission_io.py local_test/output/results.json
```

Before official submission, also run Docker:

```bash
docker build -t juggernaut-router:local .
docker run --rm -v "$PWD/local_test/input:/input:ro" -v "$PWD/local_test/output:/output" juggernaut-router:local
python3 scripts/validate_submission_io.py local_test/output/results.json
```

## Phase Dependencies

| Phase | Depends On | Unlocks |
| --- | --- | --- |
| Phase 0 | none | measurable planning baseline |
| Phase 1 | Phase 0 | safe runtime for all later work |
| Phase 2 | Phase 1 | real local-first routing |
| Phase 3 | Phase 2, with Phase 1 stable | official config comparisons |
| Phase 4 | Phase 1 plus selected Phase 2/3 features | live eval and official submissions |

## Phase 0: Planning and Eval Foundation

Status: mostly complete.

Objective: make the strategy measurable before changing runtime behavior.

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

Quality bar:

- scenario metadata covers all 8 Track 1 categories,
- model matrix and router sweep both write JSONL plus markdown reports,
- docs clearly separate implemented, planned, and open-question behavior.

Trace artifacts:

- latest `eval_runs/model_matrix_*.md`,
- latest `eval_runs/router_sweep_*.md`,
- `docs/test-eval-coverage-plan.md`,
- `docs/strategy-plan.md`.

Definition of done:

- all required checks pass,
- local quality gate exists and passes,
- branch is pushed.

Non-goals:

- no live Fireworks matrix required,
- no real classifier required,
- no Docker push required.

## Phase 1: Production-Safe Runtime

Objective: make the submitted container hard to break before making the router smarter.

Deliverables:

- `app/config.py`
- `app/types.py`
- `app/normalization.py`
- `app/telemetry.py`
- `app/deadline.py`
- hardened `app/main.py`
- hardened `app/fireworks_client.py`
- Docker runtime guard script,
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
- support `BATCH_DEADLINE_SECONDS`,
- support `DEADLINE_SAFETY_MARGIN_SECONDS`,
- support `REMOTE_WORKER_COUNT`,
- support `LOCAL_PROOF_BUDGET_MS`,
- support `LOCAL_CROSS_CHECK_ENABLED`,
- support optional `ROUTER_LOG_PATH`,
- never log secrets,
- handle missing Fireworks env vars gracefully when remote fallback is needed,
- handle Fireworks timeout, HTTP error, invalid JSON, missing `choices`, missing `usage`, and disallowed models.
- start a monotonic batch timer early in `main.py`,
- include startup/import/config/input-read time in deadline accounting where practical,
- keep startup work below the 60-second startup sub-budget,
- suppress remote retries when remaining time is too low,
- always leave enough time to normalize answers and write `/output/results.json`,
- keep per-call Fireworks timeout below the 30-second response ceiling.

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
- telemetry includes task timing metrics for local, remote, fallback, and error paths,
- telemetry does not add timing fields to official `/output/results.json`,
- deadline manager remaining-time tests with a fake clock,
- startup budget accounting test,
- no-retry-near-deadline test,
- valid-output-near-deadline test,
- remote timeout remains below per-response ceiling,
- local proof budget config parsing test,
- Docker runtime guard command is available and documented,
- `python3 scripts/run_local_quality_gate.py`,
- `python3 scripts/run_phase1_acceptance.py`,
- `python3 scripts/run_phase1_acceptance.py --include-docker` when Docker Desktop is available.

Quality bar:

- every recoverable failure produces valid final JSON,
- no exception from one task prevents later tasks from completing,
- no deadline path can prevent `/output/results.json` from being written,
- Fireworks errors are sanitized,
- telemetry is optional and never changes official output,
- quality gate summary is produced for evidence.

Trace artifacts:

- quality gate output,
- `eval_runs/phase1_acceptance_latest.json`,
- malformed-input test output,
- deadline-near-exhaustion test output,
- sanitized telemetry example,
- updated submission checklist.

Definition of done:

- all required tests/checks pass,
- no recoverable single-task failure can prevent valid final JSON,
- local quality gate passes,
- Phase 1 acceptance report is produced,
- Docker smoke/size guard command is ready to run and passes before Docker-dependent work.

Stop rules:

- stop Phase 2 work if final JSON can be malformed,
- stop Phase 2 work if missing Fireworks env crashes the batch,
- stop Phase 2 work if a timeout/retry path can consume the whole 10-minute budget,
- stop Phase 2 work if telemetry can leak secrets.

Non-goals:

- no full risk engine yet,
- no broad local proof system yet,
- no live Fireworks optimization yet.

## Phase 2: Real Local-First Router

Objective: replace solver-first routing with classifier/risk/validator routing.

Current status:

- first implementation slice is complete,
- `app/classifier.py` classifies the 8 Track 1 categories locally before any Fireworks call,
- `app/solvers/basic.py` returns structured local solver results internally,
- `app/validators.py` gates local answers through the first proof ladder,
- `app/agent.py` now accepts local answers only when validator/proof layers pass,
- `tests/test_phase2_router.py` covers classifier categories, risk components, local no-Fireworks routing, remote fallback through the wrapper, proof-budget rejection, and classifier-before-remote ordering.

Deliverables:

- `app/classifier.py`
- `app/validators.py`
- structured local solver results,
- intent and constraint extraction,
- answer-shape detection,
- local proof metadata,
- trap guard layer,
- cheap cross-check layer,
- local proof elapsed-time tracking,
- task timing metrics in router decision logs,
- expected route assertions in eval/test fixtures.

Implementation requirements:

- classifier runs before any Fireworks call,
- classifier emits category, confidence, answer shape, constraints, and risk components,
- local solvers return structured results, not raw strings,
- validators check local answers before acceptance,
- local route is allowed only when category confidence, constraint extraction, risk threshold, solver confidence, independent validator, format validator, trap guard, cheap cross-check, and local proof budget all pass,
- trap guards reject known unsafe local patterns such as sarcasm, mixed sentiment, incomplete logic, multi-step math, current/live factual claims, ambiguous entities, and nontrivial code,
- cheap cross-checks run only when they are deterministic and within the local proof budget,
- risky or unsupported tasks route to Fireworks,
- final answer still passes normalization.

Required tests/checks:

- classifier category coverage for all 8 categories,
- risk component coverage,
- local high-confidence tasks do not call Fireworks,
- risky tasks call Fireworks wrapper,
- expected route assertions pass for scenario fixtures,
- validators reject weak local answers,
- trap guards reject false-local adversarial fixtures,
- cross-check failures force Fireworks routing,
- local proof budget exhaustion forces Fireworks routing or safe fallback,
- local accepted answers include proof/evidence metadata,
- router decision logs include per-stage elapsed times,
- local quality gate passes.

Remaining expansion tests:

- expected-route assertions over the full JSONL scenario fixture,
- richer validator rejection tests for weak local summaries, ambiguous NER, and nontrivial code,
- explicit trap-guard cases for sarcasm, incomplete logic, and multi-step math,
- cheap cross-check failure fixtures beyond math/sentiment/simple logic,
- router sweep should use actual router decisions instead of legacy simulated local scores.

Quality bar:

- local answers are accepted only with proof/validator support,
- extra local proof checks improve acceptance precision without threatening the 10-minute runtime budget,
- unsafe local acceptance is treated as a blocking bug,
- expected-route mismatches are explainable and logged,
- router sweep uses actual route decisions.

Trace artifacts:

- router decision JSONL,
- expected-route assertion report,
- updated router sweep report,
- examples of local accept and Fireworks fallback.

Definition of done:

- real router decisions are visible in logs,
- router config sweep uses actual router routes instead of only simulated routes,
- local acceptance is validator-gated,
- no regression in output JSON shape.

Stop rules:

- stop Phase 3 work if local overconfidence appears in adversarial scenarios,
- stop Phase 3 work if classifier can call Fireworks directly,
- stop Phase 3 work if route decisions are not logged in eval/dev mode.

Non-goals:

- no need for every planned validator to be perfect,
- no need for full live model matrix,
- no official submission until Phase 1 remains stable.

## Phase 3: Remote Modes and Configurable Router Modes

Objective: make official submissions comparable and measurable.

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
- retry eligibility is also capped by remaining batch time,
- remote-needed tasks may use a bounded worker pool so independent Fireworks calls can finish faster without changing token usage,
- worker count must be configurable and conservative by default,
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

Quality bar:

- conservative mode should be accuracy-biased,
- aggressive mode should never bypass validators,
- balanced mode should be the default candidate unless evidence says otherwise,
- retry policy is bounded and explainable,
- token-saving changes must not lower pass rate in local eval.

Trace artifacts:

- router config sweep report,
- remote mode comparison report,
- retry/failure examples,
- selected config note in `docs/official-submission-log.md`.

Definition of done:

- router config sweep compares real conservative/balanced/aggressive behavior,
- reports show local route rate, pass rate, and token estimates by config,
- remote mode logs are inspectable,
- one retry policy is bounded and tested.

Stop rules:

- stop live spend if selected model can fall outside `ALLOWED_MODELS`,
- stop official submission if retry can loop,
- stop token optimization if local pass rate drops below threshold.

Non-goals:

- no uncontrolled live spend,
- no official submission without Docker smoke.

## Phase 4: Live Evaluation and Submission Optimization

Objective: use Fireworks credits and official submissions as controlled feedback.

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

Quality bar:

- official submission candidate has local evidence,
- Docker image is reproducible,
- live runs are staged by budget plan,
- every official attempt has a one-variable hypothesis.

Trace artifacts:

- Docker smoke output,
- selected live eval report,
- image tag/digest,
- `docs/official-submission-log.md`,
- final selected router config.

Definition of done:

- Docker image is public and pullable,
- image includes linux/amd64 manifest,
- final output JSON validates,
- selected router config has local evidence,
- official submission log is updated.

Stop rules:

- stop official submissions if Docker pull/run fails,
- stop official submissions if output JSON is malformed,
- stop official submissions if calls bypass `FIREWORKS_BASE_URL`,
- stop live expansion if token fields or response schema look wrong.

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

## Phase Review Template

Use this before moving from one phase to the next:

- Phase:
- Branch/commit:
- Required checks run:
- Reports generated:
- Known failures:
- Risks updated:
- Decision: advance / hold
- Reason:
