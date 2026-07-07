import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ALLOWED_PLANNING_MODELS = (
    "minimax-m3",
    "kimi-k2p7-code",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
    "gemma-4-31b-it-nvfp4",
)


def _get_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        value = default
    else:
        try:
            value = int(raw)
        except ValueError:
            value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _get_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        value = default
    else:
        try:
            value = float(raw)
        except ValueError:
            value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def parse_allowed_models(raw: str | None) -> list[str]:
    if not raw:
        return []
    models = []
    seen = set()
    for item in raw.split(","):
        model = item.strip()
        if model and model not in seen:
            models.append(model)
            seen.add(model)
    return models


@dataclass(frozen=True)
class RuntimeConfig:
    input_path: Path
    output_path: Path
    router_mode: str
    local_confidence_threshold: float
    fireworks_timeout_seconds: int
    fireworks_max_retries: int
    batch_deadline_seconds: int
    deadline_safety_margin_seconds: int
    remote_worker_count: int
    local_proof_budget_ms: int
    local_cross_check_enabled: bool
    router_log_path: Path | None
    fireworks_api_key: str | None
    fireworks_base_url: str | None
    allowed_models: tuple[str, ...]
    fireworks_max_tokens: int

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        router_log_path = os.environ.get("ROUTER_LOG_PATH")
        mode = os.environ.get("ROUTER_MODE", "conservative").strip().lower()
        if mode not in {"conservative", "balanced", "aggressive"}:
            mode = "conservative"

        return cls(
            input_path=Path(os.environ.get("INPUT_PATH", "/input/tasks.json")),
            output_path=Path(os.environ.get("OUTPUT_PATH", "/output/results.json")),
            router_mode=mode,
            local_confidence_threshold=_get_float("LOCAL_CONFIDENCE_THRESHOLD", 0.95, 0.0, 1.0),
            fireworks_timeout_seconds=_get_int("FIREWORKS_TIMEOUT_SECONDS", 25, 1, 29),
            fireworks_max_retries=_get_int("FIREWORKS_MAX_RETRIES", 0, 0, 3),
            batch_deadline_seconds=_get_int("BATCH_DEADLINE_SECONDS", 600, 30, 600),
            deadline_safety_margin_seconds=_get_int("DEADLINE_SAFETY_MARGIN_SECONDS", 60, 5, 300),
            remote_worker_count=_get_int("REMOTE_WORKER_COUNT", 2, 1, 8),
            local_proof_budget_ms=_get_int("LOCAL_PROOF_BUDGET_MS", 100, 1, 5000),
            local_cross_check_enabled=_get_bool("LOCAL_CROSS_CHECK_ENABLED", True),
            router_log_path=Path(router_log_path) if router_log_path else None,
            fireworks_api_key=os.environ.get("FIREWORKS_API_KEY"),
            fireworks_base_url=os.environ.get("FIREWORKS_BASE_URL"),
            allowed_models=tuple(parse_allowed_models(os.environ.get("ALLOWED_MODELS"))),
            fireworks_max_tokens=_get_int("FIREWORKS_MAX_TOKENS", 256, 1, 4096),
        )

    def first_allowed_model(self) -> str | None:
        return self.allowed_models[0] if self.allowed_models else None
