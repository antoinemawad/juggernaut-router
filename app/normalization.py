from app.types import SAFE_FALLBACK_ANSWER


def normalize_answer(answer, code_only: bool = False) -> str:
    if answer is None:
        return SAFE_FALLBACK_ANSWER

    if not isinstance(answer, str):
        answer = str(answer)

    normalized = answer.strip()
    if code_only:
        normalized = _strip_code_fence(normalized).strip()

    if not normalized:
        return SAFE_FALLBACK_ANSWER

    return normalized


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return text
