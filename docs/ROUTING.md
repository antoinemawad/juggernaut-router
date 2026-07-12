# Routing

This document describes the high-level routing behavior implemented in `app/agent.py`, `app/classifier.py`, and `app/solvers/basic.py`.

It intentionally avoids publishing exact private heuristics or hidden prompt details.

## Recognized Categories

| Category | What it covers | Typical handling |
| --- | --- | --- |
| `factual_knowledge` | Concepts, definitions, stable technical facts | Deterministic for recognized facts; otherwise model route |
| `mathematical_reasoning` | Arithmetic, percentages, budgets, projections | Deterministic for recognized formulas; otherwise model route |
| `sentiment_classification` | Positive/negative/neutral labels and brief reasons | Deterministic/local for safe labels; remote for ambiguity |
| `text_summarisation` | Concise summaries and length constraints | Deterministic/local for known safe patterns; remote for strict constraints |
| `named_entity_recognition` | Person, organization, location, date extraction | Deterministic for recognized patterns; remote for ambiguous extraction |
| `code_debugging` | Bug identification and corrected code | Deterministic templates for recognized bugs; model route for broader code |
| `logical_deductive_reasoning` | Constraint puzzles and logical labels | Deterministic for recognized puzzles; model route for deeper reasoning |
| `code_generation` | Small functions from a spec | Deterministic templates for known specs; model route for broader code |

## Decision Order

1. Classify the prompt.
2. Try deterministic solver.
3. Validate deterministic answer.
4. If local model is enabled and category-eligible, try local GGUF.
5. Validate local-model answer.
6. If needed and configured, call Fireworks through `FIREWORKS_BASE_URL`.
7. Validate and optionally escalate remote answer.
8. Normalize final answer.
9. Return safe fallback only when no accepted answer path is available.

## Fallback Route

The fallback answer is intentionally conservative. It is used when:

- Fireworks configuration is missing and no local answer is accepted.
- The deadline suppresses additional model calls.
- Local and remote model paths fail or return invalid output.

## Validation Behavior

Validation checks vary by answer shape and constraints. Examples include:

- Numeric answers must match numeric/currency expectations.
- Label answers must stay within the expected label set.
- Code answers must avoid Markdown fences when code-only output is required.
- Short answers are checked for length, repetition, and formatting artifacts.
- Entity answers are checked for required labels and expected entity mentions when fixture metadata is present.

## Ambiguous Cases

Ambiguous prompts are deliberately routed away from low-confidence local paths when the classifier detects risk such as:

- Multiple possible labels
- Fresh factual knowledge
- Deep multi-step reasoning
- Strict output formatting
- Code correctness risk

## Adding a New Solver Safely

1. Add the narrow pattern to `app/solvers/basic.py`.
2. Return a structured solver result with evidence and confidence.
3. Add validator coverage if the answer shape is new.
4. Add unit tests in `tests/`.
5. Add a fixture case in `local_test/` or `eval/` when useful.
6. Run `python3 -m unittest discover -s tests`.

Do not add broad heuristics that answer uncertain prompts without validation.
