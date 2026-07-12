import json
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
DEFAULT_ACCURACY_FIRST_MODELS = (
    "gemma-4-31b-it",
    "kimi-k2p7-code",
    "gemma-4-26b-a4b-it",
    "minimax-m3",
    "gemma-4-31b-it-nvfp4",
)
RECOMMENDATION_EXPORT_NAMES = {
    "FIREWORKS_DISABLE_MAX_TOKENS",
    "FIREWORKS_MAX_TOKENS",
    "FIREWORKS_MAX_TOKENS_BY_CATEGORY",
    "LOCAL_CONFIDENCE_THRESHOLD",
    "LOCAL_MODEL_COMMAND",
    "LOCAL_MODEL_ENABLED",
    "LOCAL_MODEL_CONTEXT",
    "LOCAL_MODEL_CATEGORIES",
    "LOCAL_MODEL_MAX_CHARS",
    "LOCAL_MODEL_MAX_TOKENS",
    "LOCAL_MODEL_BATCH_LIMIT",
    "LOCAL_MODEL_PATH",
    "LOCAL_MODEL_PATH_BY_CATEGORY",
    "LOCAL_MODEL_TEMPERATURE",
    "LOCAL_MODEL_THREADS",
    "LOCAL_MODEL_TIMEOUT_SECONDS",
    "REMOTE_VALIDATION_ESCALATION_ENABLED",
    "ROUTER_MODE",
    "ROUTER_PROFILE",
    "ROUTER_MODELS_BY_CATEGORY",
    "ROUTER_MODELS_REMOTE_ACCURACY",
    "ROUTER_MODELS_REMOTE_CODE",
    "ROUTER_MODELS_REMOTE_CONCISE",
    "ROUTER_MODELS_REMOTE_ESCALATION",
    "ROUTER_MODELS_REMOTE_FORMAT_STRICT",
    "ROUTER_PROMPT_POLICY_BY_CATEGORY",
    "ROUTER_PROMPT_POLICY_REMOTE_ACCURACY",
    "ROUTER_PROMPT_POLICY_REMOTE_CODE",
    "ROUTER_PROMPT_POLICY_REMOTE_CONCISE",
    "ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT",
}


def _get_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    return _get_int_from(os.environ, name, default, minimum, maximum)


def _get_int_from(env: dict[str, str], name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = env.get(name)
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
    return _get_float_from(os.environ, name, default, minimum, maximum)


def _get_float_from(env: dict[str, str], name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = env.get(name)
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
    return _get_bool_from(os.environ, name, default)


def _get_bool_from(env: dict[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_prompt_policy(name: str, default: str) -> str:
    return _get_prompt_policy_from(os.environ, name, default)


def _get_prompt_policy_from(env: dict[str, str], name: str, default: str) -> str:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    return value if value in PROMPT_POLICIES else default


def _get_prompt_policy_map(name: str) -> dict[str, str]:
    return _get_prompt_policy_map_from(os.environ, name)


def _get_prompt_policy_map_from(env: dict[str, str], name: str) -> dict[str, str]:
    raw = env.get(name, "")
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
    return _get_model_preference_from(os.environ, name, default)


def _get_model_preference_from(env: dict[str, str], name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    models = parse_allowed_models(env.get(name))
    return tuple(models) if models else default


def _get_model_preference_map(name: str) -> dict[str, tuple[str, ...]]:
    return _get_model_preference_map_from(os.environ, name)


def _get_model_preference_map_from(env: dict[str, str], name: str) -> dict[str, tuple[str, ...]]:
    raw = env.get(name, "")
    mapping = {}
    for item in raw.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        category, models_raw = item.split("=", 1)
        category = category.strip()
        models = tuple(parse_allowed_models(models_raw))
        if category and models:
            mapping[category] = models
    return mapping


def _get_int_map_from(
    env: dict[str, str],
    name: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> dict[str, int]:
    raw = env.get(name, "")
    mapping = {}
    for item in raw.split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        category, value_raw = item.split("=", 1)
        category = category.strip()
        try:
            value = int(value_raw.strip())
        except ValueError:
            continue
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        if category:
            mapping[category] = value
    return mapping


def _get_category_set_from(env: dict[str, str], name: str) -> tuple[str, ...]:
    raw = env.get(name, "")
    categories = []
    seen = set()
    for item in raw.split(","):
        category = item.strip()
        if category and category not in seen:
            categories.append(category)
            seen.add(category)
    return tuple(categories)


def _get_path_map_from(env: dict[str, str], name: str) -> dict[str, Path]:
    raw = env.get(name, "")
    mapping = {}
    for item in raw.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        category, path_raw = item.split("=", 1)
        category = category.strip()
        path = path_raw.strip()
        if category and path:
            mapping[category] = Path(path)
    return mapping


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


def _load_recommendation_exports(path: str | None) -> dict[str, str]:
    if not path or not path.strip():
        return {}
    try:
        with Path(path).expanduser().open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    exports = payload.get("exports")
    if not isinstance(exports, dict):
        return {}
    clean = {}
    for key, value in exports.items():
        if key in RECOMMENDATION_EXPORT_NAMES and isinstance(value, str) and value.strip():
            clean[key] = value
    return clean


def _effective_env() -> dict[str, str]:
    env = dict(os.environ)
    recommendation_exports = _load_recommendation_exports(env.get("ROUTER_RECOMMENDATION_PATH"))
    for key, value in recommendation_exports.items():
        if not env.get(key, "").strip():
            env[key] = value
    return env


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
    fireworks_disable_max_tokens: bool = False
    fireworks_max_tokens_by_category: dict[str, int] | None = None
    router_profile: str = "accuracy_gate"
    local_model_enabled: bool = False
    local_model_command: str | None = None
    local_model_path: Path | None = None
    local_model_paths_by_category: dict[str, Path] | None = None
    local_model_max_tokens: int = 128
    local_model_context: int = 1024
    local_model_threads: int = 2
    local_model_temperature: float = 0.0
    local_model_timeout_seconds: int = 20
    local_model_max_chars: int = 4096
    local_model_batch_limit: int = 12
    local_model_categories: tuple[str, ...] = ()
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
    models_by_category: dict[str, tuple[str, ...]] | None = None

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        env = _effective_env()
        router_log_path = env.get("ROUTER_LOG_PATH")
        profile_raw = env.get("ROUTER_PROFILE")
        profile = (profile_raw or "accuracy_gate").strip().lower()
        if profile not in {"accuracy_gate", "token_competitive"}:
            profile = "accuracy_gate"
        if profile_raw:
            default_mode = "accuracy_first" if profile == "accuracy_gate" else "balanced"
        else:
            default_mode = "conservative"
        mode = env.get("ROUTER_MODE", default_mode).strip().lower()
        if mode not in {"conservative", "balanced", "aggressive", "accuracy_first"}:
            mode = default_mode
        local_model_path = env.get("LOCAL_MODEL_PATH")

        return cls(
            input_path=Path(env.get("INPUT_PATH", "/input/tasks.json")),
            output_path=Path(env.get("OUTPUT_PATH", "/output/results.json")),
            router_mode=mode,
            local_confidence_threshold=_get_float_from(env, "LOCAL_CONFIDENCE_THRESHOLD", 0.95, 0.0, 1.0),
            fireworks_timeout_seconds=_get_int_from(env, "FIREWORKS_TIMEOUT_SECONDS", 25, 1, 29),
            fireworks_max_retries=_get_int_from(env, "FIREWORKS_MAX_RETRIES", 0, 0, 3),
            batch_deadline_seconds=_get_int_from(env, "BATCH_DEADLINE_SECONDS", 600, 30, 600),
            deadline_safety_margin_seconds=_get_int_from(env, "DEADLINE_SAFETY_MARGIN_SECONDS", 60, 5, 300),
            remote_worker_count=_get_int_from(env, "REMOTE_WORKER_COUNT", 2, 1, 8),
            local_proof_budget_ms=_get_int_from(env, "LOCAL_PROOF_BUDGET_MS", 100, 1, 5000),
            local_cross_check_enabled=_get_bool_from(env, "LOCAL_CROSS_CHECK_ENABLED", True),
            local_model_enabled=_get_bool_from(env, "LOCAL_MODEL_ENABLED", False),
            local_model_command=env.get("LOCAL_MODEL_COMMAND") or None,
            local_model_path=Path(local_model_path) if local_model_path else None,
            local_model_paths_by_category=_get_path_map_from(env, "LOCAL_MODEL_PATH_BY_CATEGORY"),
            local_model_max_tokens=_get_int_from(env, "LOCAL_MODEL_MAX_TOKENS", 128, 1, 512),
            local_model_context=_get_int_from(env, "LOCAL_MODEL_CONTEXT", 1024, 256, 4096),
            local_model_threads=_get_int_from(env, "LOCAL_MODEL_THREADS", 2, 1, 8),
            local_model_temperature=_get_float_from(env, "LOCAL_MODEL_TEMPERATURE", 0.0, 0.0, 1.0),
            local_model_timeout_seconds=_get_int_from(env, "LOCAL_MODEL_TIMEOUT_SECONDS", 20, 1, 120),
            local_model_max_chars=_get_int_from(env, "LOCAL_MODEL_MAX_CHARS", 4096, 128, 20000),
            local_model_batch_limit=_get_int_from(env, "LOCAL_MODEL_BATCH_LIMIT", 12, 0, 10000),
            local_model_categories=_get_category_set_from(env, "LOCAL_MODEL_CATEGORIES"),
            router_log_path=Path(router_log_path) if router_log_path else None,
            fireworks_api_key=env.get("FIREWORKS_API_KEY"),
            fireworks_base_url=env.get("FIREWORKS_BASE_URL"),
            allowed_models=tuple(parse_allowed_models(env.get("ALLOWED_MODELS"))),
            fireworks_max_tokens=_get_int_from(env, "FIREWORKS_MAX_TOKENS", 256, 1, 4096),
            fireworks_disable_max_tokens=_get_bool_from(env, "FIREWORKS_DISABLE_MAX_TOKENS", False),
            fireworks_max_tokens_by_category=_get_int_map_from(
                env,
                "FIREWORKS_MAX_TOKENS_BY_CATEGORY",
                1,
                4096,
            ),
            router_profile=profile,
            prompt_policy_remote_accuracy=_get_prompt_policy_from(env, "ROUTER_PROMPT_POLICY_REMOTE_ACCURACY", "compact"),
            prompt_policy_remote_code=_get_prompt_policy_from(env, "ROUTER_PROMPT_POLICY_REMOTE_CODE", "answer_only"),
            prompt_policy_remote_format_strict=_get_prompt_policy_from(
                env,
                "ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT",
                "answer_only",
            ),
            prompt_policy_remote_concise=_get_prompt_policy_from(env, "ROUTER_PROMPT_POLICY_REMOTE_CONCISE", "compact"),
            prompt_policy_by_category=_get_prompt_policy_map_from(env, "ROUTER_PROMPT_POLICY_BY_CATEGORY"),
            remote_validation_escalation_enabled=_get_bool_from(env, "REMOTE_VALIDATION_ESCALATION_ENABLED", True),
            models_remote_accuracy=_get_model_preference_from(
                env,
                "ROUTER_MODELS_REMOTE_ACCURACY",
                DEFAULT_REMOTE_ACCURACY_MODELS,
            ),
            models_remote_code=_get_model_preference_from(env, "ROUTER_MODELS_REMOTE_CODE", DEFAULT_REMOTE_CODE_MODELS),
            models_remote_format_strict=_get_model_preference_from(
                env,
                "ROUTER_MODELS_REMOTE_FORMAT_STRICT",
                DEFAULT_REMOTE_FORMAT_STRICT_MODELS,
            ),
            models_remote_concise=_get_model_preference_from(
                env,
                "ROUTER_MODELS_REMOTE_CONCISE",
                DEFAULT_REMOTE_CONCISE_MODELS,
            ),
            models_remote_escalation=_get_model_preference_from(
                env,
                "ROUTER_MODELS_REMOTE_ESCALATION",
                DEFAULT_REMOTE_ESCALATION_MODELS,
            ),
            models_by_category=_get_model_preference_map_from(env, "ROUTER_MODELS_BY_CATEGORY"),
        )

    def first_allowed_model(self) -> str | None:
        return self.allowed_models[0] if self.allowed_models else None
