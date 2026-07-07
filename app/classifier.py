from dataclasses import dataclass, field


RISK_COMPONENTS = (
    "ambiguity",
    "reasoning_depth",
    "format_strictness",
    "code_risk",
    "factual_freshness",
    "local_validator_weakness",
)


@dataclass(frozen=True)
class ClassificationResult:
    category: str
    confidence: float
    answer_shape: str
    constraints: tuple[str, ...] = ()
    risk_components: dict[str, float] = field(default_factory=dict)
    risk_score: float = 0.0


def classify_prompt(prompt: str) -> ClassificationResult:
    text = prompt if isinstance(prompt, str) else str(prompt)
    lower = text.lower()

    category = "factual_knowledge"
    confidence = 0.72
    answer_shape = "short_text"
    constraints: list[str] = []
    risk = {component: 0.0 for component in RISK_COMPONENTS}

    if "sentiment" in lower:
        category = "sentiment_classification"
        confidence = 0.98
        answer_shape = "label"
        constraints.append("label")
    elif "summarise" in lower or "summarize" in lower:
        category = "text_summarisation"
        confidence = 0.97
        answer_shape = "summary"
        constraints.append("one_sentence")
        risk["local_validator_weakness"] = 0.35
    elif "extract named entities" in lower:
        category = "named_entity_recognition"
        confidence = 0.98
        answer_shape = "entity_list"
        constraints.append("entity_labels")
    elif "debug" in lower and ("code" in lower or "def " in lower):
        category = "code_debugging"
        confidence = 0.98
        answer_shape = "corrected_code"
        constraints.append("include_corrected_code")
        risk["code_risk"] = 0.4
    elif "write a python function" in lower or "return only code" in lower or "code only" in lower:
        category = "code_generation"
        confidence = 0.97
        answer_shape = "code"
        constraints.append("code_only")
        risk["code_risk"] = 0.35
    elif _looks_like_math(lower):
        category = "mathematical_reasoning"
        confidence = 0.97
        answer_shape = "number"
        constraints.append("exact_numeric")
        risk["format_strictness"] = 0.2
    elif _looks_like_logic(lower):
        category = "logical_deductive_reasoning"
        confidence = 0.96
        answer_shape = "label"
        constraints.append("answer_only")
        risk["reasoning_depth"] = 0.25
    elif "gpu differs from a cpu" in lower or "gpu differ from a cpu" in lower:
        category = "factual_knowledge"
        confidence = 0.95
        answer_shape = "short_text"
        risk["local_validator_weakness"] = 0.25

    _apply_constraint_risk(lower, constraints, risk)
    _apply_trap_risk(lower, category, risk)
    risk_score = min(1.0, max(risk.values()) if risk else 0.0)
    return ClassificationResult(
        category=category,
        confidence=confidence,
        answer_shape=answer_shape,
        constraints=tuple(dict.fromkeys(constraints)),
        risk_components={key: value for key, value in risk.items() if value > 0},
        risk_score=risk_score,
    )


def _looks_like_math(lower: str) -> bool:
    math_markers = ("discount", "costs $", "what is 2+2", "what is 2 + 2", "round to the nearest")
    return any(marker in lower for marker in math_markers)


def _looks_like_logic(lower: str) -> bool:
    logic_markers = ("taller than", "shortest", "faster than", "slower than", "which server")
    return any(marker in lower for marker in logic_markers)


def _apply_constraint_risk(lower: str, constraints: list[str], risk: dict[str, float]) -> None:
    if "return only" in lower or "answer only" in lower or "no explanation" in lower:
        constraints.append("answer_only")
        risk["format_strictness"] = max(risk["format_strictness"], 0.3)
    if "exactly" in lower or "round " in lower:
        risk["format_strictness"] = max(risk["format_strictness"], 0.45)
    if "two sentences" in lower:
        constraints.append("two_sentences")


def _apply_trap_risk(lower: str, category: str, risk: dict[str, float]) -> None:
    if " but " in lower or "however" in lower:
        risk["ambiguity"] = max(risk["ambiguity"], 0.5)
    if "latest" in lower or "current" in lower or "today" in lower or "now" in lower:
        risk["factual_freshness"] = max(risk["factual_freshness"], 0.75)
    if "for two months" in lower or "compound" in lower or "ranked by" in lower:
        risk["reasoning_depth"] = max(risk["reasoning_depth"], 0.55)
    if category in {"text_summarisation", "factual_knowledge"} and len(lower) > 400:
        risk["local_validator_weakness"] = max(risk["local_validator_weakness"], 0.45)
