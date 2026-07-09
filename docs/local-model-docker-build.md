# Local Model Docker Build

Purpose: build a Track 1 image that bundles a small CPU-only GGUF model without downloading weights at runtime.

## Expected Shape

- Runtime: linux/amd64, CPU-only.
- Target evaluator limit: 4 GB RAM, 2 vCPU.
- Model class: 2B-3B 4-bit GGUF.
- No Ollama dependency.
- No model download during container startup.
- Compressed image must stay under 10 GB.

## Build Strategy

The Dockerfile uses a dependency builder stage for `llama-cpp-python`.

The first local-model build can be slow because `llama-cpp-python` may compile from source. Later builds should be faster because Docker can reuse the wheel-building layer as long as `requirements-local-model.txt` and the base image do not change.

Layer order is intentional:

1. Copy `requirements-local-model.txt`.
2. Build/install local-model Python dependencies.
3. Copy application code.
4. Copy or download `models/local-model.gguf`.

This keeps normal app-code edits from forcing a llama.cpp rebuild.

## Recommended Build On AMD64

Place the GGUF in `models/local-model.gguf` on the build machine, then run:

```bash
docker build \
  --build-arg ENABLE_LOCAL_MODEL=true \
  --build-arg LOCAL_MODEL_FILENAME=local-model.gguf \
  -t ghcr.io/antoinemawad/juggernaut-router:track1-local-model-accuracy-20260709 .
```

Expected signs of a real local-model image:

- Build context is roughly 2 GB or more when `models/local-model.gguf` exists.
- Build args are consumed.
- Final image size is roughly 2 GB or more, not 45 MB.
- `/app/models/local-model.gguf` exists in the image.

## Optional Build-Time Download

Build-time download is allowed; runtime download is not.

```bash
docker build \
  --build-arg ENABLE_LOCAL_MODEL=true \
  --build-arg LOCAL_MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf" \
  --build-arg LOCAL_MODEL_FILENAME=local-model.gguf \
  -t ghcr.io/antoinemawad/juggernaut-router:track1-local-model-accuracy-20260709 .
```

For reliability, prefer copying a known GGUF into `models/` before build.

## Weak Build Machines

A 1 vCPU / 2 GB RAM droplet may take a long time to compile `llama-cpp-python`, or may fail. If it fails:

- Use a stronger temporary builder.
- Use GitHub Actions on linux/amd64.
- Try again after Docker has cached partial layers.
- Prefer prebuilt wheels when available; the Dockerfile uses `pip wheel --prefer-binary`, but source compile may still happen if no compatible wheel is available.

## Runtime Verification

After building locally:

```bash
IMAGE=ghcr.io/antoinemawad/juggernaut-router:track1-local-model-accuracy-20260709 \
bash scripts/run_local_docker_check.sh
```

The check runs with:

- `--memory=4g`
- `--cpus=2`
- `LOCAL_MODEL_ENABLED=true`

It fails if `results.json` is empty or answer count does not match task count.

## Build Context Hygiene

Only keep `models/local-model.gguf` in the repo directory when building the local-model image. Normal small-image builds should be run without large GGUF files in `models/`.

The model file is intentionally ignored by git. Commit only `models/.gitkeep`, never the GGUF.
