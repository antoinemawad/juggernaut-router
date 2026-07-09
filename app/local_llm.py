from dataclasses import dataclass
from pathlib import Path

from app.deadline import StageTimer


@dataclass
class LocalLLMResult:
    text: str
    success: bool
    latency_ms: int
    error: str | None
    model_path: str | None
    prompt_tokens_estimate: int
    output_tokens_estimate: int


_LLM_CACHE = {}


def generate_local_answer(
    task: str,
    prompt: str,
    model_path: str | Path | None,
    max_tokens: int,
    temperature: float,
    context: int,
    threads: int,
    timeout_seconds: int,
) -> LocalLLMResult:
    timer = StageTimer()
    path = Path(model_path) if model_path else None
    prompt_tokens = _rough_token_estimate(prompt)

    if path is None:
        return _result("", False, timer, "missing_local_model_path", None, prompt_tokens)
    if not path.exists():
        return _result("", False, timer, "local_model_path_missing", str(path), prompt_tokens)

    try:
        from llama_cpp import Llama
    except Exception as exc:  # pragma: no cover - optional dependency in the default image
        return _result("", False, timer, f"llama_cpp_import_error:{type(exc).__name__}", str(path), prompt_tokens)

    try:
        llm = _load_model(path, context=context, threads=threads)
        output = llm(
            _format_prompt(task, prompt),
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["</s>", "\n\nTask:", "\n\nUser:"],
            echo=False,
        )
    except TimeoutError:
        return _result("", False, timer, "local_llm_timeout", str(path), prompt_tokens)
    except Exception as exc:  # pragma: no cover - depends on optional runtime/model
        return _result("", False, timer, f"local_llm_error:{type(exc).__name__}", str(path), prompt_tokens)

    text = _extract_text(output)
    if not text:
        return _result("", False, timer, "local_llm_empty", str(path), prompt_tokens)
    return _result(text, True, timer, None, str(path), prompt_tokens)


def _load_model(path: Path, context: int, threads: int):
    key = (str(path), context, threads)
    if key in _LLM_CACHE:
        return _LLM_CACHE[key]

    from llama_cpp import Llama

    llm = Llama(
        model_path=str(path),
        n_ctx=context,
        n_threads=threads,
        n_gpu_layers=0,
        verbose=False,
    )
    _LLM_CACHE[key] = llm
    return llm


def _format_prompt(task: str, prompt: str) -> str:
    return (
        "You are a concise answer engine. Return only the final answer. "
        "Do not restate the task, reveal reasoning, or add markdown unless requested.\n\n"
        f"Task id: {task}\n"
        f"User task:\n{prompt}\n\n"
        "Final answer:"
    )


def _extract_text(output) -> str:
    try:
        choices = output.get("choices", [])
        if choices:
            return str(choices[0].get("text", "")).strip()
    except AttributeError:
        return ""
    return ""


def _result(
    text: str,
    success: bool,
    timer: StageTimer,
    error: str | None,
    model_path: str | None,
    prompt_tokens: int,
) -> LocalLLMResult:
    return LocalLLMResult(
        text=text,
        success=success,
        latency_ms=timer.elapsed_ms(),
        error=error,
        model_path=model_path,
        prompt_tokens_estimate=prompt_tokens,
        output_tokens_estimate=_rough_token_estimate(text) if text else 0,
    )


def _rough_token_estimate(text: str) -> int:
    return max(1, (len(text) + 3) // 4) if text else 0
