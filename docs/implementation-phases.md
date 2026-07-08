# Implementation Phases

Purpose: define the exact implementation order for moving from a passing Track 1 runtime to a competitive, evidence-backed final submission.

This plan reflects the clarified scoring rule: final rank is driven by Fireworks token usage through the injected `FIREWORKS_BASE_URL`, using only models from `ALLOWED_MODELS`, after meeting the accuracy threshold. Local inference is optional and untracked as Fireworks token usage, but it can still hurt final output quality, routing decisions, image size, startup time, and runtime reliability.

## Global Engineering Rules

- Keep the submitted runtime CPU-safe unless organizers explicitly confirm final GPU access.
- Keep `/output/results.json` minimal: only `task_id` and `answer`.
- Keep all scored Fireworks calls behind `FIREWORKS_BASE_URL`.
- Keep scored model selection constrained to runtime `ALLOWED_MODELS`.
- Prefer accuracy over token reduction until the accuracy gate is safe.
- Treat the 10-minute container runtime as total wall-clock time from process start, including startup/import/input/output time.
- Treat the 60-second startup rule as a stricter sub-budget inside the 10-minute total unless official harness behavior proves otherwise.
- Keep the compressed Docker image under 10GB.
- Do not bundle large local LLM weights unless measured benefit and image/runtime safety justify it.
- Do not promote a router behavior unless it has a test, scenario, log/report path, and rollback path.
- Do not expand live Fireworks spend until the local quality gate passes.

## Global Quality Gates

Every implementation phase must preserve these checks:

```bash
python3 scripts/run_local_quality_gate.py
python3 scripts/validate_submission_io.py local_test/output/results.json
```

After this plan update, Phase 1 must be rerun with:

```bash
python3 -m unittest discover -s tests
python3 scripts/check_submission_static.py
INPUT_PATH=local_test/input/tasks.json OUTPUT_PATH=local_test/output/results_check.json python3 -m app.main
python3 scripts/validate_submission_io.py local_test/output/results_check.json
```

Before official submission, also run Docker:

```bash
docker buildx build --platform linux/amd64 --tag juggernaut-router:local --load .
docker run --rm -v "$PWD/local_test/input:/input:ro" -v "$PWD/local_test/output:/output" juggernaut-router:local
python3 scripts/validate_submission_io.py local_test/output/results.json
python3 scripts/check_docker_runtime.py
```

## Phase Dependencies

| Phase | Depends On | Unlocks |
| --- | --- | --- |
| Phase 1 | none | safe official IO/runtime contract |
| Phase 2 | Phase 1 | measurable mock/golden routing quality |
| Phase 3 | Phase 2 | live Fireworks model evidence |
| Phase 4 | Phase 3 | optimized router and local inference decision |
| Phase 5 | Phase 4 | judge-safe Docker image |
| Phase 6 | Phase 5 | final evidence package and presentation/demo proof |

## Phase 1: Local Runtime Contract

Status: completed once, but rerun required after this plan update.

Purpose: prove the app runs correctly with the official input/output contract.

Include:

- unit tests,
- official `/input/tasks.json` to `/output/results.json` smoke test,
- output schema validation,
- static submission guard,
- validation-after-answer pipeline check,
- local fallback behavior check,
- no hardcoded secrets/API URLs check,
- confirmation that Fireworks calls use `FIREWORKS_BASE_URL`,
- confirmation that scored Fireworks calls use only `ALLOWED_MODELS`,
- confirmation that local-only paths still work without `FIREWORKS_API_KEY` when remote calls are not needed,
- confirmation that Gemma model names are configurable and restricted to allowed models,
- confirmation that Native.Builder is not required at runtime.

Required rerun:

```bash
python3 -m unittest discover -s tests
python3 scripts/check_submission_static.py
INPUT_PATH=local_test/input/tasks.json OUTPUT_PATH=local_test/output/results_check.json python3 -m app.main
python3 scripts/validate_submission_io.py local_test/output/results_check.json
```

Exit criteria:

- all required checks pass,
- final output objects contain only `task_id` and `answer`,
- local-only tasks can complete without Fireworks credentials,
- missing Fireworks env vars fail closed when remote calls are needed,
- no Native.Builder dependency exists in the runtime path.

## Phase 2: Mock/Golden Routing Quality

Purpose: prove routing logic before live Fireworks evaluation.

Include:

- router scorecard with pass rate, correctness, estimated Fireworks input tokens, output tokens, total tokens, local route/inference usage if present, Gemma selection rate, Gemma skip rate, Gemma escalation rate, fallback rate, latency, and format failure rate,
- task taxonomy for Fireworks model routing: `cheap_model_safe`, `mid_model_required`, `strong_model_required`, `code_model_required`, `reasoning_model_required`, `structured_output_sensitive`, `ambiguous_or_high_risk`, `gemma_safe`, `gemma_risky`, `gemma_bonus_candidate`,
- confidence-based routing with selected route/model, confidence, reason, fallback behavior, and whether Gemma was attempted, skipped, or escalated from,
- validation-after-answer for local outputs, Fireworks outputs, normalization, and escalation on invalid output,
- golden regression tests,
- router config sweep,
- failure-case review loop with task id, expected model/category, actual model/category, failure type, root cause, fix, fixed/not fixed status, and Gemma-specific note when relevant.

Required checks:

```bash
python3 scripts/check_eval_coverage.py
python3 scripts/check_expected_routes.py --config strict_hybrid
python3 scripts/check_expected_routes.py --config strict_hybrid --scenarios eval/golden_tier_2_regression.jsonl
python3 scripts/check_expected_routes.py --config strict_hybrid --scenarios eval/golden_tier_3_adversarial.jsonl
python3 eval/router_config_sweep.py --accuracy-threshold 0.85
python3 scripts/recommend_runtime_env.py --from-latest-sweep
python3 eval/model_matrix.py --prompt-policies all
```

Exit criteria:

- expected route and remote-mode checks pass on core/regression/adversarial fixtures,
- route changes are explainable,
- the selected sweep config has been converted into real runtime env vars; `ROUTER_MODE` must be `conservative`, `balanced`, or `aggressive`, not a sweep config name,
- unsafe local acceptance is treated as a blocking bug,
- mock/golden reports contain enough metrics to compare token-saving and accuracy tradeoffs.

## Phase 3: Live Fireworks Model Matrix

Purpose: identify the cheapest sufficient Fireworks model per task category.

Include:

- validate `FIREWORKS_API_KEY`,
- validate `FIREWORKS_BASE_URL`,
- run tiny live smoke test first,
- run live matrix across all `ALLOWED_MODELS`: `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it-nvfp4`,
- compare prompt policies: `original`, `compact`, `answer_only`,
- measure accuracy, Fireworks input tokens, Fireworks output tokens, total Fireworks tokens, latency, format failures, and category performance for each model/prompt/category,
- add Gemma-specific matrix for accuracy by category, token usage by category, cheapest-sufficient categories, failure categories, default-suitable cases, skip cases, and try-first-then-escalate cases,
- assign cheapest sufficient model per category, including simple/cheap-safe, code, reasoning, summarization, structured output, fallback/general, Gemma-safe, and Gemma-risky tasks,
- record live failure cases.

Required checks:

```bash
python3 scripts/check_live_eval_env.py --print-models
python3 eval/model_matrix.py --live --limit 2 --models minimax-m3 --prompt-policies original
python3 eval/model_matrix.py --live --prompt-policies all
```

Exit criteria:

- token fields and latency fields are sane,
- live calls go through `FIREWORKS_BASE_URL`,
- all model choices are present in `ALLOWED_MODELS`,
- matrix reports can support cheapest-sufficient model decisions.

## Phase 4: Router Optimization and Local Inference Impact Tests

Purpose: optimize Fireworks token usage and explicitly test whether local inference helps or hurts output quality.

Do not assume local inference helps. Test it.

### Part A: Fireworks Cost Router Optimization

Include:

- build cheapest-sufficient Fireworks model selection policy,
- use Phase 3 live results to assign models per task category,
- make Gemma the default candidate for medium/general tasks only if live data supports it,
- add compact prompts where safe,
- add `answer_only` prompts where safe,
- add escalation to stronger Fireworks models when validation fails or confidence is low,
- compare `always_cheapest_fireworks`, `always_strongest_fireworks`, `always_default_fireworks`, `gemma_first_router`, `cost_router`, `cost_router_with_compact_prompts`, `cost_router_with_validation_escalation`, and `gemma_first_router_with_validation_escalation`.

### Part B: Local Inference Impact Tests

Test these configurations separately:

- `no_local_inference_final_router`,
- `local_inference_for_development_only`,
- `local_inference_as_route_suggester`,
- `local_inference_as_format_checker`,
- `local_inference_as_final_answer_generator`.

For each configuration, measure:

- final output accuracy,
- Fireworks input tokens,
- Fireworks output tokens,
- total Fireworks tokens,
- wrong routing decisions caused by local inference,
- format failures caused by local inference,
- fallback/escalation rate,
- Gemma selection/skipping/escalation changes caused by local inference,
- latency,
- startup time,
- Docker compressed image size impact,
- dependency/image bloat impact,
- reliability failures/timeouts.

Required conclusions:

- If local inference only helps development/testing, keep it out of the final runtime.
- If local inference as route suggester lowers accuracy or causes wrong cheap-model choices, disable it.
- If local inference as format checker improves validation without accuracy risk, keep only if lightweight and reliable.
- If local inference as final answer generator reduces accuracy, do not use it.
- Include local inference in final runtime only if it preserves or improves accuracy, reduces scored Fireworks tokens, does not create wrong routing decisions, does not increase format failures, and does not threaten Docker/runtime reliability.
- Default must remain safe. If implemented, local inference must be behind `LOCAL_MODEL_ENABLED=false` until proven.
- Do not add model weights, PyTorch, Transformers, GGUF files, ROCm/CUDA, or other heavy dependencies unless explicitly justified as a later experiment.

Exit criteria:

- cost-router variants are compared with the same scenario set,
- local inference impact is measured or explicitly deferred,
- final default remains safe and reversible.

## Phase 5: Docker/Submission Hardening

Purpose: prove final image is judge-safe.

Include:

- review `requirements.txt` intentionally; empty is acceptable only if runtime is standard-library only,
- build `linux/amd64` Docker image,
- run image with mounted `/input` and `/output`,
- validate `/output/results.json`,
- check compressed image size under 10GB,
- verify `.dockerignore`,
- confirm image excludes `.env`, `.env.*`, `.git`, `.venv`, `__pycache__`, `eval_runs`, `notebooks`, model caches, downloaded models unless intentionally justified, zip files, tar files, local output artifacts, and Native.Builder exports unless intentionally needed and lightweight,
- confirm no secrets or API keys are copied,
- confirm Native.Builder is not needed for the final container to run,
- confirm Fireworks calls use `FIREWORKS_BASE_URL`,
- confirm only `ALLOWED_MODELS` are used for scored Fireworks calls,
- if final image is pushed, pull public image and retest.

Required checks:

```bash
python3 scripts/run_phase1_acceptance.py --include-docker
python3 scripts/submission_readiness_report.py --include-docker
python3 scripts/final_submission_commands.py <public-image-tag>
```

Exit criteria:

- public image is pullable,
- image includes `linux/amd64` manifest,
- image compressed size is under 10GB,
- mounted IO test passes,
- no forbidden artifacts or secrets are included.

## Phase 6: Final Evidence Package

Purpose: prepare the judge-facing proof.

Include:

- final benchmark table,
- token savings versus Fireworks baselines,
- live model selection evidence,
- cheapest-sufficient routing explanation,
- prompt compression evidence,
- Gemma-first routing strategy: where Gemma is used, why Gemma is used, where Gemma is not used, Gemma accuracy/token evidence, Gemma fallback/escalation evidence, and relevance to Best Use of Gemma Models challenge,
- Native.Builder usage note: used only for prototyping/demo if applicable and not required for final runtime unless explicitly allowed,
- local inference impact conclusion: tested configurations, measured effect on output quality, token impact, routing risk, Docker impact, and final include/exclude decision,
- final Docker proof,
- official submission log.

Exit criteria:

- evidence package is internally consistent,
- screenshots/video/slides do not reveal secrets,
- final submission URL, GitHub URL, image tag, and benchmark notes are ready.

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
