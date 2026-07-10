# syntax=docker/dockerfile:1.6

FROM python:3.11-slim AS local-model-deps

WORKDIR /app

ARG ENABLE_LOCAL_MODEL=false

COPY requirements-local-model.txt ./requirements-local-model.txt

RUN mkdir -p /wheels && \
    if [ "${ENABLE_LOCAL_MODEL}" = "true" ]; then \
      apt-get update && \
      apt-get install -y --no-install-recommends build-essential cmake ca-certificates && \
      pip wheel --prefer-binary --wheel-dir=/wheels -r requirements-local-model.txt && \
      rm -rf /var/lib/apt/lists/*; \
    fi

FROM python:3.11-slim

WORKDIR /app

ARG ENABLE_LOCAL_MODEL=false
ARG LOCAL_MODEL_URL=https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
ARG LOCAL_MODEL_FILENAME=local-model.gguf

COPY requirements-local-model.txt ./requirements-local-model.txt
COPY scripts/download_local_model.py /tmp/download_local_model.py
COPY --from=local-model-deps /wheels /wheels

RUN mkdir -p /app/models && \
    if [ "${ENABLE_LOCAL_MODEL}" = "true" ]; then \
      apt-get update && \
      apt-get install -y --no-install-recommends ca-certificates libgomp1 && \
      pip install --no-cache-dir --no-index --find-links=/wheels -r requirements-local-model.txt && \
      rm -rf /wheels /var/lib/apt/lists/*; \
    else \
      rm -rf /wheels; \
    fi

RUN --mount=type=bind,source=models,target=/build-models,ro \
    mkdir -p /app/models && \
    if [ "${ENABLE_LOCAL_MODEL}" = "true" ]; then \
      exact="/build-models/${LOCAL_MODEL_FILENAME}"; \
      target="/app/models/${LOCAL_MODEL_FILENAME}"; \
      if [ -f "${exact}" ]; then \
        echo "Using exact bundled model: ${exact}"; \
        cp "${exact}" "${target}"; \
      elif [ -n "${LOCAL_MODEL_URL}" ]; then \
        echo "Downloading local model from configured LOCAL_MODEL_URL into ${target}"; \
        LOCAL_MODEL_URL="${LOCAL_MODEL_URL}" LOCAL_MODEL_TARGET="${target}" python /tmp/download_local_model.py; \
      else \
        fallback="$(find /build-models -maxdepth 1 -type f -name '*.gguf' | sort | head -n 1)"; \
        if [ -n "${fallback}" ]; then \
          echo "Using deterministic fallback model: ${fallback}"; \
          cp "${fallback}" "${target}"; \
        else \
          echo "No local GGUF model was found." >&2; \
          exit 12; \
        fi; \
      fi; \
      test -s "${target}"; \
      ls -lh "${target}"; \
    fi && \
    rm -f /tmp/download_local_model.py

COPY app ./app

# AMD input/output paths.
ENV INPUT_PATH=/input/tasks.json \
    OUTPUT_PATH=/output/results.json

# Runtime-only evaluator variables, intentionally not assigned here:
# FIREWORKS_API_KEY
# FIREWORKS_BASE_URL
# ALLOWED_MODELS
# ROUTER_LOG_PATH
# ROUTER_RECOMMENDATION_PATH

# Router profile and deterministic/local gate.
ENV ROUTER_PROFILE=token_competitive \
    ROUTER_MODE=balanced \
    LOCAL_CONFIDENCE_THRESHOLD=1.0 \
    LOCAL_PROOF_BUDGET_MS=100 \
    LOCAL_CROSS_CHECK_ENABLED=false

# Local GGUF runtime. ENABLE_LOCAL_MODEL is a build arg; runtime can still override LOCAL_MODEL_ENABLED.
ENV LOCAL_MODEL_ENABLED=${ENABLE_LOCAL_MODEL} \
    LOCAL_MODEL_COMMAND= \
    LOCAL_MODEL_PATH=/app/models/${LOCAL_MODEL_FILENAME} \
    LOCAL_MODEL_MAX_TOKENS=128 \
    LOCAL_MODEL_BATCH_LIMIT=12 \
    LOCAL_MODEL_CONTEXT=1024 \
    LOCAL_MODEL_THREADS=2 \
    LOCAL_MODEL_TEMPERATURE=0 \
    LOCAL_MODEL_TIMEOUT_SECONDS=20 \
    LOCAL_MODEL_MAX_CHARS=4096

# Batch deadline and concurrency.
ENV BATCH_DEADLINE_SECONDS=600 \
    DEADLINE_SAFETY_MARGIN_SECONDS=10 \
    REMOTE_WORKER_COUNT=6

# Fireworks request controls.
ENV FIREWORKS_TIMEOUT_SECONDS=25 \
    FIREWORKS_DISABLE_MAX_TOKENS=false \
    FIREWORKS_MAX_TOKENS=256 \
    FIREWORKS_MAX_RETRIES=1

# Per-category output-token controls.
ENV FIREWORKS_MAX_TOKENS_BY_CATEGORY=sentiment_classification=16,named_entity_recognition=96,mathematical_reasoning=192,logical_deductive_reasoning=192,factual_knowledge=192,text_summarisation=256,code_generation=512,code_debugging=384

# Remote validation and escalation.
ENV REMOTE_VALIDATION_ESCALATION_ENABLED=false

# Prompt policies.
ENV ROUTER_PROMPT_POLICY_REMOTE_ACCURACY=compact \
    ROUTER_PROMPT_POLICY_REMOTE_CODE=compact \
    ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT=answer_only \
    ROUTER_PROMPT_POLICY_REMOTE_CONCISE=compact \
    ROUTER_PROMPT_POLICY_BY_CATEGORY=sentiment_classification=answer_only;named_entity_recognition=answer_only;mathematical_reasoning=final_only;logical_deductive_reasoning=final_only;code_generation=compact;code_debugging=compact;factual_knowledge=compact;text_summarisation=compact

# Remote model preference lists.
ENV ROUTER_MODELS_REMOTE_ACCURACY=minimax-m3,gemma-4-31b-it,kimi-k2p7-code,gemma-4-26b-a4b-it \
    ROUTER_MODELS_REMOTE_CODE=kimi-k2p7-code,minimax-m3,gemma-4-31b-it \
    ROUTER_MODELS_REMOTE_FORMAT_STRICT=minimax-m3,gemma-4-31b-it,kimi-k2p7-code \
    ROUTER_MODELS_REMOTE_CONCISE=minimax-m3,gemma-4-26b-a4b-it,gemma-4-31b-it \
    ROUTER_MODELS_REMOTE_ESCALATION=gemma-4-31b-it,kimi-k2p7-code,minimax-m3

# Category-specific model preferences.
ENV ROUTER_MODELS_BY_CATEGORY=code_debugging=kimi-k2p7-code,minimax-m3,gemma-4-31b-it;code_generation=kimi-k2p7-code,minimax-m3,gemma-4-31b-it;factual_knowledge=minimax-m3,gemma-4-31b-it,kimi-k2p7-code;logical_deductive_reasoning=gemma-4-31b-it,minimax-m3,kimi-k2p7-code;mathematical_reasoning=gemma-4-31b-it,minimax-m3,kimi-k2p7-code;named_entity_recognition=minimax-m3,gemma-4-31b-it,kimi-k2p7-code;sentiment_classification=minimax-m3,gemma-4-31b-it,kimi-k2p7-code;text_summarisation=minimax-m3,gemma-4-31b-it,kimi-k2p7-code

CMD ["python", "-m", "app.main"]
