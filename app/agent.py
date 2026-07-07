from app.config import RuntimeConfig
from app.deadline import DeadlineManager, StageTimer
from app.fireworks_client import ask_fireworks_structured
from app.normalization import normalize_answer
from app.solvers.basic import try_basic_solver
from app.types import AgentResult, TimingMetrics


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

    local_timer = StageTimer()
    local_answer = try_basic_solver(prompt)
    timings.local_solver_elapsed_ms = local_timer.elapsed_ms()
    timings.local_proof_elapsed_ms = timings.local_solver_elapsed_ms

    if local_answer is not None:
        normalize_timer = StageTimer()
        answer = normalize_answer(local_answer, code_only=_requests_code_only(prompt))
        timings.normalization_elapsed_ms = normalize_timer.elapsed_ms()
        _finish_timings(timings, task_timer, deadline)
        return AgentResult(
            answer=answer,
            route="local",
            route_reason="basic_solver",
            router_mode=config.router_mode,
            prompt_token_estimate=prompt_token_estimate,
            deadline_decision=_deadline_decision(deadline, config),
            timings=timings,
            metadata={
                "local_proof_layers_passed": ["local_solver", "normalization"],
                "local_proof_layers_failed": [],
            },
        )

    remote = ask_fireworks_structured(prompt, config=config, deadline=deadline)
    timings.remote_elapsed_ms = remote.elapsed_ms
    normalize_timer = StageTimer()
    answer = normalize_answer(remote.answer, code_only=_requests_code_only(prompt))
    timings.normalization_elapsed_ms = normalize_timer.elapsed_ms()
    _finish_timings(timings, task_timer, deadline)

    return AgentResult(
        answer=answer,
        route="fireworks" if remote.error is None else "fallback",
        route_reason="no_local_solver" if remote.error is None else remote.error,
        router_mode=config.router_mode,
        selected_model=remote.model,
        remote_mode="remote_concise",
        max_tokens=config.fireworks_max_tokens,
        prompt_token_estimate=prompt_token_estimate,
        completion_tokens=remote.completion_tokens,
        total_tokens=remote.total_tokens,
        retry_count=remote.retry_count,
        deadline_decision=_deadline_decision(deadline, config),
        error=remote.error,
        timings=timings,
        metadata={
            "local_proof_layers_passed": [],
            "local_proof_layers_failed": ["local_solver"],
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
