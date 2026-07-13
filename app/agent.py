from dataclasses import replace

from app.classifier import classify_prompt
from app.config import DEFAULT_ACCURACY_FIRST_MODELS, RuntimeConfig
from app.deadline import DeadlineManager, StageTimer
from app.fireworks_client import ask_fireworks_structured
from app.local_model_client import ask_local_model_structured
from app.normalization import normalize_answer
from app.solvers.basic import try_basic_solver_structured
from app.types import SAFE_FALLBACK_ANSWER, AgentResult, TimingMetrics
from app.validators import validate_local_answer, validate_remote_answer


def answer_prompt(prompt: str) -> str:
    return answer_task("adhoc", prompt).answer


def answer_task(
    task_id: str,
    prompt: str,
    config: RuntimeConfig | None = None,
    deadline: DeadlineManager | None = None,
    local_model_allowed: bool = True,
) -> AgentResult:
    config = config or RuntimeConfig.from_env()
    timings = TimingMetrics()
    if deadline is not None:
        timings.batch_elapsed_ms_at_start = deadline.elapsed_ms()
    task_timer = StageTimer()

    prompt = prompt if isinstance(prompt, str) else str(prompt)
    prompt_char_count = len(prompt)
    prompt_token_estimate = estimate_tokens(prompt)

    classification_timer = StageTimer()
    classification = classify_prompt(prompt)
    timings.classification_elapsed_ms = classification_timer.elapsed_ms()

    local_timer = StageTimer()
    local_result = try_basic_solver_structured(prompt)
    timings.local_solver_elapsed_ms = local_timer.elapsed_ms()

    validation_timer = StageTimer()
    proof_elapsed_ms = timings.classification_elapsed_ms + timings.local_solver_elapsed_ms
    validation = validate_local_answer(
        prompt=prompt,
        classification=classification,
        solver_result=local_result,
        config=config,
        proof_elapsed_ms=proof_elapsed_ms,
    )
    timings.validation_elapsed_ms = validation_timer.elapsed_ms()
    timings.local_proof_elapsed_ms = proof_elapsed_ms + timings.validation_elapsed_ms

    if local_result is not None and validation.accepted:
        normalize_timer = StageTimer()
        answer = _normalize_for_classification(local_result.answer, prompt, classification)
        timings.normalization_elapsed_ms = normalize_timer.elapsed_ms()
        _finish_timings(timings, task_timer, deadline)
        return AgentResult(
            answer=answer,
            route="local",
            route_reason=local_result.solver_name,
            category=classification.category,
            router_mode=config.router_mode,
            prompt_char_count=prompt_char_count,
            prompt_token_estimate=prompt_token_estimate,
            deadline_decision=_deadline_decision(deadline, config),
            timings=timings,
            metadata={
                "answer_shape": classification.answer_shape,
                "constraints": list(classification.constraints),
                "classification_confidence": classification.confidence,
                "risk_score": classification.risk_score,
                "risk_components": classification.risk_components,
                "solver_confidence": local_result.confidence,
                "local_evidence": list(local_result.evidence),
                "local_proof_layers_passed": list(validation.passed_layers),
                "local_proof_layers_failed": list(validation.failed_layers),
                "validator_notes": list(validation.notes),
            },
        )

    remote_mode = _select_remote_mode(classification, local_result)
    prompt_policy = _prompt_policy_for_remote_mode(remote_mode, config, classification.category)
    remote_prompt = _apply_prompt_policy(prompt, prompt_policy)
    remote_prompt_token_estimate = estimate_tokens(remote_prompt)
    system_prompt = _system_prompt_for_remote_mode(remote_mode)
    remote_max_tokens = _max_tokens_for_category(config, classification.category)
    remote_config = _config_with_max_tokens(config, remote_max_tokens)

    local_model = None
    local_model_validation = None
    local_model_skip_reason = _local_model_skip_reason(config, deadline, classification, prompt, local_model_allowed)
    if local_model_skip_reason is None:
        local_model = ask_local_model_structured(
            remote_prompt,
            config=config,
            deadline=deadline,
            system_prompt=system_prompt,
            task_id=task_id,
            category=classification.category,
        )
        timings.local_model_elapsed_ms = local_model.elapsed_ms
        if local_model.error is None:
            raw_local_model_answer = local_model.answer if isinstance(local_model.answer, str) else str(local_model.answer)
            local_model_validation = validate_remote_answer(prompt, raw_local_model_answer, classification)
        if local_model.error is None and local_model_validation is not None and local_model_validation.accepted:
            normalize_timer = StageTimer()
            local_model_answer = _normalize_for_classification(local_model.answer, prompt, classification)
            timings.normalization_elapsed_ms += normalize_timer.elapsed_ms()
            local_model_validation = validate_remote_answer(prompt, local_model_answer, classification)
            if local_model_validation.accepted:
                _finish_timings(timings, task_timer, deadline)
                return AgentResult(
                    answer=local_model_answer,
                    route="local_model",
                    route_reason="local_model_validated",
                    category=classification.category,
                    router_mode=config.router_mode,
                    selected_model="local_model",
                    remote_mode=remote_mode,
                    prompt_policy=prompt_policy,
                    max_tokens=remote_max_tokens,
                    prompt_char_count=prompt_char_count,
                    prompt_token_estimate=prompt_token_estimate,
                    remote_prompt_token_estimate=remote_prompt_token_estimate,
                    completion_tokens=0,
                    total_tokens=0,
                    deadline_decision=_deadline_decision(deadline, config),
                    timings=timings,
                    metadata={
                        "answer_shape": classification.answer_shape,
                        "constraints": list(classification.constraints),
                        "classification_confidence": classification.confidence,
                        "risk_score": classification.risk_score,
                        "risk_components": classification.risk_components,
                        "solver_confidence": local_result.confidence if local_result is not None else None,
                        "local_evidence": list(local_result.evidence) if local_result is not None else [],
                        "local_proof_layers_passed": list(validation.passed_layers),
                        "local_proof_layers_failed": list(validation.failed_layers),
                        "validator_notes": list(validation.notes),
                        "local_model_validation_passed": list(local_model_validation.passed_layers),
                        "local_model_validation_failed": list(local_model_validation.failed_layers),
                        "local_model_validation_notes": list(local_model_validation.notes),
                        "local_model_path": local_model.model_path,
                        "local_model_runtime": local_model.runtime,
                        "local_model_prompt_tokens_estimate": local_model.prompt_tokens_estimate,
                        "local_model_output_tokens_estimate": local_model.output_tokens_estimate,
                        "final_answer_type": _answer_type(local_model_answer),
                    },
                )
    if deadline is not None and not deadline.can_spend(config.fireworks_timeout_seconds):
        _finish_timings(timings, task_timer, deadline)
        return AgentResult(
            answer=SAFE_FALLBACK_ANSWER,
            route="fallback",
            route_reason="deadline_suppressed_remote",
            category=classification.category,
            router_mode=config.router_mode,
            remote_mode=remote_mode,
            prompt_policy=prompt_policy,
            max_tokens=remote_max_tokens,
            prompt_char_count=prompt_char_count,
            prompt_token_estimate=prompt_token_estimate,
            remote_prompt_token_estimate=remote_prompt_token_estimate,
            deadline_decision=_deadline_decision(deadline, config),
            error="deadline_suppressed_remote",
            timings=timings,
            metadata={
                "answer_shape": classification.answer_shape,
                "constraints": list(classification.constraints),
                "classification_confidence": classification.confidence,
                "risk_score": classification.risk_score,
                "risk_components": classification.risk_components,
                "solver_confidence": local_result.confidence if local_result is not None else None,
                "local_evidence": list(local_result.evidence) if local_result is not None else [],
                "local_proof_layers_passed": list(validation.passed_layers),
                "local_proof_layers_failed": list(validation.failed_layers),
                "validator_notes": list(validation.notes),
                "local_model_error": local_model.error if local_model is not None else None,
                "local_model_skip_reason": local_model_skip_reason,
                "local_model_path": local_model.model_path if local_model is not None else None,
                "local_model_runtime": local_model.runtime if local_model is not None else None,
                "local_model_validation_failed": (
                    list(local_model_validation.failed_layers) if local_model_validation is not None else []
                ),
                "local_model_validation_notes": (
                    list(local_model_validation.notes) if local_model_validation is not None else []
                ),
            },
        )

    if config.local_model_enabled and not _fireworks_available(config):
        _finish_timings(timings, task_timer, deadline)
        return AgentResult(
            answer=SAFE_FALLBACK_ANSWER,
            route="fallback",
            route_reason="fireworks_unavailable_after_local_model",
            category=classification.category,
            router_mode=config.router_mode,
            remote_mode=remote_mode,
            prompt_policy=prompt_policy,
            max_tokens=remote_max_tokens,
            prompt_char_count=prompt_char_count,
            prompt_token_estimate=prompt_token_estimate,
            remote_prompt_token_estimate=remote_prompt_token_estimate,
            deadline_decision=_deadline_decision(deadline, config),
            error="fireworks_unavailable",
            timings=timings,
            metadata={
                "answer_shape": classification.answer_shape,
                "constraints": list(classification.constraints),
                "classification_confidence": classification.confidence,
                "risk_score": classification.risk_score,
                "risk_components": classification.risk_components,
                "solver_confidence": local_result.confidence if local_result is not None else None,
                "local_evidence": list(local_result.evidence) if local_result is not None else [],
                "local_proof_layers_passed": list(validation.passed_layers),
                "local_proof_layers_failed": list(validation.failed_layers),
                "validator_notes": list(validation.notes),
                "fireworks_called": False,
                "fireworks_http_status": None,
                "fireworks_error": "fireworks_unavailable",
                "local_model_attempted": local_model is not None,
                "local_model_skip_reason": local_model_skip_reason,
                "local_model_error": local_model.error if local_model is not None else None,
                "local_model_path": local_model.model_path if local_model is not None else None,
                "local_model_runtime": local_model.runtime if local_model is not None else None,
                "local_model_validation_failed": (
                    list(local_model_validation.failed_layers) if local_model_validation is not None else []
                ),
                "local_model_validation_notes": (
                    list(local_model_validation.notes) if local_model_validation is not None else []
                ),
                "final_answer_type": _answer_type(SAFE_FALLBACK_ANSWER),
            },
        )

    remote = ask_fireworks_structured(
        remote_prompt,
        config=remote_config,
        deadline=deadline,
        preferred_models=_preferred_models_for_remote_mode(remote_mode, config, classification.category),
        system_prompt=system_prompt,
    )
    timings.remote_elapsed_ms = remote.elapsed_ms
    normalize_timer = StageTimer()
    answer = _normalize_for_classification(remote.answer, prompt, classification)
    timings.normalization_elapsed_ms = normalize_timer.elapsed_ms()
    remote_validation = validate_remote_answer(prompt, answer, classification)
    escalation = None
    escalation_validation = None
    if _should_escalate_remote_answer(remote, remote_validation, config, deadline):
        escalation_prompt_policy = _escalation_prompt_policy(prompt_policy)
        escalation_prompt = _apply_prompt_policy(prompt, escalation_prompt_policy)
        escalation = ask_fireworks_structured(
            escalation_prompt,
            config=_config_with_max_tokens(config, _escalation_max_tokens(remote_max_tokens, classification.category)),
            deadline=deadline,
            preferred_models=_escalation_models(remote.model, config),
            system_prompt=_system_prompt_for_remote_mode(remote_mode),
        )
        timings.remote_elapsed_ms += escalation.elapsed_ms
        if escalation.error is None:
            escalation_answer = _normalize_for_classification(escalation.answer, prompt, classification)
            escalation_validation = validate_remote_answer(prompt, escalation_answer, classification)
            if escalation_validation.accepted:
                answer = escalation_answer
                remote = _merged_remote_result(remote, escalation)
                prompt_policy = escalation_prompt_policy
                remote_prompt_token_estimate = estimate_tokens(escalation_prompt)
                remote_validation = escalation_validation
    _finish_timings(timings, task_timer, deadline)

    return AgentResult(
        answer=answer,
        route="fireworks" if remote.error is None else "fallback",
        route_reason=_remote_route_reason(local_result, validation, remote.error, remote_validation),
        category=classification.category,
        router_mode=config.router_mode,
        selected_model=remote.model,
        remote_mode=remote_mode,
        prompt_policy=prompt_policy,
        max_tokens=remote_max_tokens,
        prompt_char_count=prompt_char_count,
        prompt_token_estimate=prompt_token_estimate,
        remote_prompt_token_estimate=remote_prompt_token_estimate,
        completion_tokens=remote.completion_tokens,
        total_tokens=remote.total_tokens,
        retry_count=remote.retry_count,
        deadline_decision=_deadline_decision(deadline, config),
        error=remote.error,
        timings=timings,
        metadata={
            "answer_shape": classification.answer_shape,
            "constraints": list(classification.constraints),
            "classification_confidence": classification.confidence,
            "risk_score": classification.risk_score,
            "risk_components": classification.risk_components,
            "solver_confidence": local_result.confidence if local_result is not None else None,
            "local_evidence": list(local_result.evidence) if local_result is not None else [],
            "local_proof_layers_passed": list(validation.passed_layers),
            "local_proof_layers_failed": list(validation.failed_layers),
            "validator_notes": list(validation.notes),
            "remote_validation_passed": list(remote_validation.passed_layers),
            "remote_validation_failed": list(remote_validation.failed_layers),
            "remote_validation_notes": list(remote_validation.notes),
            "fireworks_called": remote.model is not None,
            "fireworks_http_status": remote.http_status,
            "fireworks_error": remote.error,
            "remote_validation_escalation_enabled": config.remote_validation_escalation_enabled,
            "local_model_attempted": local_model is not None,
            "local_model_skip_reason": local_model_skip_reason,
            "local_model_error": local_model.error if local_model is not None else None,
            "local_model_path": local_model.model_path if local_model is not None else None,
            "local_model_runtime": local_model.runtime if local_model is not None else None,
            "local_model_prompt_tokens_estimate": local_model.prompt_tokens_estimate if local_model is not None else None,
            "local_model_output_tokens_estimate": local_model.output_tokens_estimate if local_model is not None else None,
            "local_model_validation_failed": (
                list(local_model_validation.failed_layers) if local_model_validation is not None else []
            ),
            "local_model_validation_notes": (
                list(local_model_validation.notes) if local_model_validation is not None else []
            ),
            "validation_result": "accepted" if remote_validation.accepted else "rejected",
            "remote_escalated_after_validation": escalation is not None,
            "remote_escalation_model": escalation.model if escalation is not None else None,
            "remote_escalation_error": escalation.error if escalation is not None else None,
            "remote_escalation_validation_failed": (
                list(escalation_validation.failed_layers) if escalation_validation is not None else []
            ),
            "final_answer_type": _answer_type(answer),
        },
    )


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _requests_code_only(prompt: str) -> bool:
    lower = prompt.lower()
    return "code only" in lower or "return only code" in lower or "return only corrected code" in lower


def _normalize_for_classification(answer, prompt: str, classification) -> str:
    constraints = set(classification.constraints)
    return normalize_answer(
        answer,
        code_only=(
            _requests_code_only(prompt)
            or "code_only" in constraints
            or classification.answer_shape in {"code", "corrected_code"}
            or "include_corrected_code" in constraints
        ),
        exact_numeric="exact_numeric" in constraints,
        answer_only="answer_only" in constraints,
        entity_labels="entity_labels" in constraints,
        allowed_labels=_allowed_labels_for_classification(classification),
    )


def _allowed_labels_for_classification(classification) -> tuple[str, ...] | None:
    if classification.category == "sentiment_classification":
        return ("positive", "negative", "neutral")
    return None


def _deadline_decision(deadline: DeadlineManager | None, config: RuntimeConfig) -> str | None:
    if deadline is None:
        return None
    return deadline.deadline_decision(config.fireworks_timeout_seconds)


def _finish_timings(timings: TimingMetrics, task_timer: StageTimer, deadline: DeadlineManager | None) -> None:
    timings.task_elapsed_ms = task_timer.elapsed_ms()
    if deadline is not None:
        timings.batch_elapsed_ms_at_finish = deadline.elapsed_ms()
        timings.remaining_budget_ms = deadline.remaining_budget_ms()


def _remote_route_reason(local_result, validation, remote_error: str | None, remote_validation=None) -> str:
    if remote_error is not None:
        return remote_error
    if remote_validation is not None and remote_validation.failed_layers:
        return "remote_validation_failed:" + ",".join(remote_validation.failed_layers)
    if local_result is None:
        return "no_local_solver"
    if validation.failed_layers:
        return "local_validation_failed:" + ",".join(validation.failed_layers)
    return "remote_selected"


def _select_remote_mode(classification, local_result=None) -> str:
    constraints = set(classification.constraints)
    if classification.category in {"code_generation", "code_debugging"}:
        return "remote_code"
    if classification.risk_components.get("reasoning_depth", 0) >= 0.5:
        return "remote_accuracy"
    if classification.risk_components.get("factual_freshness", 0) >= 0.5:
        return "remote_accuracy"
    if classification.risk_components.get("ambiguity", 0) >= 0.5:
        return "remote_accuracy"
    if classification.category == "logical_deductive_reasoning" and local_result is None:
        return "remote_accuracy"
    if classification.category == "factual_knowledge" and local_result is None:
        return "remote_accuracy"
    if constraints & {"code_only", "entity_labels", "exact_numeric"}:
        return "remote_format_strict"
    if classification.risk_components.get("format_strictness", 0) >= 0.45:
        return "remote_format_strict"
    return "remote_concise"


def _preferred_models_for_remote_mode(
    remote_mode: str,
    config: RuntimeConfig,
    category: str | None = None,
) -> tuple[str, ...]:
    if category and config.models_by_category and category in config.models_by_category:
        return config.models_by_category[category]
    if config.router_mode == "accuracy_first":
        return DEFAULT_ACCURACY_FIRST_MODELS
    if remote_mode == "remote_code":
        return config.models_remote_code
    if remote_mode == "remote_accuracy":
        return config.models_remote_accuracy
    if remote_mode == "remote_format_strict":
        return config.models_remote_format_strict
    return config.models_remote_concise


def _max_tokens_for_category(config: RuntimeConfig, category: str | None) -> int:
    if config.fireworks_disable_max_tokens:
        return config.fireworks_max_tokens
    if category and config.fireworks_max_tokens_by_category:
        return config.fireworks_max_tokens_by_category.get(category, config.fireworks_max_tokens)
    return config.fireworks_max_tokens


def _escalation_max_tokens(base_max_tokens: int, category: str | None) -> int:
    if category in {"code_generation", "code_debugging", "text_summarisation", "factual_knowledge"}:
        return max(base_max_tokens, 384)
    return base_max_tokens


def _config_with_max_tokens(config: RuntimeConfig, max_tokens: int) -> RuntimeConfig:
    if max_tokens == config.fireworks_max_tokens:
        return config
    return replace(config, fireworks_max_tokens=max_tokens)


def _should_escalate_remote_answer(remote, remote_validation, config: RuntimeConfig, deadline: DeadlineManager | None) -> bool:
    if not config.remote_validation_escalation_enabled:
        return False
    if remote.error is None and remote_validation.accepted:
        return False
    if not _escalation_models(remote.model, config):
        return False
    if deadline is not None and not deadline.should_retry(config.fireworks_timeout_seconds):
        return False
    return True


def _fireworks_available(config: RuntimeConfig) -> bool:
    return bool(config.fireworks_api_key and config.fireworks_base_url and config.allowed_models)


def _local_model_skip_reason(
    config: RuntimeConfig,
    deadline: DeadlineManager | None,
    classification,
    prompt: str,
    local_model_allowed: bool = True,
) -> str | None:
    if not local_model_allowed:
        return "local_model_batch_limit"
    if not config.local_model_enabled:
        return "local_model_disabled"
    if _local_model_path_for_category(config, classification.category) is None and not config.local_model_command:
        return "local_model_runtime_missing"
    if deadline is not None and not deadline.can_spend(config.local_model_timeout_seconds):
        return "deadline_suppressed_local_model"
    if len(prompt) > _local_model_max_prompt_chars(config):
        return "prompt_too_long_for_local_model"
    if classification.category not in _local_model_safe_categories(config):
        return "category_not_local_model_safe"
    if classification.risk_components.get("ambiguity", 0) >= 0.5 and classification.category not in {
        "sentiment_classification",
        "named_entity_recognition",
    }:
        return "ambiguous_task"
    if classification.risk_components.get("factual_freshness", 0) >= 0.5:
        return "fresh_factual_task"
    if classification.risk_components.get("reasoning_depth", 0) >= 0.75:
        return "deep_reasoning_task"
    if classification.category in {"code_generation", "code_debugging"} and not _code_task_is_local_model_eligible(
        prompt,
        classification,
    ):
        return "code_task_requires_fireworks"
    return None


def _local_model_safe_categories(config: RuntimeConfig) -> set[str]:
    if config.local_model_categories:
        return set(config.local_model_categories)
    safe = {
        "sentiment_classification",
        "named_entity_recognition",
        "mathematical_reasoning",
        "logical_deductive_reasoning",
    }
    if config.router_profile == "accuracy_gate":
        safe.update(
            {
                "factual_knowledge",
                "text_summarisation",
                "code_generation",
                "code_debugging",
            }
        )
    if config.router_profile == "token_competitive":
        safe.update({"factual_knowledge", "text_summarisation", "code_generation", "code_debugging"})
    return safe


def _local_model_path_for_category(config: RuntimeConfig, category: str | None):
    if category and config.local_model_paths_by_category:
        path = config.local_model_paths_by_category.get(category)
        if path is not None:
            return path
    return config.local_model_path


def _code_task_is_local_model_eligible(prompt: str, classification) -> bool:
    constraints = set(classification.constraints)
    if "code_only" in constraints:
        return True
    if classification.answer_shape in {"code", "corrected_code"}:
        return True
    lower = prompt.lower()
    code_markers = (
        "write code",
        "write python",
        "python function",
        "return code",
        "return only code",
        "corrected code",
        "debug this",
        "def ",
    )
    return any(marker in lower for marker in code_markers)


def _local_model_max_prompt_chars(config: RuntimeConfig) -> int:
    return 900 if config.router_profile == "accuracy_gate" else 1600


def _answer_type(answer: str) -> str:
    stripped = answer.strip()
    if not stripped:
        return "empty"
    if stripped.startswith("{") or stripped.startswith("["):
        return "json_like"
    if "\n" in stripped:
        return "multiline"
    if stripped.replace(".", "", 1).replace("-", "", 1).isdigit():
        return "numeric"
    return "text"


def _escalation_models(current_model: str | None, config: RuntimeConfig) -> tuple[str, ...]:
    models = config.models_remote_escalation or DEFAULT_ACCURACY_FIRST_MODELS
    return tuple(model for model in models if model != current_model)


def _escalation_prompt_policy(prompt_policy: str) -> str:
    if prompt_policy in {"compact", "original"}:
        return "answer_only"
    return prompt_policy


def _merged_remote_result(first, second):
    first_completion = first.completion_tokens if first.completion_tokens is not None else 0
    second_completion = second.completion_tokens if second.completion_tokens is not None else 0
    first_total = first.total_tokens if first.total_tokens is not None else 0
    second_total = second.total_tokens if second.total_tokens is not None else 0
    first.completion_tokens = first_completion + second_completion if first.completion_tokens is not None or second.completion_tokens is not None else None
    first.total_tokens = first_total + second_total if first.total_tokens is not None or second.total_tokens is not None else None
    first.retry_count += second.retry_count + 1
    first.model = second.model
    first.answer = second.answer
    first.elapsed_ms += second.elapsed_ms
    first.error = second.error
    return first


def _prompt_policy_for_remote_mode(remote_mode: str, config: RuntimeConfig, category: str | None = None) -> str:
    if category and config.prompt_policy_by_category and category in config.prompt_policy_by_category:
        return config.prompt_policy_by_category[category]
    if remote_mode == "remote_code":
        return config.prompt_policy_remote_code
    if remote_mode == "remote_format_strict":
        return config.prompt_policy_remote_format_strict
    if remote_mode == "remote_accuracy":
        return config.prompt_policy_remote_accuracy
    if remote_mode == "remote_concise":
        return config.prompt_policy_remote_concise
    return "original"


def _apply_prompt_policy(prompt: str, prompt_policy: str) -> str:
    if prompt_policy == "compact":
        return (
            "Answer accurately and concisely. Return only the final answer. Preserve every requested constraint. "
            "Do not restate the task, describe user intent, show analysis, or mention instructions.\n\n"
            "Task:\n" + prompt + "\n\nFinal answer:"
        )
    if prompt_policy == "answer_only":
        return (
            "Return only the final answer. Preserve the exact requested format. "
            "Do not restate the task, explain reasoning, describe user intent, mention instructions, or add markdown "
            "unless the task asks for it. Never begin with 'The user wants', 'I need to', or 'Let me'.\n\n"
            "Task:\n" + prompt + "\n\nFinal answer:"
        )
    if prompt_policy == "final_only":
        return (
            "You are being evaluated. Output exactly the final answer and nothing else.\n"
            "Forbidden: task restatement, analysis, hidden reasoning, plans, markdown fences, and phrases like "
            "'The user wants' or 'I need to'.\n"
            "If code is requested, output only valid code. If a label is requested, output the label first.\n\n"
            "Task:\n" + prompt + "\n\nFinal answer only:"
        )
    return prompt


def _system_prompt_for_remote_mode(remote_mode: str) -> str:
    base = (
        "You are an answer engine. Return only the final answer for the task. "
        "Do not restate the task. Do not describe the task, user intent, instructions, analysis, hidden reasoning, plans, or word counts. "
        "Never start with phrases like 'The user wants', 'I need to', 'Let me', or 'We need to'. "
    )
    if remote_mode == "remote_code":
        return (
            base
            + "For code tasks, return only complete valid Python code with a full function body. "
            "Do not include markdown fences or prose unless explicitly requested."
        )
    if remote_mode == "remote_format_strict":
        return (
            base
            + "Follow the requested output format exactly. For labels, output the label first. "
            "For no entities, output exactly None."
        )
    if remote_mode == "remote_accuracy":
        return (
            base
            + "Answer accurately in English. Reason internally, but output only the concise requested answer."
        )
    return base + "Answer accurately and concisely in English."
