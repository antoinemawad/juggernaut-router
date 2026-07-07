import ast
import re

from app.types import SAFE_FALLBACK_ANSWER


def normalize_answer(answer, code_only: bool = False) -> str:
    if answer is None:
        return SAFE_FALLBACK_ANSWER

    if not isinstance(answer, str):
        answer = str(answer)

    normalized = answer.strip()
    if code_only:
        normalized = _extract_code_only(normalized).strip()

    if not normalized:
        return SAFE_FALLBACK_ANSWER

    return normalized


def _extract_code_only(text: str) -> str:
    fenced = _first_fenced_code_block(text)
    if fenced is not None:
        return fenced

    for marker in ("def ", "class ", "import ", "from "):
        index = text.find(marker)
        if index >= 0:
            return _trim_to_valid_python_prefix(text[index:].strip())

    return _strip_code_fence(text)


def _first_fenced_code_block(text: str) -> str | None:
    match = re.search(r"```(?:[A-Za-z0-9_+.-]+)?\s*\n(.*?)```", text, flags=re.DOTALL)
    if match is None:
        return None
    return match.group(1).strip()


def _trim_to_valid_python_prefix(text: str) -> str:
    lines = text.splitlines()
    for end in range(len(lines), 0, -1):
        candidate = "\n".join(lines[:end]).strip()
        if _python_syntax_valid(candidate):
            return candidate
    return text


def _python_syntax_valid(code: str) -> bool:
    try:
        ast.parse(code)
    except SyntaxError:
        return False
    return True


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return text
