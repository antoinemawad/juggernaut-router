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
ARG LOCAL_MODEL_URL=
ARG LOCAL_MODEL_FILENAME=local-model.gguf

COPY requirements-local-model.txt ./requirements-local-model.txt
COPY --from=local-model-deps /wheels /wheels

RUN mkdir -p /app/models && \
    if [ "${ENABLE_LOCAL_MODEL}" = "true" ]; then \
      apt-get update && \
      apt-get install -y --no-install-recommends ca-certificates libgomp1 && \
      pip install --no-cache-dir --no-index --find-links=/wheels -r requirements-local-model.txt && \
      rm -rf /wheels /var/lib/apt/lists/*; \
    fi

COPY models ./models

RUN mkdir -p /app/models && \
    if [ "${ENABLE_LOCAL_MODEL}" = "true" ]; then \
      if [ -n "${LOCAL_MODEL_URL}" ]; then \
        python -c "import os, urllib.request; urllib.request.urlretrieve(os.environ['LOCAL_MODEL_URL'], '/app/models/' + os.environ['LOCAL_MODEL_FILENAME'])"; \
      fi && \
      if [ ! -f "/app/models/${LOCAL_MODEL_FILENAME}" ]; then \
        first_model=$(find /app/models -maxdepth 1 -type f -name '*.gguf' | head -1); \
        if [ -n "$first_model" ]; then cp "$first_model" "/app/models/${LOCAL_MODEL_FILENAME}"; fi; \
      fi && \
      test -f "/app/models/${LOCAL_MODEL_FILENAME}"; \
    fi

COPY app ./app

ENV ROUTER_PROFILE=accuracy_gate \
    ROUTER_MODE=conservative \
    LOCAL_CONFIDENCE_THRESHOLD=1.0 \
    LOCAL_MODEL_ENABLED=false \
    LOCAL_MODEL_PATH=/app/models/${LOCAL_MODEL_FILENAME} \
    LOCAL_MODEL_MAX_TOKENS=128 \
    LOCAL_MODEL_BATCH_LIMIT=0 \
    LOCAL_MODEL_CONTEXT=1024 \
    LOCAL_MODEL_THREADS=2 \
    LOCAL_MODEL_TEMPERATURE=0 \
    LOCAL_MODEL_TIMEOUT_SECONDS=20 \
    FIREWORKS_MAX_TOKENS=256 \
    FIREWORKS_MAX_RETRIES=1 \
    ROUTER_PROMPT_POLICY_REMOTE_ACCURACY=original \
    ROUTER_PROMPT_POLICY_REMOTE_CODE=original \
    ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT=original \
    ROUTER_PROMPT_POLICY_REMOTE_CONCISE=original \
    ROUTER_PROMPT_POLICY_BY_CATEGORY=code_generation=compact,factual_knowledge=compact \
    ROUTER_MODELS_REMOTE_ACCURACY=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3,gemma-4-31b-it-nvfp4 \
    ROUTER_MODELS_REMOTE_CODE=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3,gemma-4-31b-it-nvfp4 \
    ROUTER_MODELS_REMOTE_FORMAT_STRICT=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3,gemma-4-31b-it-nvfp4 \
    ROUTER_MODELS_REMOTE_CONCISE=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3,gemma-4-31b-it-nvfp4 \
    ROUTER_MODELS_REMOTE_ESCALATION=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3,gemma-4-31b-it-nvfp4 \
    ROUTER_MODELS_BY_CATEGORY=code_debugging=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3;code_generation=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3;factual_knowledge=kimi-k2p7-code,gemma-4-31b-it,gemma-4-26b-a4b-it,minimax-m3;logical_deductive_reasoning=gemma-4-26b-a4b-it,gemma-4-31b-it,kimi-k2p7-code,minimax-m3;mathematical_reasoning=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3;named_entity_recognition=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3;sentiment_classification=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3;text_summarisation=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3

CMD ["python", "-m", "app.main"]
