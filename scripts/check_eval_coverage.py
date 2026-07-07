import json
import sys
from collections import Counter
from pathlib import Path


REQUIRED_CATEGORIES = {
    "factual_knowledge",
    "mathematical_reasoning",
    "sentiment_classification",
    "text_summarisation",
    "named_entity_recognition",
    "code_debugging",
    "logical_deductive_reasoning",
    "code_generation",
}

REQUIRED_DIFFICULTIES = {"easy", "medium"}
REQUIRED_SCENARIO_CLASSES = {
    "safe_local_candidate",
    "remote_candidate",
    "adversarial",
    "exact_format",
}
REQUIRED_RISK_COMPONENTS = {
    "ambiguity",
    "reasoning_depth",
    "format_strictness",
    "code_risk",
    "factual_freshness",
    "local_validator_weakness",
}
REQUIRED_OUTPUT_CONSTRAINTS = {
    "answer_only",
    "exact_numeric",
    "label_plus_reason",
    "one_sentence",
    "exact_word_count",
    "entity_labels",
    "code_only",
    "one_word",
}
REQUIRED_ANSWER_SHAPES = {
    "label",
    "number",
    "short_text",
    "summary",
    "entity_list",
    "code",
    "corrected_code",
}
REQUIRED_CONSTRAINTS = {
    "answer_only",
    "no_explanation",
    "one_sentence",
    "exact_word_count",
    "code_only",
    "label_plus_reason",
    "entity_labels",
    "exact_numeric",
    "include_corrected_code",
}
REQUIRED_REMOTE_MODES = {
    "remote_concise",
    "remote_accuracy",
    "remote_format_strict",
    "remote_code",
}
REQUIRED_VERIFIERS = {
    "label_set",
    "numeric_exact",
    "summary_constraints",
    "entity_labels",
    "python_syntax",
    "word_count",
    "keyword_coverage",
}
REQUIRED_FAILURE_TAXONOMY = {
    "wrong_category",
    "local_overconfidence",
    "validator_too_weak",
    "remote_model_weak",
    "prompt_too_loose",
    "max_tokens_too_low",
    "output_format_failure",
}


def load_rows(path):
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            rows.append(row)
    return rows


def collect(rows, key):
    values = set()
    for row in rows:
        value = row.get(key)
        if isinstance(value, list):
            values.update(value)
        elif value:
            values.add(value)
    return values


def require(name, found, required):
    missing = sorted(required - found)
    if missing:
        return [f"{name} missing: {', '.join(missing)}"]
    return []


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("eval/model_matrix_scenarios.jsonl")
    rows = load_rows(path)
    errors = []

    if not rows:
        errors.append(f"{path} has no scenarios")

    task_ids = [row.get("task_id") for row in rows]
    duplicate_task_ids = [task_id for task_id, count in Counter(task_ids).items() if count > 1]
    if duplicate_task_ids:
        errors.append("duplicate task_id values: " + ", ".join(sorted(duplicate_task_ids)))

    errors.extend(require("category coverage", collect(rows, "category"), REQUIRED_CATEGORIES))
    errors.extend(require("difficulty coverage", collect(rows, "difficulty"), REQUIRED_DIFFICULTIES))
    errors.extend(require("scenario_class coverage", collect(rows, "scenario_class"), REQUIRED_SCENARIO_CLASSES))
    errors.extend(require("risk_components coverage", collect(rows, "risk_components"), REQUIRED_RISK_COMPONENTS))
    errors.extend(require("output_constraints coverage", collect(rows, "output_constraints"), REQUIRED_OUTPUT_CONSTRAINTS))
    errors.extend(require("answer_shape coverage", collect(rows, "answer_shape"), REQUIRED_ANSWER_SHAPES))
    errors.extend(require("constraints coverage", collect(rows, "constraints"), REQUIRED_CONSTRAINTS))
    errors.extend(require("remote_mode_hint coverage", collect(rows, "remote_mode_hint"), REQUIRED_REMOTE_MODES))
    errors.extend(require("verifier coverage", collect(rows, "verifier"), REQUIRED_VERIFIERS))
    errors.extend(require("failure_taxonomy coverage", collect(rows, "failure_taxonomy"), REQUIRED_FAILURE_TAXONOMY))

    required_fields = {
        "task_id",
        "category",
        "difficulty",
        "scenario_class",
        "intent",
        "answer_shape",
        "constraints",
        "risk_components",
        "output_constraints",
        "expected_route",
        "remote_mode_hint",
        "verifier",
        "retry_policy",
        "failure_taxonomy",
        "prompt",
        "expected_keywords",
        "expected_answer",
        "scoring_notes",
    }
    for index, row in enumerate(rows, start=1):
        missing_fields = sorted(field for field in required_fields if field not in row)
        if missing_fields:
            errors.append(f"scenario row {index} missing fields: {', '.join(missing_fields)}")

    if errors:
        for error in errors:
            print("ERROR:", error)
        raise SystemExit(1)

    print(f"OK: {len(rows)} scenarios in {path}")
    print(f"Categories: {len(collect(rows, 'category'))}")
    print(f"Scenario classes: {', '.join(sorted(collect(rows, 'scenario_class')))}")
    print(f"Risk components: {', '.join(sorted(collect(rows, 'risk_components')))}")
    print(f"Answer shapes: {', '.join(sorted(collect(rows, 'answer_shape')))}")
    print(f"Constraints: {', '.join(sorted(collect(rows, 'constraints')))}")
    print(f"Remote modes: {', '.join(sorted(collect(rows, 'remote_mode_hint')))}")
    print(f"Verifiers: {', '.join(sorted(collect(rows, 'verifier')))}")


if __name__ == "__main__":
    main()
