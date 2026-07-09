FROM python:3.11-slim

WORKDIR /app

COPY app ./app

ENV ROUTER_MODE=conservative \
    LOCAL_CONFIDENCE_THRESHOLD=0.95 \
    FIREWORKS_MAX_TOKENS=192 \
    ROUTER_PROMPT_POLICY_REMOTE_ACCURACY=original \
    ROUTER_PROMPT_POLICY_REMOTE_CODE=original \
    ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT=original \
    ROUTER_PROMPT_POLICY_REMOTE_CONCISE=original \
    ROUTER_PROMPT_POLICY_BY_CATEGORY=code_generation=compact,factual_knowledge=compact \
    ROUTER_MODELS_REMOTE_ACCURACY=minimax-m3 \
    ROUTER_MODELS_REMOTE_CODE=minimax-m3 \
    ROUTER_MODELS_REMOTE_FORMAT_STRICT=minimax-m3 \
    ROUTER_MODELS_REMOTE_CONCISE=minimax-m3 \
    ROUTER_MODELS_BY_CATEGORY=code_debugging=gemma-4-31b-it,minimax-m3;code_generation=gemma-4-31b-it,minimax-m3;factual_knowledge=kimi-k2p7-code,minimax-m3;logical_deductive_reasoning=gemma-4-26b-a4b-it,minimax-m3;mathematical_reasoning=gemma-4-31b-it,minimax-m3;named_entity_recognition=gemma-4-31b-it,minimax-m3;sentiment_classification=gemma-4-31b-it,minimax-m3;text_summarisation=gemma-4-31b-it,minimax-m3

CMD ["python", "-m", "app.main"]
