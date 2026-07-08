# Juggernaut Router

Benchmark-driven hybrid LLM routing agent for AMD Developer Hackathon: ACT II.

## Track 1 Runtime Contract

The submitted container defaults to the official harness paths:

- input: `/input/tasks.json`
- output: `/output/results.json`

For local testing only, those paths can be overridden:

- `INPUT_PATH`
- `OUTPUT_PATH`

Fireworks values must come from the environment. Local development may use `--env-file .env`, but `.env` must never be committed or bundled into the submitted image.

Required runtime env vars for live Fireworks fallback:

- `FIREWORKS_API_KEY`
- `FIREWORKS_BASE_URL`
- `ALLOWED_MODELS`

All Fireworks calls are built from `FIREWORKS_BASE_URL`; do not hardcode the normal Fireworks API URL.

Optional prompt-policy tuning env vars:

- `ROUTER_PROMPT_POLICY_REMOTE_ACCURACY`
- `ROUTER_PROMPT_POLICY_REMOTE_CODE`
- `ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT`
- `ROUTER_PROMPT_POLICY_REMOTE_CONCISE`
- `ROUTER_PROMPT_POLICY_BY_CATEGORY`

Allowed values are `original`, `compact`, `answer_only`, and `final_only`. `ROUTER_PROMPT_POLICY_BY_CATEGORY` accepts comma-separated `category=policy` pairs such as `code_generation=compact,mathematical_reasoning=answer_only`. Defaults are evidence-biased but configurable so notebook/live runs can compare models without code changes.

Optional remote model preference env vars:

- `ROUTER_MODELS_REMOTE_ACCURACY`
- `ROUTER_MODELS_REMOTE_CODE`
- `ROUTER_MODELS_REMOTE_FORMAT_STRICT`
- `ROUTER_MODELS_REMOTE_CONCISE`

Values are comma-separated model aliases. The Fireworks client still selects only models present in `ALLOWED_MODELS`.

## Local Smoke Test

```bash
INPUT_PATH=local_test/input/tasks.json \
OUTPUT_PATH=local_test/output/results.json \
python3 -m app.main

python3 scripts/validate_submission_io.py local_test/output/results.json
```

## AMD AI Notebook Checkpoint

Open `notebooks/amd_ai_manual_checkpoint.ipynb` in the AMD AI Notebook connected to this repo. It runs safe local tests, prints commit/manual-test commands, then intentionally stops before live Fireworks or Docker submission work.

Before any live Fireworks/AMD notebook model matrix run, validate the injected env:

```bash
python3 scripts/check_live_eval_env.py --print-models
python3 eval/model_matrix.py --live --limit 2 --models minimax-m3 --prompt-policies original
```

## Router Config Sweep

Before spending official submission attempts, compare candidate router configurations locally:

```bash
python3 eval/router_config_sweep.py --accuracy-threshold 0.85
python3 scripts/recommend_runtime_env.py --from-latest-sweep
```

This produces `eval_runs/router_sweep_*.jsonl` and `eval_runs/router_sweep_*.md`, ranking configurations by accuracy first and token usage second. The env helper converts the winning sweep config into real runtime exports such as `ROUTER_MODE=conservative`; do not set `ROUTER_MODE` to a sweep config name like `strict_hybrid`.

## Production Readiness Checks

Before final submission, verify malformed input handling, Fireworks failure handling, answer normalization, optional router telemetry, and Docker mounted IO. These checks are tracked in `docs/submission-checklist.md` and `docs/test-eval-coverage-plan.md`.

Run the current local quality gate:

```bash
python3 scripts/run_local_quality_gate.py
```

Run the Phase 1 acceptance gate before moving into routing implementation:

```bash
python3 scripts/run_phase1_acceptance.py
```

Include Docker when Docker Desktop is running:

```bash
python3 scripts/run_phase1_acceptance.py --include-docker
```

The acceptance gate writes `eval_runs/phase1_acceptance_latest.json` for demo and submission-prep evidence.

After acceptance, print the latest readiness summary:

```bash
python3 scripts/submission_readiness_report.py --include-docker
```

Tiered eval coverage can also be checked directly:

```bash
python3 scripts/check_eval_coverage.py
python3 scripts/check_eval_coverage.py eval/golden_tier_2_regression.jsonl --profile tier
python3 scripts/check_eval_coverage.py eval/golden_tier_3_adversarial.jsonl --profile tier
```

## Docker Smoke Test

Recommended local guard:

```bash
python3 scripts/check_submission_static.py
python3 scripts/check_docker_runtime.py
```

The static guard checks for forbidden Fireworks URL hardcoding, tracked secrets/env files, Dockerfile scope, and ignore rules. The Docker guard builds a local `linux/amd64` image, checks the image architecture, enforces an 8GB conservative local image-size ceiling, runs mounted `/input` and `/output`, and validates `results.json`.

Manual equivalent:

```bash
docker build --platform linux/amd64 -t juggernaut-router:local .

docker run --rm \
  -v "$PWD/local_test/input:/input:ro" \
  -v "$PWD/local_test/output:/output" \
  juggernaut-router:local

python3 scripts/validate_submission_io.py local_test/output/results.json
```

The official compressed image limit is 10GB. The local guard uses an 8GB ceiling to keep margin.

## Final linux/amd64 Build and Push

Use this for the submitted image, especially from Apple Silicon:

```bash
docker buildx build --platform linux/amd64 \
  --tag <public-registry>/juggernaut-router:latest \
  --push .
```

Before submitting, pull the public image and run it with mounted `/input` and `/output`.

To print the final build/push/check commands from a chosen public image tag:

```bash
python3 scripts/final_submission_commands.py docker.io/<user>/juggernaut-router:act2
```

## Submission Materials

Planning docs for final presentation and demo:

- `docs/presentation-plan.md`
- `docs/video-demo-plan.md`
- `docs/planned-architecture-diagram.md`
- `docs/elite-routing-plan.md`
- `docs/implementation-phases.md`
- `docs/risk-register.md`
- `docs/category-playbooks.md`
- `docs/accuracy-gates.md`
- `docs/eval-field-glossary.md`
- `docs/official-submission-decision-tree.md`
- `docs/live-eval-budget-plan.md`
- `docs/test-eval-coverage-plan.md`
- `docs/model-matrix-evaluation.md`
- `docs/track1-execution-discipline.md`
- `docs/submission-checklist.md`
- `docs/official-submission-log.md`

## Goal

Build a routing system that decides when to use local AMD-hosted inference and when to use remote inference, optimizing:

- accuracy
- token usage
- latency
- cost
- reproducibility

## AMD Infrastructure Proof

Initial sanity testing was run on AMD AI Notebooks with ROCm, PyTorch, and vLLM.

Evidence is stored in:

docs/amd_proof/environment_proof.txt

Confirmed:

- ROCm GPU visible through rocm-smi
- PyTorch GPU available
- vLLM imports successfully
- Qwen/Qwen2.5-0.5B-Instruct runs locally through vLLM

## Planned Strategies

- baseline_remote_all
- baseline_local_all
- hybrid_router

## Project Structure

router/       Routing logic
providers/    Local and remote inference adapters
benchmarks/   Evaluation scripts
data/         Benchmark datasets
results/      Benchmark outputs
docs/         Evidence and technical notes
tests/        Unit tests
scripts/      Utility scripts
