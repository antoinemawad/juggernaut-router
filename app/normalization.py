import ast
import re

from app.types import SAFE_FALLBACK_ANSWER


def normalize_answer(
    answer,
    code_only: bool = False,
    exact_numeric: bool = False,
    answer_only: bool = False,
    entity_labels: bool = False,
    allowed_labels: tuple[str, ...] | list[str] | None = None,
) -> str:
    if answer is None:
        return SAFE_FALLBACK_ANSWER

    if not isinstance(answer, str):
        answer = str(answer)

    normalized = answer.strip()
    if code_only:
        normalized = _extract_code_only(normalized).strip()
    elif entity_labels:
        normalized = _normalize_entity_labels(normalized)
    elif allowed_labels:
        normalized = _extract_allowed_label(normalized, allowed_labels)
    elif exact_numeric:
        normalized = _extract_exact_numeric(normalized)
    elif answer_only:
        normalized = _extract_answer_only(normalized)

    if not normalized:
        return SAFE_FALLBACK_ANSWER

    return normalized


def _normalize_entity_labels(text: str) -> str:
    labels = ("PERSON", "ORG", "LOCATION", "DATE")
    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        line = re.sub(r"^[-*•]\s*", "", line).strip()
        if not line or line.lower().rstrip(":") in {"entities", "named entities", "answer"}:
            continue
        if any(re.search(rf"\b{label}\b", line) for label in labels) and ":" in line:
            cleaned_lines.append(line.rstrip(";,"))

    if cleaned_lines:
        return "\n".join(cleaned_lines)

    paren_matches = re.findall(r"([A-Z][A-Za-z0-9 .&-]+?)\s*\((PERSON|ORG|LOCATION|DATE)\)", text)
    if paren_matches:
        return "\n".join(f"{entity.strip()}: {label}" for entity, label in paren_matches)

    return _extract_answer_only(text)


def _extract_allowed_label(text: str, allowed_labels: tuple[str, ...] | list[str]) -> str:
    lowered = text.lower()
    matches = []
    for label in allowed_labels:
        if re.search(rf"\b{re.escape(label.lower())}\b", lowered):
            matches.append(label)
    if len(matches) == 1:
        return matches[0]
    return _extract_answer_only(text)


def _extract_exact_numeric(text: str) -> str:
    stripped = text.strip()
    marker_answer = _answer_after_final_marker(stripped)
    if marker_answer != stripped:
        marker_numeric = _extract_exact_numeric(marker_answer)
        if marker_numeric:
            return marker_numeric

    final_sentence = _sentence_with_final_numeric(stripped)
    if final_sentence is not None and final_sentence != stripped:
        final_numeric = _extract_exact_numeric(final_sentence)
        if final_numeric and final_numeric != final_sentence:
            return final_numeric

    candidates = _numeric_candidates(stripped)
    if len(candidates) == 1:
        candidate = candidates[0]
        unit_match = re.match(rf"^\s*{re.escape(candidate)}\s+[A-Za-z%][A-Za-z0-9/%.-]*\s*$", stripped)
        if unit_match:
            return stripped
        return candidate

    if len(candidates) > 1:
        return stripped

    return _extract_answer_only(stripped)


def _extract_answer_only(text: str) -> str:
    stripped = text.strip()
    for pattern in (
        r"^\s*final\s+answer\s*:\s*",
        r"^\s*answer\s*:\s*",
        r"^\s*result\s*:\s*",
        r"^\s*the\s+answer\s+is\s*:?\s*",
    ):
        cleaned = re.sub(pattern, "", stripped, count=1, flags=re.IGNORECASE)
        if cleaned != stripped:
            return cleaned.strip()
    return stripped


def _answer_after_final_marker(text: str) -> str:
    marker = re.search(
        r"(?:final\s+answer|answer|result|the\s+answer\s+is)\s*:?\s*(.+)\s*$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return marker.group(1).strip() if marker else text


def _sentence_with_final_numeric(text: str) -> str | None:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        if re.search(r"\b(final|result|answer|therefore|total)\b", sentence, flags=re.IGNORECASE) and _numeric_candidates(sentence):
            return sentence.strip()
    return None


def _numeric_candidates(text: str) -> list[str]:
    pattern = re.compile(
        r"""
        (?<![\w])
        (?:
            [-+]?\$\s*\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?
            |
            \$\s*[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?
            |
            [-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?\s*%
            |
            [-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?
        )
        (?![\w])
        """,
        flags=re.VERBOSE,
    )
    return [match.group(0).replace("$ ", "$").replace(" %", "%").strip() for match in pattern.finditer(text)]


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
