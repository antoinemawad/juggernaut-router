# Demo Guide

This guide uses synthetic tasks only. It does not require private evaluator inputs.

## Prerequisites

- Docker installed
- Python 3.11+ available as `python3`
- Repository checked out
- Optional `.env` with Fireworks values for remote routes

## Recommended Demo Mode

Use the standard Docker image first. It is fast, reproducible, and does not require bundling local weights.

```bash
./scripts/demo.sh
```

The script builds `juggernaut-router:demo`, runs `examples/sample_tasks.json`, validates the output schema, and prints the produced answers.

## Manual Demo Commands

```bash
docker build --platform linux/amd64 -t juggernaut-router:demo .

mkdir -p /tmp/juggernaut-demo-output
docker run --rm --platform linux/amd64 \
  -v "$PWD/examples:/input:ro" \
  -v /tmp/juggernaut-demo-output:/output \
  -e INPUT_PATH=/input/sample_tasks.json \
  juggernaut-router:demo

python3 scripts/validate_submission_io.py /tmp/juggernaut-demo-output/results.json
cat /tmp/juggernaut-demo-output/results.json
```

## Demo Scenarios

| Task ID | Category | Expected route shape | What to show |
| --- | --- | --- | --- |
| `demo_sentiment` | Sentiment classification | deterministic or model-backed | Label-only output |
| `demo_math` | Mathematical reasoning | deterministic when pattern is recognized | Exact numeric output |
| `demo_code` | Code generation | deterministic or model-backed | Code-shaped answer |
| `demo_summary` | Text summarisation | deterministic/local/remote depending config | Concise summary |
| `demo_factual` | Factual knowledge | deterministic or remote when configured | Short explanatory answer |

## Confirming Routes

Run with telemetry:

```bash
mkdir -p /tmp/juggernaut-demo-output
docker run --rm --platform linux/amd64 \
  -v "$PWD/examples:/input:ro" \
  -v /tmp/juggernaut-demo-output:/output \
  -e INPUT_PATH=/input/sample_tasks.json \
  -e ROUTER_LOG_PATH=/output/router_log.jsonl \
  juggernaut-router:demo

cat /tmp/juggernaut-demo-output/router_log.jsonl
```

Look for `route` values such as `local`, `local_model`, `fireworks`, or `fallback`.

## Optional Remote Demo

Only run this when credentials are available and token use is intended:

```bash
set -a
source .env
set +a

python3 scripts/check_live_eval_env.py --print-models

docker run --rm --platform linux/amd64 \
  --env-file .env \
  -v "$PWD/examples:/input:ro" \
  -v /tmp/juggernaut-demo-output:/output \
  -e INPUT_PATH=/input/sample_tasks.json \
  -e ROUTER_LOG_PATH=/output/router_log.jsonl \
  juggernaut-router:demo
```

## Optional Local-Model Demo

This requires a GGUF file in `models/local-model.gguf` or a reachable `LOCAL_MODEL_URL`.

```bash
docker build --platform linux/amd64 \
  --build-arg ENABLE_LOCAL_MODEL=true \
  --build-arg LOCAL_MODEL_FILENAME=local-model.gguf \
  -t juggernaut-router:demo-local .
```

Then run the same mounted-input command with `juggernaut-router:demo-local`.

## Cloudflare Worker Demo

The public web demo is in `demo-worker/`. It is a lightweight presentation/demo surface for synthetic tasks only; the Track 1 submission remains the Docker image.

```bash
cd demo-worker
npm install
npm run dev
npm run dry-run
npm run deploy
```

## Recovery Steps

- Missing Docker: install Docker or use the Python local smoke path.
- Missing Fireworks env: use the standard offline demo or create `.env` from `.env.example`.
- Invalid output: run `python3 scripts/validate_submission_io.py <path>`.
- Unexpected fallback: inspect `router_log.jsonl` for `route_reason`, `fireworks_error`, or local-model validation notes.
- Local model too slow: disable it with `LOCAL_MODEL_ENABLED=false` or use the standard build.

## Cleanup

```bash
rm -rf /tmp/juggernaut-demo-output
docker image rm juggernaut-router:demo juggernaut-router:demo-local 2>/dev/null || true
```
