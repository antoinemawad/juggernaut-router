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

ENV ROUTER_PROFILE=token_competitive \
    ROUTER_MODE=balanced \
    LOCAL_CONFIDENCE_THRESHOLD=1.0 \
    LOCAL_CROSS_CHECK_ENABLED=false \
    LOCAL_MODEL_ENABLED=false \
    REMOTE_VALIDATION_ESCALATION_ENABLED=false \
    LOCAL_MODEL_PATH=/app/models/${LOCAL_MODEL_FILENAME} \
    LOCAL_MODEL_MAX_TOKENS=128 \
    LOCAL_MODEL_BATCH_LIMIT=0 \
    LOCAL_MODEL_CONTEXT=1024 \
    LOCAL_MODEL_THREADS=2 \
    LOCAL_MODEL_TEMPERATURE=0 \
    LOCAL_MODEL_TIMEOUT_SECONDS=20 \
    BATCH_DEADLINE_SECONDS=600 \
    DEADLINE_SAFETY_MARGIN_SECONDS=10 \
    REMOTE_WORKER_COUNT=6 \
    FIREWORKS_TIMEOUT_SECONDS=25 \
    FIREWORKS_DISABLE_MAX_TOKENS=false \
    FIREWORKS_MAX_TOKENS=256 \
    FIREWORKS_MAX_TOKENS_BY_CATEGORY=sentiment_classification=16,named_entity_recognition=96,mathematical_reasoning=192,logical_deductive_reasoning=192,factual_knowledge=192,text_summarisation=256,code_generation=512,code_debugging=384 \
    FIREWORKS_MAX_RETRIES=1 \
    ROUTER_PROMPT_POLICY_REMOTE_ACCURACY=compact \
    ROUTER_PROMPT_POLICY_REMOTE_CODE=compact \
    ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT=answer_only \
    ROUTER_PROMPT_POLICY_REMOTE_CONCISE=compact \
    ROUTER_PROMPT_POLICY_BY_CATEGORY=sentiment_classification=answer_only;named_entity_recognition=answer_only;mathematical_reasoning=final_only;logical_deductive_reasoning=final_only;code_generation=compact;code_debugging=compact;factual_knowledge=compact;text_summarisation=compact \
    ROUTER_MODELS_REMOTE_ACCURACY=minimax-m3,gemma-4-31b-it,kimi-k2p7-code,gemma-4-26b-a4b-it \
    ROUTER_MODELS_REMOTE_CODE=kimi-k2p7-code,minimax-m3,gemma-4-31b-it \
    ROUTER_MODELS_REMOTE_FORMAT_STRICT=minimax-m3,gemma-4-31b-it,kimi-k2p7-code \
    ROUTER_MODELS_REMOTE_CONCISE=minimax-m3,gemma-4-26b-a4b-it,gemma-4-31b-it \
    ROUTER_MODELS_REMOTE_ESCALATION=gemma-4-31b-it,kimi-k2p7-code,minimax-m3 \
    ROUTER_MODELS_BY_CATEGORY=code_debugging=kimi-k2p7-code,minimax-m3,gemma-4-31b-it;code_generation=kimi-k2p7-code,minimax-m3,gemma-4-31b-it;factual_knowledge=minimax-m3,gemma-4-31b-it,kimi-k2p7-code;logical_deductive_reasoning=gemma-4-31b-it,minimax-m3,kimi-k2p7-code;mathematical_reasoning=gemma-4-31b-it,minimax-m3,kimi-k2p7-code;named_entity_recognition=minimax-m3,gemma-4-31b-it,kimi-k2p7-code;sentiment_classification=minimax-m3,gemma-4-31b-it,kimi-k2p7-code;text_summarisation=minimax-m3,gemma-4-31b-it,kimi-k2p7-code
CMD ["python", "-m", "app.main"]
