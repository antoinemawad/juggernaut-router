import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable


Clock = Callable[[], float]


@dataclass
class DeadlineManager:
    total_seconds: int = 600
    safety_margin_seconds: int = 60
    clock: Clock = time.monotonic
    started_at: float = field(init=False)
    started_at_iso: str = field(init=False)

    def __post_init__(self) -> None:
        self.started_at = self.clock()
        self.started_at_iso = datetime.now(timezone.utc).isoformat()

    def elapsed_seconds(self) -> float:
        return max(0.0, self.clock() - self.started_at)

    def elapsed_ms(self) -> int:
        return int(self.elapsed_seconds() * 1000)

    def remaining_seconds(self) -> float:
        return max(0.0, self.total_seconds - self.elapsed_seconds())

    def remaining_budget_seconds(self) -> float:
        return max(0.0, self.remaining_seconds() - self.safety_margin_seconds)

    def remaining_budget_ms(self) -> int:
        return int(self.remaining_budget_seconds() * 1000)

    def can_spend(self, seconds: float) -> bool:
        return self.remaining_budget_seconds() >= seconds

    def should_retry(self, timeout_seconds: int) -> bool:
        return self.can_spend(timeout_seconds + 1)

    def deadline_decision(self, timeout_seconds: int) -> str:
        if self.should_retry(timeout_seconds):
            return "deadline_allows_remote"
        return "deadline_suppressed_remote_or_retry"


class StageTimer:
    def __init__(self, clock: Clock = time.monotonic) -> None:
        self.clock = clock
        self.started_at = clock()

    def elapsed_ms(self) -> int:
        return int(max(0.0, self.clock() - self.started_at) * 1000)
