from app.classifier import classify_prompt
from app.config import RuntimeConfig
from app.deadline import DeadlineManager, StageTimer
from app.fireworks_client import ask_fireworks_structured
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
            max_tokens=config.fireworks_max_tokens,
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
            },
        )

    remote = ask_fireworks_structured(
        remote_prompt,
        config=config,
        deadline=deadline,
        preferred_models=_preferred_models_for_remote_mode(remote_mode, config),
        system_prompt=_system_prompt_for_remote_mode(remote_mode),
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
            config=config,
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
        max_tokens=config.fireworks_max_tokens,
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
            "remote_validation_escalation_enabled": config.remote_validation_escalation_enabled,
            "remote_escalated_after_validation": escalation is not None,
            "remote_escalation_model": escalation.model if escalation is not None else None,
            "remote_escalation_error": escalation.error if escalation is not None else None,
            "remote_escalation_validation_failed": (
                list(escalation_validation.failed_layers) if escalation_validation is not None else []
            ),
        },
    )


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _requests_code_only(prompt: str) -> bool:
    lower = prompt.lower()
    return "code only" in lower or "return only code" in lower


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
    if classification.category == "factual_knowledge" and local_result is None:
        return "remote_accuracy"
    if constraints & {"code_only", "entity_labels", "exact_numeric"}:
        return "remote_format_strict"
    if classification.risk_components.get("format_strictness", 0) >= 0.45:
        return "remote_format_strict"
    return "remote_concise"


def _preferred_models_for_remote_mode(remote_mode: str, config: RuntimeConfig) -> tuple[str, ...]:
    if remote_mode == "remote_code":
        return config.models_remote_code
    if remote_mode == "remote_accuracy":
        return config.models_remote_accuracy
    if remote_mode == "remote_format_strict":
        return config.models_remote_format_strict
    return config.models_remote_concise


def _should_escalate_remote_answer(remote, remote_validation, config: RuntimeConfig, deadline: DeadlineManager | None) -> bool:
    if not config.remote_validation_escalation_enabled:
        return False
    if remote.error is not None or remote_validation.accepted:
        return False
    if not _escalation_models(remote.model, config):
        return False
    if deadline is not None and not deadline.should_retry(config.fireworks_timeout_seconds):
        return False
    return True


def _escalation_models(current_model: str | None, config: RuntimeConfig) -> tuple[str, ...]:
    return tuple(model for model in config.models_remote_escalation if model != current_model)


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
            "Answer accurately and concisely. Preserve every requested constraint. "
            "Do not restate the task.\n\nTask:\n" + prompt
        )
    if prompt_policy == "answer_only":
        return (
            "Return only the final answer. Preserve the exact requested format. "
            "Do not restate the task, explain reasoning, mention instructions, or add markdown unless the task asks for it.\n\n"
            "Task:\n" + prompt
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
    if remote_mode == "remote_code":
        return (
            "Return the corrected or requested code only when code-only is requested. "
            "Do not include analysis, markdown fences, prose, or task restatement unless the user explicitly asks for them."
        )
    if remote_mode == "remote_format_strict":
        return (
            "Follow the requested output format exactly. Return only the answer. "
            "Do not restate the task, explain reasoning, or mention instructions unless requested."
        )
    if remote_mode == "remote_accuracy":
        return (
            "Answer accurately in English. Reason internally, but return only the concise final answer "
            "in the requested format."
        )
    return "Answer accurately and concisely in English. Do not restate the task."
