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
        normalized = _strip_meta_preamble(normalized)
        normalized = _normalize_entity_labels(normalized)
    elif allowed_labels:
        normalized = _strip_meta_preamble(normalized)
        normalized = _extract_allowed_label(normalized, allowed_labels)
    elif exact_numeric:
        normalized = _strip_meta_preamble(normalized)
        normalized = _extract_exact_numeric(normalized)
    elif answer_only:
        normalized = _strip_meta_preamble(normalized)
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
    marker_answer = _after_explicit_answer_marker(text)
    search_text = marker_answer or text
    explicit_pattern = "|".join(re.escape(label) for label in allowed_labels)

    for line in [line.strip() for line in search_text.splitlines() if line.strip()]:
        match = re.match(
            rf"^(?:sentiment|label|answer|final answer)?\s*:?\s*({explicit_pattern})\b",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            return _canonical_label(match.group(1), allowed_labels)

    explicit_match = re.search(
        rf"\b(?:sentiment|label|answer|final answer)\s*(?:is|:)\s*({explicit_pattern})\b",
        search_text,
        flags=re.IGNORECASE,
    )
    if explicit_match:
        return _canonical_label(explicit_match.group(1), allowed_labels)

    lowered = search_text.lower()
    matches = []
    for label in allowed_labels:
        if re.search(rf"\b{re.escape(label.lower())}\b", lowered):
            matches.append(label)
    if len(matches) == 1:
        return matches[0]
    return _extract_answer_only(text)


def _extract_exact_numeric(text: str) -> str:
    search_text = _after_explicit_answer_marker(text) or text

    money_match = re.search(r"[-+]?\$\s*\d+(?:,\d{3})*(?:\.\d+)?", search_text)
    if money_match:
        return money_match.group(0).replace("$ ", "$")

    percent_match = re.search(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?\s*%", search_text)
    if percent_match:
        return percent_match.group(0).replace(" %", "%")

    number_match = re.search(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?", search_text)
    if number_match:
        return number_match.group(0)

    return _extract_answer_only(text)


def _extract_answer_only(text: str) -> str:
    marked = _after_explicit_answer_marker(text)
    if marked:
        text = marked

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return text
    first = lines[0]
    for prefix in ("Answer:", "Final answer:", "Result:"):
        if first.lower().startswith(prefix.lower()):
            return first[len(prefix):].strip()
    return first


def _strip_meta_preamble(text: str) -> str:
    marked = _after_explicit_answer_marker(text)
    if marked:
        return marked.strip()

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        useful_lines = [line for line in lines if not _is_meta_reasoning_line(line)]
        if useful_lines and len(useful_lines) < len(lines):
            return "\n".join(useful_lines).strip()

    sentences = re.split(r"(?<=[.!?])\s+", text)
    useful_sentences = [sentence.strip() for sentence in sentences if sentence.strip() and not _is_meta_reasoning_line(sentence)]
    if useful_sentences and len(useful_sentences) < len(sentences):
        return " ".join(useful_sentences).strip()

    return text


def _after_explicit_answer_marker(text: str) -> str:
    matches = list(re.finditer(r"(?im)^\s*(?:final answer|answer|result)\s*:\s*", text))
    if matches:
        return text[matches[-1].end():].strip()

    inline = re.search(r"(?i)\b(?:final answer|answer|result)\s+(?:is|should be)\s+", text)
    if inline:
        return text[inline.end():].strip()

    return ""


def _is_meta_reasoning_line(text: str) -> bool:
    return bool(re.match(
        r"^\s*(?:the user wants|the user asks|the task asks|the prompt asks|i need to|let me|we need to|they want)\b",
        text,
        flags=re.IGNORECASE,
    ))


def _canonical_label(label: str, allowed_labels: tuple[str, ...] | list[str]) -> str:
    lowered = label.lower()
    for allowed in allowed_labels:
        if allowed.lower() == lowered:
            return allowed
    return label


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
