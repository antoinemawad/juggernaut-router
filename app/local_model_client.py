import shlex
import subprocess
from dataclasses import dataclass

from app.config import RuntimeConfig
from app.deadline import DeadlineManager, StageTimer
from app.types import SAFE_FALLBACK_ANSWER


@dataclass
class LocalModelResult:
    answer: str
    elapsed_ms: int = 0
    error: str | None = None


def ask_local_model_structured(
    prompt: str,
    config: RuntimeConfig | None = None,
    deadline: DeadlineManager | None = None,
    system_prompt: str | None = None,
) -> LocalModelResult:
    config = config or RuntimeConfig.from_env()
    timer = StageTimer()

    if not config.local_model_enabled:
        return LocalModelResult(SAFE_FALLBACK_ANSWER, elapsed_ms=timer.elapsed_ms(), error="local_model_disabled")
    if not config.local_model_command:
        return LocalModelResult(SAFE_FALLBACK_ANSWER, elapsed_ms=timer.elapsed_ms(), error="missing_local_model_command")
    if deadline is not None and not deadline.can_spend(config.local_model_timeout_seconds):
        return LocalModelResult(SAFE_FALLBACK_ANSWER, elapsed_ms=timer.elapsed_ms(), error="deadline_suppressed_local_model")

    try:
        args = shlex.split(config.local_model_command)
    except ValueError as exc:
        return LocalModelResult(
            SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error=f"local_model_command_error:{type(exc).__name__}",
        )
    if not args:
        return LocalModelResult(SAFE_FALLBACK_ANSWER, elapsed_ms=timer.elapsed_ms(), error="missing_local_model_command")

    try:
        completed = subprocess.run(
            args,
            input=_local_model_input(prompt, system_prompt),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=config.local_model_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return LocalModelResult(SAFE_FALLBACK_ANSWER, elapsed_ms=timer.elapsed_ms(), error="local_model_timeout")
    except OSError as exc:
        return LocalModelResult(
            SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error=f"local_model_exec_error:{type(exc).__name__}",
        )

    if completed.returncode != 0:
        return LocalModelResult(
            SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error=f"local_model_exit_{completed.returncode}",
        )

    answer = completed.stdout.strip()
    if not answer:
        return LocalModelResult(SAFE_FALLBACK_ANSWER, elapsed_ms=timer.elapsed_ms(), error="local_model_empty")
    return LocalModelResult(answer[: config.local_model_max_chars], elapsed_ms=timer.elapsed_ms())


def _local_model_input(prompt: str, system_prompt: str | None) -> str:
    if system_prompt:
        return f"System:\n{system_prompt}\n\nUser:\n{prompt}\n\nAnswer:\n"
    return prompt
