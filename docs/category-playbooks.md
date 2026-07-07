# Category Playbooks

Purpose: make routing decisions category-specific instead of relying on one generic confidence threshold.

Each category should have local acceptance criteria, remote fallback criteria, validator requirements, and eval scenarios. These playbooks are implementation guidance; final defaults must come from `eval` reports.

## Shared Promotion Rule

A category route can become default only when:

- the local classifier identifies the category before any Fireworks call,
- the local solver has a verifier or proof stronger than keyword matching,
- adversarial scenarios for that category do not produce unsafe local acceptance,
- the selected Fireworks mode/model is chosen from `ALLOWED_MODELS`,
- the category passes the configured accuracy gate before token savings are counted.

## Factual Knowledge

- Default route: Fireworks unless the answer is a stable built-in rule or explicit from the prompt.
- Local accept only if: the answer is directly extractive from prompt text or a fixed known concept we intentionally maintain.
- Validator: keyword coverage plus no invented current/live facts.
- Remote mode: `remote_accuracy` for current, niche, or explanation tasks; `remote_concise` for stable short explanations.
- Traps to test: current leaderboard facts, dates, benchmark-specific claims, hallucinated API details.

## Mathematical Reasoning

- Default route: local for parsed arithmetic; Fireworks for multi-step or ambiguous word problems.
- Local accept only if: parser extracts operands/operation unambiguously and exact numeric verifier passes.
- Validator: numeric exactness, rounding rule detection, answer-only formatting.
- Remote mode: `remote_format_strict` for exact numeric; `remote_accuracy` for multi-step reasoning.
- Traps to test: sequential percentages, units, rounding, negation, chained operations.

## Sentiment Classification

- Default route: local for high-confidence clear polarity; Fireworks for mixed/sarcastic/justification-heavy prompts.
- Local accept only if: polarity words are strong, no sarcasm marker, no mixed conjunction, and label format passes.
- Validator: label set plus required reason when requested.
- Remote mode: `remote_concise` for clear labels; `remote_accuracy` for sarcasm/mixed cases.
- Traps to test: sarcasm, "but" clauses, weak positive plus strong negative, neutral factual statements.

## Text Summarisation

- Default route: Fireworks.
- Local accept only if: exact extractive summary is explicitly safe and no strict semantic compression is needed.
- Validator: word count, one-sentence rule, no bullets when prohibited, required keyword coverage.
- Remote mode: `remote_format_strict` for length constraints; `remote_concise` for simple summaries.
- Traps to test: exact word count, conflicting style constraints, important named entities, token trimming.

## Named Entity Recognition

- Default route: local for simple person/org/location/date patterns; Fireworks for ambiguous labels or product names.
- Local accept only if: every detected entity has a label and no ambiguous entity class is present.
- Validator: entity-label pairs, date preservation, no missing obvious capitalized entities.
- Remote mode: `remote_format_strict`.
- Traps to test: Apple/Gemma ambiguity, multi-token orgs, dates, locations that are also products.

## Code Debugging

- Default route: Fireworks.
- Local accept only if: bug pattern is deterministic and corrected code passes syntax plus targeted micro-check.
- Validator: Python syntax, required function name, no markdown when code-only requested.
- Remote mode: `remote_code`.
- Traps to test: boundary conditions, accumulator resets, wrong operator, indentation, hidden behavior.

## Logical / Deductive Reasoning

- Default route: Fireworks.
- Local accept only if: relation graph or deterministic rule solver proves the answer.
- Validator: answer-only formatting, no unwarranted inference, exact label when requested.
- Remote mode: `remote_accuracy`.
- Traps to test: incomplete information, negation, pairwise comparisons with no bridge, reversed ordering.

## Code Generation

- Default route: Fireworks.
- Local accept only if: known template fully satisfies the requested function and constraints.
- Validator: Python syntax, function name, core keyword/operation checks, no imports when prohibited.
- Remote mode: `remote_code`.
- Traps to test: no-import constraints, edge cases, exact function name, code-only output, hidden tests.
