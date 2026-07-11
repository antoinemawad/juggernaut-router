from dataclasses import replace

from app.classifier import classify_prompt
from app.config import RuntimeConfig
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
                "selected_route_before_generation": "local",
                "selected_model_before_generation": None,
                "generation_call_count": 0,
                "deterministic_solver_used": True,
                "normalization_applied": _normalization_name(prompt, classification),
                "validator_result": _validation_result(validation),
                "fireworks_called": False,
                "local_model_attempted": False,
                "final_answer_type": _answer_type(answer),
            },
        )

    remote_mode = _select_remote_mode(classification, local_result)
    prompt_policy = "original"
    generation_prompt = _apply_prompt_policy(prompt, prompt_policy)
    remote_prompt_token_estimate = estimate_tokens(generation_prompt)
    system_prompt = _system_prompt_for_remote_mode(remote_mode)
    remote_max_tokens = _max_tokens_for_category(config, classification.category)
    metadata_base = _base_metadata(classification, local_result, validation)

    local_model_skip_reason = _local_model_skip_reason(config, deadline, classification, prompt, local_model_allowed)
    if local_model_skip_reason is None:
        local_model = ask_local_model_structured(
            generation_prompt,
            config=config,
            deadline=deadline,
            system_prompt=system_prompt,
            task_id=task_id,
        )
        timings.local_model_elapsed_ms = local_model.elapsed_ms
        if local_model.error is not None:
            answer = SAFE_FALLBACK_ANSWER
            local_model_validation = None
            route = "fallback"
            route_reason = local_model.error
            error = local_model.error
        else:
            normalize_timer = StageTimer()
            answer = _normalize_for_classification(local_model.answer, prompt, classification)
            timings.normalization_elapsed_ms += normalize_timer.elapsed_ms()
            local_model_validation = validate_remote_answer(prompt, answer, classification)
            route = "local_model"
            route_reason = "local_model_generated"
            error = None
        _finish_timings(timings, task_timer, deadline)
        return AgentResult(
            answer=answer,
            route=route,
            route_reason=route_reason,
            category=classification.category,
            router_mode=config.router_mode,
            selected_model="local_model" if route == "local_model" else None,
            remote_mode=remote_mode,
            prompt_policy=prompt_policy,
            max_tokens=config.local_model_max_tokens,
            prompt_char_count=prompt_char_count,
            prompt_token_estimate=prompt_token_estimate,
            remote_prompt_token_estimate=remote_prompt_token_estimate,
            completion_tokens=0 if route == "local_model" else None,
            prompt_tokens=0 if route == "local_model" else None,
            total_tokens=0 if route == "local_model" else None,
            deadline_decision=_deadline_decision(deadline, config),
            error=error,
            timings=timings,
            metadata={
                **metadata_base,
                "selected_route_before_generation": "local_model",
                "generation_call_count": 1,
                "normalization_applied": _normalization_name(prompt, classification),
                "validator_result": _validation_result(local_model_validation),
                "local_model_attempted": True,
                "local_model_skip_reason": local_model_skip_reason,
                "local_model_error": local_model.error,
                "local_model_path": local_model.model_path,
                "local_model_runtime": local_model.runtime,
                "local_model_prompt_tokens_estimate": local_model.prompt_tokens_estimate,
                "local_model_output_tokens_estimate": local_model.output_tokens_estimate,
                "local_model_validation_passed": (
                    list(local_model_validation.passed_layers) if local_model_validation is not None else []
                ),
                "local_model_validation_failed": (
                    list(local_model_validation.failed_layers) if local_model_validation is not None else []
                ),
                "local_model_validation_notes": (
                    list(local_model_validation.notes) if local_model_validation is not None else []
                ),
                "fireworks_called": False,
                "final_answer_type": _answer_type(answer),
            },
        )

    selected_model = _select_single_fireworks_model(remote_mode, config, classification.category)
    if selected_model is None or not _fireworks_available(config):
        _finish_timings(timings, task_timer, deadline)
        return AgentResult(
            answer=SAFE_FALLBACK_ANSWER,
            route="fallback",
            route_reason="fireworks_unavailable",
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
                **metadata_base,
                "selected_route_before_generation": "fallback",
                "selected_model_before_generation": selected_model,
                "generation_call_count": 0,
                "normalization_applied": None,
                "validator_result": None,
                "fireworks_called": False,
                "fireworks_http_status": None,
                "fireworks_error": "fireworks_unavailable",
                "local_model_attempted": False,
                "local_model_skip_reason": local_model_skip_reason,
                "final_answer_type": _answer_type(SAFE_FALLBACK_ANSWER),
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
                **metadata_base,
                "selected_route_before_generation": "fallback",
                "selected_model_before_generation": selected_model,
                "generation_call_count": 0,
                "normalization_applied": None,
                "validator_result": None,
                "fireworks_called": False,
                "local_model_attempted": False,
                "local_model_skip_reason": local_model_skip_reason,
            },
        )

    single_model_config = _single_generation_config(config, selected_model, remote_max_tokens)
    remote = ask_fireworks_structured(
        generation_prompt,
        config=single_model_config,
        deadline=deadline,
        preferred_models=(selected_model,),
        system_prompt=system_prompt,
    )
    timings.remote_elapsed_ms = remote.elapsed_ms
    normalize_timer = StageTimer()
    answer = _normalize_for_classification(remote.answer, prompt, classification)
    timings.normalization_elapsed_ms = normalize_timer.elapsed_ms()
    remote_validation = validate_remote_answer(prompt, answer, classification)
    _finish_timings(timings, task_timer, deadline)

    return AgentResult(
        answer=answer,
        route="fireworks" if remote.error is None else "fallback",
        route_reason=_remote_route_reason(local_result, validation, remote.error, remote_validation),
        category=classification.category,
        router_mode=config.router_mode,
        selected_model=remote.model or selected_model,
        remote_mode=remote_mode,
        prompt_policy=prompt_policy,
        max_tokens=remote_max_tokens,
        prompt_char_count=prompt_char_count,
        prompt_token_estimate=prompt_token_estimate,
        remote_prompt_token_estimate=remote_prompt_token_estimate,
        prompt_tokens=remote.prompt_tokens,
        completion_tokens=remote.completion_tokens,
        total_tokens=remote.total_tokens,
        retry_count=remote.retry_count,
        deadline_decision=_deadline_decision(deadline, config),
        error=remote.error,
        timings=timings,
        metadata={
            **metadata_base,
            "selected_route_before_generation": "fireworks",
            "selected_model_before_generation": selected_model,
            "generation_call_count": 1 if remote.model is not None else 0,
            "normalization_applied": _normalization_name(prompt, classification),
            "validator_result": _validation_result(remote_validation),
            "remote_validation_passed": list(remote_validation.passed_layers),
            "remote_validation_failed": list(remote_validation.failed_layers),
            "remote_validation_notes": list(remote_validation.notes),
            "fireworks_called": remote.model is not None,
            "fireworks_http_status": remote.http_status,
            "fireworks_error": remote.error,
            "remote_validation_escalation_enabled": False,
            "local_model_attempted": False,
            "local_model_skip_reason": local_model_skip_reason,
            "validation_result": "accepted" if remote_validation.accepted else "rejected",
            "remote_escalated_after_validation": False,
            "remote_escalation_model": None,
            "remote_escalation_error": None,
            "remote_escalation_validation_failed": [],
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
        code_only=_requests_code_only(prompt) or "code_only" in constraints,
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
        return "remote_validation_observed:" + ",".join(remote_validation.failed_layers)
    if local_result is None:
        return "no_local_solver"
    if validation.failed_layers:
        return "local_validation_failed:" + ",".join(validation.failed_layers)
    return "remote_selected"


def _select_remote_mode(classification, local_result=None) -> str:
    if classification.category in {"code_generation", "code_debugging"}:
        return "remote_code"
    return "remote_accuracy"


def _select_single_fireworks_model(remote_mode: str, config: RuntimeConfig, category: str | None = None) -> str | None:
    allowed = set(config.allowed_models)
    preferred = "kimi-k2p7-code" if remote_mode == "remote_code" else "minimax-m3"
    if preferred in allowed:
        return preferred
    return config.first_allowed_model()


def _max_tokens_for_category(config: RuntimeConfig, category: str | None) -> int:
    if config.fireworks_disable_max_tokens:
        return config.fireworks_max_tokens
    if category and config.fireworks_max_tokens_by_category:
        return config.fireworks_max_tokens_by_category.get(category, config.fireworks_max_tokens)
    return config.fireworks_max_tokens


def _single_generation_config(config: RuntimeConfig, selected_model: str, max_tokens: int) -> RuntimeConfig:
    return replace(
        config,
        allowed_models=(selected_model,),
        fireworks_max_retries=0,
        fireworks_max_tokens=max_tokens,
    )


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
    if config.local_model_path is None and not config.local_model_command:
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
    return "Follow the user's instructions exactly. Return only the requested answer."


def _base_metadata(classification, local_result, validation) -> dict:
    return {
        "answer_shape": classification.answer_shape,
        "constraints": list(classification.constraints),
        "classification": {
            "category": classification.category,
            "answer_shape": classification.answer_shape,
            "constraints": list(classification.constraints),
            "confidence": classification.confidence,
            "risk_score": classification.risk_score,
            "risk_components": classification.risk_components,
        },
        "classification_confidence": classification.confidence,
        "risk_score": classification.risk_score,
        "risk_components": classification.risk_components,
        "deterministic_solver_used": local_result is not None and validation.accepted,
        "solver_confidence": local_result.confidence if local_result is not None else None,
        "local_evidence": list(local_result.evidence) if local_result is not None else [],
        "local_proof_layers_passed": list(validation.passed_layers),
        "local_proof_layers_failed": list(validation.failed_layers),
        "validator_notes": list(validation.notes),
    }


def _validation_result(validation) -> dict | None:
    if validation is None:
        return None
    return {
        "accepted": validation.accepted,
        "passed": list(validation.passed_layers),
        "failed": list(validation.failed_layers),
        "notes": list(validation.notes),
    }


def _normalization_name(prompt: str, classification) -> str:
    constraints = set(classification.constraints)
    applied = []
    if _requests_code_only(prompt) or "code_only" in constraints:
        applied.append("code_only")
    if "exact_numeric" in constraints:
        applied.append("exact_numeric")
    if "answer_only" in constraints:
        applied.append("answer_only")
    if "entity_labels" in constraints:
        applied.append("entity_labels")
    if _allowed_labels_for_classification(classification):
        applied.append("allowed_label")
    return ",".join(applied) if applied else "trim"
