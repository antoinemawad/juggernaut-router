import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

from app.config import RuntimeConfig
from app.deadline import DeadlineManager, StageTimer
from app.types import SAFE_FALLBACK_ANSWER


NORMAL_FIREWORKS_HOST = "api.fireworks.ai"


@dataclass
class FireworksResult:
    answer: str
    model: str | None = None
    http_status: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    elapsed_ms: int = 0
    retry_count: int = 0
    error: str | None = None


def ask_fireworks(prompt: str, config: RuntimeConfig | None = None, deadline: DeadlineManager | None = None) -> str:
    return ask_fireworks_structured(prompt, config=config, deadline=deadline).answer


def ask_fireworks_structured(
    prompt: str,
    config: RuntimeConfig | None = None,
    deadline: DeadlineManager | None = None,
    preferred_models: tuple[str, ...] | list[str] | None = None,
    system_prompt: str | None = None,
) -> FireworksResult:
    config = config or RuntimeConfig.from_env()
    timer = StageTimer()

    if not config.fireworks_api_key or not config.fireworks_base_url or not config.allowed_models:
        return FireworksResult(
            answer=SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error="missing_fireworks_environment",
        )

    if deadline is not None and not deadline.can_spend(config.fireworks_timeout_seconds):
        return FireworksResult(
            answer=SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error="deadline_suppressed_remote",
        )

    models = allowed_model_candidates(config, preferred_models)
    if not models:
        return FireworksResult(
            answer=SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error="no_allowed_model",
        )

    url = config.fireworks_base_url.rstrip("/") + "/chat/completions"

    last_error = None
    last_model = None
    max_attempts = config.fireworks_max_retries + 1
    total_attempts = 0
    for model in models:
        last_model = model
        provider_model = provider_model_for_dev(model, config.fireworks_base_url)
        payload = {
            "model": provider_model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt or "Answer accurately and concisely in English."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0,
        }
        if not config.fireworks_disable_max_tokens:
            payload["max_tokens"] = config.fireworks_max_tokens

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config.fireworks_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        for attempt in range(max_attempts):
            total_attempts += 1
            if total_attempts > 1 and deadline is not None and not deadline.should_retry(config.fireworks_timeout_seconds):
                return FireworksResult(
                    answer=SAFE_FALLBACK_ANSWER,
                    model=last_model,
                    elapsed_ms=timer.elapsed_ms(),
                    retry_count=total_attempts - 1,
                    error="deadline_suppressed_retry",
                )
            try:
                with urllib.request.urlopen(request, timeout=config.fireworks_timeout_seconds) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    http_status = getattr(response, "status", None)
                answer = _extract_answer(data)
                usage = data.get("usage") if isinstance(data, dict) else None
                return FireworksResult(
                    answer=answer,
                    model=model,
                    http_status=http_status,
                    completion_tokens=_usage_int(usage, "completion_tokens"),
                    total_tokens=_usage_int(usage, "total_tokens"),
                    elapsed_ms=timer.elapsed_ms(),
                    retry_count=total_attempts - 1,
                )
            except urllib.error.HTTPError as exc:
                last_error = f"fireworks_http_error:{exc.code}:model={model}:{_safe_error_body(exc)}"
            except (TimeoutError, urllib.error.URLError) as exc:
                last_error = f"fireworks_network_error:{type(exc).__name__}:model={model}"
            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
                last_error = f"fireworks_response_error:{type(exc).__name__}:model={model}"

    return FireworksResult(
        answer=SAFE_FALLBACK_ANSWER,
        model=last_model,
        elapsed_ms=timer.elapsed_ms(),
        retry_count=max(0, total_attempts - 1),
        error=last_error or "fireworks_unknown_error",
    )


def _extract_answer(data) -> str:
    if not isinstance(data, dict):
        raise ValueError("response_not_object")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing_choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValueError("missing_message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("missing_content")
    return content.strip()


def _safe_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read(500).decode("utf-8", errors="replace")
    except Exception:
        return ""
    return " ".join(body.split())


def _usage_int(usage, key: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    return value if isinstance(value, int) else None


def select_allowed_model(
    config: RuntimeConfig,
    preferred_models: tuple[str, ...] | list[str] | None = None,
) -> str | None:
    allowed = set(config.allowed_models)
    for model in preferred_models or ():
        if model in allowed:
            return model
    return config.first_allowed_model()


def allowed_model_candidates(
    config: RuntimeConfig,
    preferred_models: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    allowed = set(config.allowed_models)
    candidates = []
    for model in preferred_models or ():
        if model in allowed and model not in candidates:
            candidates.append(model)
    for model in config.allowed_models:
        if model not in candidates:
            candidates.append(model)
    return candidates


def provider_model_for_dev(alias: str, base_url: str | None) -> str:
    if not normal_fireworks_dev_enabled(base_url):
        return alias
    mapping = parse_dev_model_map(os.environ.get("FIREWORKS_DEV_MODEL_MAP", ""))
    return mapping.get(alias, alias)


def normal_fireworks_dev_enabled(base_url: str | None) -> bool:
    if not base_url:
        return False
    return urlparse(base_url).netloc == NORMAL_FIREWORKS_HOST


def parse_dev_model_map(raw: str) -> dict[str, str]:
    mapping = {}
    for item in re.split(r"[,;]", raw):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            continue
        alias, provider_model = item.split("=", 1)
        alias = alias.strip()
        provider_model = provider_model.strip()
        if alias and provider_model:
            mapping[alias] = provider_model
    return mapping
