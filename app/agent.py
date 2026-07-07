from app.classifier import classify_prompt
from app.config import RuntimeConfig
from app.deadline import DeadlineManager, StageTimer
from app.fireworks_client import ask_fireworks_structured
from app.normalization import normalize_answer
from app.solvers.basic import try_basic_solver_structured
from app.types import AgentResult, TimingMetrics
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
        answer = normalize_answer(local_result.answer, code_only=_requests_code_only(prompt))
        timings.normalization_elapsed_ms = normalize_timer.elapsed_ms()
        _finish_timings(timings, task_timer, deadline)
        return AgentResult(
            answer=answer,
            route="local",
            route_reason=local_result.solver_name,
            category=classification.category,
            router_mode=config.router_mode,
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
    remote = ask_fireworks_structured(prompt, config=config, deadline=deadline)
    timings.remote_elapsed_ms = remote.elapsed_ms
    normalize_timer = StageTimer()
    answer = normalize_answer(remote.answer, code_only=_requests_code_only(prompt))
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
        max_tokens=config.fireworks_max_tokens,
        prompt_token_estimate=prompt_token_estimate,
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
