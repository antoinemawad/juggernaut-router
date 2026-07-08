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

PROMPT_POLICIES = {"original", "compact", "answer_only", "final_only"}
DEFAULT_REMOTE_ACCURACY_MODELS = ("minimax-m3", "gemma-4-31b-it", "kimi-k2p7-code")
DEFAULT_REMOTE_CODE_MODELS = ("kimi-k2p7-code", "minimax-m3", "gemma-4-31b-it")
DEFAULT_REMOTE_FORMAT_STRICT_MODELS = ("minimax-m3", "kimi-k2p7-code", "gemma-4-31b-it")
DEFAULT_REMOTE_CONCISE_MODELS = ("minimax-m3", "gemma-4-26b-a4b-it", "gemma-4-31b-it")
DEFAULT_REMOTE_ESCALATION_MODELS = ("kimi-k2p7-code", "minimax-m3", "gemma-4-31b-it")


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


def _get_prompt_policy(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    return value if value in PROMPT_POLICIES else default


def _get_prompt_policy_map(name: str) -> dict[str, str]:
    raw = os.environ.get(name, "")
    mapping = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            continue
        category, policy = item.split("=", 1)
        category = category.strip()
        policy = policy.strip().lower()
        if category and policy in PROMPT_POLICIES:
            mapping[category] = policy
    return mapping


def _get_model_preference(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    models = parse_allowed_models(os.environ.get(name))
    return tuple(models) if models else default


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
    prompt_policy_remote_accuracy: str = "compact"
    prompt_policy_remote_code: str = "answer_only"
    prompt_policy_remote_format_strict: str = "answer_only"
    prompt_policy_remote_concise: str = "compact"
    prompt_policy_by_category: dict[str, str] | None = None
    remote_validation_escalation_enabled: bool = True
    models_remote_accuracy: tuple[str, ...] = DEFAULT_REMOTE_ACCURACY_MODELS
    models_remote_code: tuple[str, ...] = DEFAULT_REMOTE_CODE_MODELS
    models_remote_format_strict: tuple[str, ...] = DEFAULT_REMOTE_FORMAT_STRICT_MODELS
    models_remote_concise: tuple[str, ...] = DEFAULT_REMOTE_CONCISE_MODELS
    models_remote_escalation: tuple[str, ...] = DEFAULT_REMOTE_ESCALATION_MODELS

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
            prompt_policy_remote_accuracy=_get_prompt_policy("ROUTER_PROMPT_POLICY_REMOTE_ACCURACY", "compact"),
            prompt_policy_remote_code=_get_prompt_policy("ROUTER_PROMPT_POLICY_REMOTE_CODE", "answer_only"),
            prompt_policy_remote_format_strict=_get_prompt_policy(
                "ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT",
                "answer_only",
            ),
            prompt_policy_remote_concise=_get_prompt_policy("ROUTER_PROMPT_POLICY_REMOTE_CONCISE", "compact"),
            prompt_policy_by_category=_get_prompt_policy_map("ROUTER_PROMPT_POLICY_BY_CATEGORY"),
            remote_validation_escalation_enabled=_get_bool("REMOTE_VALIDATION_ESCALATION_ENABLED", True),
            models_remote_accuracy=_get_model_preference(
                "ROUTER_MODELS_REMOTE_ACCURACY",
                DEFAULT_REMOTE_ACCURACY_MODELS,
            ),
            models_remote_code=_get_model_preference("ROUTER_MODELS_REMOTE_CODE", DEFAULT_REMOTE_CODE_MODELS),
            models_remote_format_strict=_get_model_preference(
                "ROUTER_MODELS_REMOTE_FORMAT_STRICT",
                DEFAULT_REMOTE_FORMAT_STRICT_MODELS,
            ),
            models_remote_concise=_get_model_preference(
                "ROUTER_MODELS_REMOTE_CONCISE",
                DEFAULT_REMOTE_CONCISE_MODELS,
            ),
            models_remote_escalation=_get_model_preference(
                "ROUTER_MODELS_REMOTE_ESCALATION",
                DEFAULT_REMOTE_ESCALATION_MODELS,
            ),
        )

    def first_allowed_model(self) -> str | None:
        return self.allowed_models[0] if self.allowed_models else None
