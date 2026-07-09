from dataclasses import dataclass, field
from typing import Any


SAFE_FALLBACK_ANSWER = "Unable to answer safely."


@dataclass
class TimingMetrics:
    task_elapsed_ms: int = 0
    classification_elapsed_ms: int = 0
    constraint_extraction_elapsed_ms: int = 0
    local_solver_elapsed_ms: int = 0
    validation_elapsed_ms: int = 0
    local_proof_elapsed_ms: int = 0
    local_model_elapsed_ms: int = 0
    trap_guard_elapsed_ms: int = 0
    cross_check_elapsed_ms: int = 0
    remote_elapsed_ms: int = 0
    normalization_elapsed_ms: int = 0
    batch_elapsed_ms_at_start: int = 0
    batch_elapsed_ms_at_finish: int = 0
    remaining_budget_ms: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "task_elapsed_ms": self.task_elapsed_ms,
            "classification_elapsed_ms": self.classification_elapsed_ms,
            "constraint_extraction_elapsed_ms": self.constraint_extraction_elapsed_ms,
            "local_solver_elapsed_ms": self.local_solver_elapsed_ms,
            "validation_elapsed_ms": self.validation_elapsed_ms,
            "local_proof_elapsed_ms": self.local_proof_elapsed_ms,
            "local_model_elapsed_ms": self.local_model_elapsed_ms,
            "trap_guard_elapsed_ms": self.trap_guard_elapsed_ms,
            "cross_check_elapsed_ms": self.cross_check_elapsed_ms,
            "remote_elapsed_ms": self.remote_elapsed_ms,
            "normalization_elapsed_ms": self.normalization_elapsed_ms,
            "batch_elapsed_ms_at_start": self.batch_elapsed_ms_at_start,
            "batch_elapsed_ms_at_finish": self.batch_elapsed_ms_at_finish,
            "remaining_budget_ms": self.remaining_budget_ms,
        }


@dataclass
class AgentResult:
    answer: str
    route: str
    route_reason: str
    category: str = "unknown"
    router_mode: str = "conservative"
    selected_model: str | None = None
    remote_mode: str | None = None
    prompt_policy: str = "original"
    max_tokens: int | None = None
    prompt_char_count: int = 0
    prompt_token_estimate: int = 0
    remote_prompt_token_estimate: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    retry_count: int = 0
    deadline_decision: str | None = None
    error: str | None = None
    timings: TimingMetrics = field(default_factory=TimingMetrics)
    metadata: dict[str, Any] = field(default_factory=dict)

    def telemetry_record(self, task_id: str) -> dict[str, Any]:
        record: dict[str, Any] = {
            "task_id": task_id,
            "category": self.category,
            "route": self.route,
            "route_reason": self.route_reason,
            "router_mode": self.router_mode,
            "selected_model": self.selected_model,
            "remote_mode": self.remote_mode,
            "prompt_policy": self.prompt_policy,
            "max_tokens": self.max_tokens,
            "prompt_char_count": self.prompt_char_count,
            "prompt_token_estimate": self.prompt_token_estimate,
            "remote_prompt_token_estimate": self.remote_prompt_token_estimate,
            "answer_char_count": len(self.answer),
            "answer_token_estimate": _rough_token_estimate(self.answer),
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "retry_count": self.retry_count,
            "deadline_decision": self.deadline_decision,
            "error": self.error,
        }
        record.update(self.timings.as_dict())
        record.update(self.metadata)
        return record


def _rough_token_estimate(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
