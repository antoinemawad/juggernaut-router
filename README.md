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

## Local Smoke Test

```bash
INPUT_PATH=local_test/input/tasks.json \
OUTPUT_PATH=local_test/output/results.json \
python3 -m app.main

python3 scripts/validate_submission_io.py local_test/output/results.json
```

## AMD AI Notebook Checkpoint

Open `notebooks/amd_ai_manual_checkpoint.ipynb` in the AMD AI Notebook connected to this repo. It runs safe local tests, prints commit/manual-test commands, then intentionally stops before live Fireworks or Docker submission work.

## Router Config Sweep

Before spending official submission attempts, compare candidate router configurations locally:

```bash
python3 eval/router_config_sweep.py --accuracy-threshold 0.85
```

This produces `eval_runs/router_sweep_*.jsonl` and `eval_runs/router_sweep_*.md`, ranking configurations by accuracy first and token usage second.

## Docker Smoke Test

```bash
docker build -t juggernaut-router:local .

docker run --rm \
  -v "$PWD/local_test/input:/input:ro" \
  -v "$PWD/local_test/output:/output" \
  juggernaut-router:local

python3 scripts/validate_submission_io.py local_test/output/results.json
```

## Final linux/amd64 Build and Push

Use this for the submitted image, especially from Apple Silicon:

```bash
docker buildx build --platform linux/amd64 \
  --tag <public-registry>/juggernaut-router:latest \
  --push .
```

Before submitting, pull the public image and run it with mounted `/input` and `/output`.

## Submission Materials

Planning docs for final presentation and demo:

- `docs/presentation-plan.md`
- `docs/video-demo-plan.md`
- `docs/elite-routing-plan.md`
- `docs/test-eval-coverage-plan.md`
- `docs/model-matrix-evaluation.md`
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
