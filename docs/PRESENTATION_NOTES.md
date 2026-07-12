# Presentation Notes

Use this as source material for slides.

## 1. Problem

General-purpose AI agents often send every task to a remote model. That is simple, but it can waste tokens on tasks that are easy, deterministic, or locally verifiable.

## 2. Why Naive Model Usage Is Inefficient

- Simple arithmetic, labels, and templated code do not always need a remote LLM.
- Remote calls add token usage and latency.
- Model answers still require normalization and validation.

## 3. Juggernaut Router Solution

Juggernaut Router classifies each task and chooses between deterministic solvers, optional local GGUF inference, and remote Fireworks models.

## 4. Architecture

Input file -> task loader -> classifier -> deterministic solver -> optional local model -> Fireworks fallback -> validation -> output file.

Use the diagram in `docs/ARCHITECTURE.md`.

## 5. Routing Strategy

The router supports all eight Track 1 categories and uses category/risk signals to avoid unnecessary remote calls while preserving fallback paths for harder tasks.

## 6. Deterministic Solvers

Solvers target safe patterns where correctness can be validated locally, such as recognized arithmetic, sentiment labels, summaries, NER forms, code templates, and factual patterns.

## 7. Local and Remote Model Use

Local GGUF inference is optional and must be enabled at build/runtime. Remote inference uses Fireworks through `FIREWORKS_BASE_URL` and model aliases from `ALLOWED_MODELS`.

## 8. Token-Efficiency Strategy

The agent minimizes unnecessary remote calls only after local validation. Remote calls remain available for high-risk, ambiguous, or strict-format tasks.

## 9. Reliability and Validation

The system validates answer format, labels, numeric outputs, code formatting, repetition, and route failures. It emits startup/finish diagnostics and optional per-task telemetry.

## 10. Demo Flow

1. Show repository structure.
2. Run `./scripts/demo.sh`.
3. Show `examples/sample_tasks.json`.
4. Show `/tmp/juggernaut-demo-output/results.json`.
5. Re-run with `ROUTER_LOG_PATH` and show route decisions.

## 11. Results and Evidence

- Latest verified leaderboard accuracy: `[Insert latest verified leaderboard accuracy]`
- Latest verified token usage: `[Insert latest verified token usage]`
- Final submitted image: `[Insert final public image tag]`
- Evidence files: `eval_runs/` and `docs/official-submission-log.md` when available.

## 12. Limitations

- Local models can be unreliable across broad task types.
- Remote APIs are required for some high-risk routes.
- Classification errors can affect route choice.
- Model answers can vary and require validation.

## 13. Future Improvements

- Add more narrow deterministic solvers.
- Improve category-specific validation.
- Evaluate stronger local models per category.
- Add richer public demos and visual dashboards.

## 14. Closing Message

Juggernaut Router is built around a practical idea: route easy work cheaply, reserve powerful models for risky work, and validate the result before returning it.
