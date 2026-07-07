# Track 1 Strategy Plan

This plan targets rank #1 for Track 1 only. It separates source-backed constraints from our engineering strategy.

## Core Ranking Logic

1. Accuracy gate first.
   - Source-backed fact: submissions below the accuracy threshold are excluded from the leaderboard. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
   - Engineering decision: keep the exact local evaluation threshold programmable/configurable because the official numeric threshold is not present in the current `Guides/`.
2. Token minimization second.
   - Source-backed fact: passing submissions are ranked ascending by total tokens recorded by the judging proxy. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
3. Wrong zero-token answers are dangerous.
   - Decision: a local answer that fails the LLM judge can eliminate us from ranking, so zero tokens are only valuable when confidence is high.

## Rank #1 Strategy

- Use confidence-gated local solvers for deterministic or high-confidence tasks.
- Use category-specific Fireworks fallback when local solvers are uncertain, output validation fails, or the task is naturally high risk.
- Use Fireworks accuracy mode for hard/risky tasks: richer prompts, more careful instructions, and model selection optimized for correctness.
- Use model selection only from runtime `ALLOWED_MODELS`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Use AMD AI Notebooks / AMD Developer Cloud for validation evidence and optional local-model experiments, not as a required final runtime unless organizers confirm that path. Sources: `Guides/Hackathon Act II.txt`, `Guides/AMD Developer Hackathon Participant Guide.txt`.
- Keep final container CPU-safe unless local LLM runtime is proven to fit the standardized environment, 10-minute runtime, 60-second startup, 30-second per-response, and 10GB compressed image limits. Sources: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`, `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- Local deterministic logic and local model experimentation are allowed under the Track 1 local-token rule. Whenever the router chooses Fireworks, the request must be sent through `FIREWORKS_BASE_URL` so the judging proxy can record token usage. The final agent treats `FIREWORKS_BASE_URL` as the only valid remote inference base URL and selects models only from `ALLOWED_MODELS`.
- Do not use Native.Builder for now; revisit only if it accelerates prototyping without entering the final runtime path.

## Model Selection

- Runtime model list must come from `ALLOWED_MODELS`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- The short guide currently lists Track 1 models: `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, and `gemma-4-31b-it-nvfp4`. Source: `Guides/AMD Developer Hackathon Participant Guide.txt`.
- Planning model set: `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it-nvfp4`.
- Runtime enforcement: select only models present in `ALLOWED_MODELS`.

## Category-by-Category Strategy

| Category | Initial Strategy | Token Plan | Risk |
| --- | --- | --- | --- |
| Factual knowledge | Fireworks unless prompt is trivial and local rule answer is safe | Avoid local guessing; use concise prompt | Hallucination and LLM-judge mismatch |
| Mathematical reasoning | Local deterministic parser for clear arithmetic; Fireworks for word problems or uncertainty | Zero-token for parsed arithmetic | Multi-step reasoning mistakes can fail gate |
| Sentiment classification | Local high-confidence classifier for clear sentiment; Fireworks for mixed/justification-heavy prompts | Strong local savings | Justification requirement may require richer answer |
| Text summarisation | Fireworks by default unless format is simple and local extractive summary is clearly adequate | Tune `max_tokens` tightly | Format/length constraints and semantic loss |
| Named entity recognition | Local regex/rule extraction for simple person/org/location/date patterns; Fireworks fallback on ambiguity | High local coverage possible | Missing labels or ambiguous entities |
| Code debugging | Fireworks by default; local only for obvious syntax or tiny deterministic corrections | Accuracy mode, concise output | Correctness hard to validate locally |
| Logical / deductive reasoning | Fireworks by default; local only for simple deterministic constraints | Accuracy mode | Constraint satisfaction failures |
| Code generation | Fireworks by default; local templates only for extremely simple functions | Accuracy mode, tuned max tokens | Hidden tests may punish subtle bugs |

## Experiments Needed Before Finalizing

- Measure all-Fireworks baseline accuracy and tokens.
- Measure local deterministic coverage by category.
- Compare confidence thresholds: 0.85 vs 0.90 vs 0.95.
- Compare category-specific Fireworks prompts.
- Compare allowed model preference by category once `ALLOWED_MODELS` is known.
- Tune `max_tokens` by category without hurting answer quality.
- Test hard-task Fireworks accuracy mode.
- Run Docker with mounted `/input` and `/output` on `linux/amd64`.

## Current Assumptions

- The hidden benchmark uses unseen variants in the same general task categories. Source-backed unseen-variant fact: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- The exact accuracy threshold is unknown, so the local threshold must remain configurable.
- Final evaluator GPU access for local LLM inference inside the submitted Docker container is not confirmed. Therefore, the final image should remain CPU-safe and should not require a GPU to run correctly.
- Native.Builder is optional support infrastructure and is not part of the plan for now. Source for Builder option: `Guides/Hackathon Act II.txt`.

## Stop Conditions

- Do not optimize token use if accuracy drops below the gate.
- Do not introduce a heavy local model if it threatens image size, startup time, runtime, or per-response limits.
- Do not call any model outside `ALLOWED_MODELS`.
