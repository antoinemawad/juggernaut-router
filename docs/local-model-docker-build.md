# Local Model Docker Build

Purpose: build a Track 1 image that optionally bundles a small CPU-only GGUF model without downloading weights at runtime.

This lane restores the local GGUF configuration introduced in `281181c`, optimized in `b8b2d4a`, and hardened in `228e8d1`. That image family is known to have passed the AMD evaluator runtime/pipeline contract. It is not being represented as accuracy-proven.

## Default Model

- Model: Qwen2.5-3B-Instruct Q4_K_M
- Repository: `Qwen/Qwen2.5-3B-Instruct-GGUF`
- Source filename: `qwen2.5-3b-instruct-q4_k_m.gguf`
- Image filename: `local-model.gguf`
- In-image path: `/app/models/local-model.gguf`
- Historical URL:

```text
https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
```

## Build-Time Versus Runtime

These Docker build arguments decide whether a model is included in the image:

- `ENABLE_LOCAL_MODEL`
- `LOCAL_MODEL_URL`
- `LOCAL_MODEL_FILENAME`

These runtime variables control use of a model that already exists inside the image:

- `LOCAL_MODEL_ENABLED`
- `LOCAL_MODEL_COMMAND`
- `LOCAL_MODEL_PATH`
- `LOCAL_MODEL_MAX_TOKENS`
- `LOCAL_MODEL_BATCH_LIMIT`
- `LOCAL_MODEL_CONTEXT`
- `LOCAL_MODEL_THREADS`
- `LOCAL_MODEL_TEMPERATURE`
- `LOCAL_MODEL_TIMEOUT_SECONDS`
- `LOCAL_MODEL_MAX_CHARS`

`LOCAL_MODEL_FILENAME` is not a runtime selector. To select among multiple GGUF files already bundled into one image, set `LOCAL_MODEL_PATH`.

## Normal No-Local Build

This is the default. It does not build `llama-cpp-python`, does not install local-model runtime dependencies, and does not download a model.

```bash
DOCKER_BUILDKIT=1 docker build \
  --build-arg ENABLE_LOCAL_MODEL=false \
  -t juggernaut-router:no-local .
```

Expected image default:

```text
LOCAL_MODEL_ENABLED=false
```

## Default Local-Model Build

This downloads the historical Qwen2.5 GGUF at build time and stores it at `/app/models/local-model.gguf`.

```bash
DOCKER_BUILDKIT=1 docker build \
  --build-arg ENABLE_LOCAL_MODEL=true \
  -t juggernaut-router:qwen25-3b .
```

Expected image defaults:

```text
LOCAL_MODEL_ENABLED=true
LOCAL_MODEL_PATH=/app/models/local-model.gguf
LOCAL_MODEL_BATCH_LIMIT=12
LOCAL_MODEL_MAX_TOKENS=128
LOCAL_MODEL_CONTEXT=1024
LOCAL_MODEL_THREADS=2
LOCAL_MODEL_TEMPERATURE=0
LOCAL_MODEL_TIMEOUT_SECONDS=20
LOCAL_MODEL_MAX_CHARS=4096
```

## Existing Bundled GGUF Build

Place the GGUF under `models/` on the build machine. The file remains ignored by git, but Docker can use it during an explicit local-model build.

```bash
DOCKER_BUILDKIT=1 docker build \
  --build-arg ENABLE_LOCAL_MODEL=true \
  --build-arg LOCAL_MODEL_URL= \
  --build-arg LOCAL_MODEL_FILENAME=qwen3-1.7b-q4_k_m.gguf \
  -t juggernaut-router:qwen3-1.7b .
```

The build selects in this order:

1. Exact file matching `/build-models/${LOCAL_MODEL_FILENAME}`
2. Download from `LOCAL_MODEL_URL` into `/app/models/${LOCAL_MODEL_FILENAME}`
3. Deterministic sorted fallback to the first `models/*.gguf`, only when no URL is provided
4. Clear build failure

## Custom URL Build

```bash
DOCKER_BUILDKIT=1 docker build \
  --build-arg ENABLE_LOCAL_MODEL=true \
  --build-arg LOCAL_MODEL_URL="https://example.com/path/model.gguf" \
  --build-arg LOCAL_MODEL_FILENAME=model.gguf \
  -t juggernaut-router:custom-local .
```

The downloader follows HTTPS redirects, rejects failed responses, writes to a partial file first, rejects zero-byte files, and atomically renames the completed file.

## Runtime Controls

Disable local inference without rebuilding:

```bash
docker run --rm \
  -e LOCAL_MODEL_ENABLED=false \
  juggernaut-router:qwen25-3b
```

Select another already-bundled model:

```bash
docker run --rm \
  -e LOCAL_MODEL_PATH=/app/models/qwen3-1.7b-q4_k_m.gguf \
  juggernaut-router:qwen3-1.7b
```

Override the local-model task limit:

```bash
docker run --rm \
  -e LOCAL_MODEL_BATCH_LIMIT=4 \
  juggernaut-router:qwen25-3b
```

Override the local output-token limit:

```bash
docker run --rm \
  -e LOCAL_MODEL_MAX_TOKENS=96 \
  juggernaut-router:qwen25-3b
```

## Fireworks Fallback

The local model is optional. Existing Fireworks routing, prompt policies, and model preferences remain controlled by the Dockerfile runtime variables and evaluator-supplied:

- `FIREWORKS_API_KEY`
- `FIREWORKS_BASE_URL`
- `ALLOWED_MODELS`

No Fireworks key is baked into the image. If local inference is disabled, rejected, timed out, or unavailable, the existing remote/fallback behavior remains responsible for the final answer.

## Verification

Inspect no-local configuration:

```bash
docker image inspect juggernaut-router:no-local
```

Inspect local-model configuration:

```bash
docker image inspect juggernaut-router:qwen25-3b
```

Confirm the model exists and is non-empty:

```bash
docker run --rm \
  --entrypoint sh \
  juggernaut-router:qwen25-3b \
  -c 'ls -lh /app/models && test -s /app/models/local-model.gguf'
```

Run the bounded local-model smoke check:

```bash
IMAGE=juggernaut-router:qwen25-3b \
bash scripts/run_local_docker_check.sh
```

The smoke check runs with `--memory=4g`, `--cpus=2`, writes `results.json`, and prints route counts from the structured log. Do not infer local-model use merely from zero Fireworks tokens; check the route counts.

## Expected Cost

The Qwen2.5 Q4_K_M GGUF is about 2 GB. The final image should remain well below the official 10 GB compressed limit, but first build and first pull are slower than the small Fireworks-only image.

The first local-model build can be slow because `llama-cpp-python` may compile from source. Later builds should be faster because Docker can reuse the wheel-building layer while `requirements-local-model.txt` and the base image stay unchanged.

## Troubleshooting

- 404 model URL: confirm the URL in `LOCAL_MODEL_URL`, or use an existing `models/${LOCAL_MODEL_FILENAME}` with `LOCAL_MODEL_URL=`.
- Missing GGUF: the build fails with `No local GGUF model was found.`
- Zero-byte/incomplete download: the downloader rejects it and leaves no target model.
- Model-load failure: run the `test -s` command above, then inspect container logs for `llama_cpp_import_error` or `local_model_path_missing`.
- Local-model timeout: reduce `LOCAL_MODEL_BATCH_LIMIT`, reduce `LOCAL_MODEL_MAX_TOKENS`, or increase `LOCAL_MODEL_TIMEOUT_SECONDS` within the 10-minute total runtime.
- Local answer rejection: the router can escalate to Fireworks when credentials are available; otherwise it uses the existing safe fallback.
- Fireworks fallback: confirm `FIREWORKS_BASE_URL`, `FIREWORKS_API_KEY`, and `ALLOWED_MODELS` are injected at runtime.
- Output file not written: run `python3 scripts/validate_submission_io.py <results.json>` and inspect structured startup logs for input/output paths.
