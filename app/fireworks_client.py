import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.config import RuntimeConfig
from app.deadline import DeadlineManager, StageTimer
from app.types import SAFE_FALLBACK_ANSWER


@dataclass
class FireworksResult:
    answer: str
    model: str | None = None
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

    model = select_allowed_model(config, preferred_models)
    if model is None:
        return FireworksResult(
            answer=SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error="no_allowed_model",
        )

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Answer accurately and concisely in English."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0,
        "max_tokens": config.fireworks_max_tokens,
    }

    url = config.fireworks_base_url.rstrip("/") + "/chat/completions"

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.fireworks_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    last_error = None
    max_attempts = config.fireworks_max_retries + 1
    for attempt in range(max_attempts):
        if attempt > 0 and deadline is not None and not deadline.should_retry(config.fireworks_timeout_seconds):
            return FireworksResult(
                answer=SAFE_FALLBACK_ANSWER,
                model=model,
                elapsed_ms=timer.elapsed_ms(),
                retry_count=attempt,
                error="deadline_suppressed_retry",
            )
        try:
            with urllib.request.urlopen(request, timeout=config.fireworks_timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
            answer = _extract_answer(data)
            usage = data.get("usage") if isinstance(data, dict) else None
            return FireworksResult(
                answer=answer,
                model=model,
                completion_tokens=_usage_int(usage, "completion_tokens"),
                total_tokens=_usage_int(usage, "total_tokens"),
                elapsed_ms=timer.elapsed_ms(),
                retry_count=attempt,
            )
        except (TimeoutError, urllib.error.URLError) as exc:
            last_error = f"fireworks_network_error:{type(exc).__name__}"
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            last_error = f"fireworks_response_error:{type(exc).__name__}"

    return FireworksResult(
        answer=SAFE_FALLBACK_ANSWER,
        model=model,
        elapsed_ms=timer.elapsed_ms(),
        retry_count=max_attempts - 1,
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
