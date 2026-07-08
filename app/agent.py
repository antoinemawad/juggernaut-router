from app.classifier import classify_prompt
from app.config import RuntimeConfig
from app.deadline import DeadlineManager, StageTimer
from app.fireworks_client import ask_fireworks_structured
from app.normalization import normalize_answer
from app.solvers.basic import try_basic_solver_structured
from app.types import SAFE_FALLBACK_ANSWER, AgentResult, TimingMetrics
from app.validators import validate_local_answer


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
    prompt_policy = _prompt_policy_for_remote_mode(remote_mode, config)
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
    _finish_timings(timings, task_timer, deadline)

    return AgentResult(
        answer=answer,
        route="fireworks" if remote.error is None else "fallback",
        route_reason=_remote_route_reason(local_result, validation, remote.error),
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


def _remote_route_reason(local_result, validation, remote_error: str | None) -> str:
    if remote_error is not None:
        return remote_error
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


def _prompt_policy_for_remote_mode(remote_mode: str, config: RuntimeConfig) -> str:
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
