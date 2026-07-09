import shlex
import subprocess
from dataclasses import dataclass

from app.config import RuntimeConfig
from app.deadline import DeadlineManager, StageTimer
from app.local_llm import generate_local_answer
from app.types import SAFE_FALLBACK_ANSWER


@dataclass
class LocalModelResult:
    answer: str
    elapsed_ms: int = 0
    error: str | None = None
    model_path: str | None = None
    prompt_tokens_estimate: int | None = None
    output_tokens_estimate: int | None = None
    runtime: str | None = None


def ask_local_model_structured(
    prompt: str,
    config: RuntimeConfig | None = None,
    deadline: DeadlineManager | None = None,
    system_prompt: str | None = None,
    task_id: str = "task",
) -> LocalModelResult:
    config = config or RuntimeConfig.from_env()
    timer = StageTimer()

    if not config.local_model_enabled:
        return LocalModelResult(SAFE_FALLBACK_ANSWER, elapsed_ms=timer.elapsed_ms(), error="local_model_disabled")
    if config.local_model_path is not None:
        if deadline is not None and not deadline.can_spend(config.local_model_timeout_seconds):
            return LocalModelResult(
                SAFE_FALLBACK_ANSWER,
                elapsed_ms=timer.elapsed_ms(),
                error="deadline_suppressed_local_model",
                model_path=str(config.local_model_path),
                runtime="llama_cpp",
            )
        result = generate_local_answer(
            task=task_id,
            prompt=_local_model_input(prompt, system_prompt),
            model_path=config.local_model_path,
            max_tokens=config.local_model_max_tokens,
            temperature=config.local_model_temperature,
            context=config.local_model_context,
            threads=config.local_model_threads,
            timeout_seconds=config.local_model_timeout_seconds,
        )
        return LocalModelResult(
            result.text if result.success else SAFE_FALLBACK_ANSWER,
            elapsed_ms=result.latency_ms,
            error=result.error,
            model_path=result.model_path,
            prompt_tokens_estimate=result.prompt_tokens_estimate,
            output_tokens_estimate=result.output_tokens_estimate,
            runtime="llama_cpp",
        )
    if not config.local_model_command:
        return LocalModelResult(SAFE_FALLBACK_ANSWER, elapsed_ms=timer.elapsed_ms(), error="missing_local_model_command")
    if deadline is not None and not deadline.can_spend(config.local_model_timeout_seconds):
        return LocalModelResult(
            SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error="deadline_suppressed_local_model",
            runtime="command",
        )

    try:
        args = shlex.split(config.local_model_command)
    except ValueError as exc:
        return LocalModelResult(
            SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error=f"local_model_command_error:{type(exc).__name__}",
            runtime="command",
        )
    if not args:
        return LocalModelResult(
            SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error="missing_local_model_command",
            runtime="command",
        )

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
        return LocalModelResult(
            SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error="local_model_timeout",
            runtime="command",
        )
    except OSError as exc:
        return LocalModelResult(
            SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error=f"local_model_exec_error:{type(exc).__name__}",
            runtime="command",
        )

    if completed.returncode != 0:
        return LocalModelResult(
            SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error=f"local_model_exit_{completed.returncode}",
            runtime="command",
        )

    answer = completed.stdout.strip()
    if not answer:
        return LocalModelResult(
            SAFE_FALLBACK_ANSWER,
            elapsed_ms=timer.elapsed_ms(),
            error="local_model_empty",
            runtime="command",
        )
    return LocalModelResult(answer[: config.local_model_max_chars], elapsed_ms=timer.elapsed_ms(), runtime="command")


def _local_model_input(prompt: str, system_prompt: str | None) -> str:
    if system_prompt:
        return f"System:\n{system_prompt}\n\nUser:\n{prompt}\n\nAnswer:\n"
    return prompt
