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

COPY models ./models

RUN mkdir -p /app/models && \
    if [ "${ENABLE_LOCAL_MODEL}" = "true" ]; then \
      target="/app/models/${LOCAL_MODEL_FILENAME}"; \
      if [ -s "${target}" ]; then \
        echo "Using exact bundled model: ${target}"; \
      elif [ -n "${LOCAL_MODEL_URL}" ]; then \
        echo "Downloading local model from configured LOCAL_MODEL_URL into ${target}"; \
        LOCAL_MODEL_URL="${LOCAL_MODEL_URL}" LOCAL_MODEL_TARGET="${target}" python /tmp/download_local_model.py; \
      else \
        fallback="$(find /app/models -maxdepth 1 -type f -name '*.gguf' | sort | head -n 1)"; \
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
ENV ROUTER_PROFILE=accuracy_gate \
    ROUTER_MODE=accuracy_first \
    LOCAL_CONFIDENCE_THRESHOLD=0.98 \
    LOCAL_PROOF_BUDGET_MS=250 \
    LOCAL_CROSS_CHECK_ENABLED=true

# Local GGUF runtime. ENABLE_LOCAL_MODEL is a build arg; runtime can still override LOCAL_MODEL_ENABLED.
ENV LOCAL_MODEL_ENABLED=${ENABLE_LOCAL_MODEL} \
    LOCAL_MODEL_COMMAND= \
    LOCAL_MODEL_PATH=/app/models/${LOCAL_MODEL_FILENAME} \
    LOCAL_MODEL_MAX_TOKENS=128 \
    LOCAL_MODEL_BATCH_LIMIT=6 \
    LOCAL_MODEL_CATEGORIES=sentiment_classification,text_summarisation \
    LOCAL_MODEL_CONTEXT=1024 \
    LOCAL_MODEL_THREADS=2 \
    LOCAL_MODEL_TEMPERATURE=0 \
    LOCAL_MODEL_TIMEOUT_SECONDS=10 \
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
ENV REMOTE_VALIDATION_ESCALATION_ENABLED=true

# Prompt policies.
ENV ROUTER_PROMPT_POLICY_REMOTE_ACCURACY=answer_only \
    ROUTER_PROMPT_POLICY_REMOTE_CODE=answer_only \
    ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT=answer_only \
    ROUTER_PROMPT_POLICY_REMOTE_CONCISE=answer_only \
    ROUTER_PROMPT_POLICY_BY_CATEGORY=sentiment_classification=answer_only;named_entity_recognition=answer_only;mathematical_reasoning=final_only;logical_deductive_reasoning=final_only;code_generation=answer_only;code_debugging=answer_only;factual_knowledge=answer_only;text_summarisation=answer_only

# Remote model preference lists.
ENV ROUTER_MODELS_REMOTE_ACCURACY=gemma-4-31b-it,kimi-k2p7-code,gemma-4-26b-a4b-it,minimax-m3 \
    ROUTER_MODELS_REMOTE_CODE=kimi-k2p7-code,gemma-4-31b-it,gemma-4-26b-a4b-it,minimax-m3 \
    ROUTER_MODELS_REMOTE_FORMAT_STRICT=gemma-4-31b-it,kimi-k2p7-code,gemma-4-26b-a4b-it,minimax-m3 \
    ROUTER_MODELS_REMOTE_CONCISE=gemma-4-26b-a4b-it,gemma-4-31b-it,kimi-k2p7-code,minimax-m3 \
    ROUTER_MODELS_REMOTE_ESCALATION=gemma-4-31b-it,kimi-k2p7-code,gemma-4-26b-a4b-it,minimax-m3

# Category-specific model preferences.
ENV ROUTER_MODELS_BY_CATEGORY=code_debugging=kimi-k2p7-code,gemma-4-31b-it,gemma-4-26b-a4b-it,minimax-m3;code_generation=kimi-k2p7-code,gemma-4-31b-it,gemma-4-26b-a4b-it,minimax-m3;factual_knowledge=gemma-4-31b-it,kimi-k2p7-code,gemma-4-26b-a4b-it,minimax-m3;logical_deductive_reasoning=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3;mathematical_reasoning=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3;named_entity_recognition=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3;sentiment_classification=gemma-4-26b-a4b-it,gemma-4-31b-it,kimi-k2p7-code,minimax-m3;text_summarisation=gemma-4-26b-a4b-it,gemma-4-31b-it,kimi-k2p7-code,minimax-m3

CMD ["python", "-m", "app.main"]
