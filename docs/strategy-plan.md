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

- Classify every task locally before any Fireworks call.
- Treat routing as a risk engine: prove local safety first, otherwise route to Fireworks.
- Use confidence-gated local solvers for deterministic or high-confidence tasks.
- Use category-specific validators as the main defense against overconfident zero-token answers.
- Maintain category playbooks for local acceptance, remote fallback, validators, and known traps.
- Use category-specific Fireworks fallback when local solvers are uncertain, output validation fails, or the task is naturally high risk.
- Use Fireworks accuracy mode for hard/risky tasks: richer prompts, more careful instructions, and model selection optimized for correctness.
- Maintain configurable `conservative`, `balanced`, and `aggressive` router modes for official submission comparisons.
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
- Per-category model defaults should be selected from logged model-matrix evidence, not guesses.
- Model selection should remain configuration-driven so we can update category preferences after experiments without rewriting router logic.
- For each category, track both the best-accuracy model and the cheapest passing model.
- Prompt policy should also be selected from evidence: original input, compact prompt, or answer-only prompt.

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

## Local-First Decision Policy

Every task should pass through this decision sequence:

1. Local classification: identify category, confidence, and risk.
2. Risk scoring: estimate ambiguity, reasoning depth, format strictness, code risk, factual freshness, and validator weakness.
3. Local solvability check: decide whether any local solver can prove correctness.
4. Local solver attempt: only for categories with deterministic or high-confidence local coverage.
5. Local validation: reject empty, malformed, non-English, low-confidence, unchecked, or structurally wrong answers.
6. Route decision:
   - Stay local when category confidence, solver confidence, and validation all pass.
   - Use Fireworks when the category is risky, confidence is low, solver coverage is missing, or validation fails.
7. Fireworks mode selection: choose concise, accuracy, format-strict, or code mode.
8. Fireworks model selection: choose from `ALLOWED_MODELS` based on category/model matrix results.
9. Prompt policy selection: use original prompt when exact wording matters; use compact or answer-only only when experiments show no accuracy loss.
10. Decision logging: record route, risk, validator notes, model, prompt policy, tokens, latency, and errors.

The router must never use Fireworks as the first step for all tasks. Fireworks is the fallback or accuracy path after local classification decides it is needed.

See `docs/elite-routing-plan.md` for the full risk-engine design.
See `docs/category-playbooks.md` for category-specific acceptance rules.
See `docs/accuracy-gates.md` for promotion thresholds and A/B config rules.

## Prompt Size Policy

Prompt resizing is allowed only when metrics show it preserves accuracy.

- Preserve original task text for math word problems, logic puzzles, code debugging, code generation, NER, and strict summarization constraints.
- Prefer reducing wrapper text and `max_tokens` before trimming user content.
- Test `original`, `compact`, and `answer_only` prompt policies by category.
- Promote prompt policy decisions into configuration, not hardcoded branches.
- Any uncertain prompt-size decision must be tested and logged before becoming default behavior.

## Experiments Needed Before Finalizing

- Measure all-Fireworks baseline accuracy and tokens.
- Measure local deterministic coverage by category.
- Compare confidence thresholds: 0.85 vs 0.90 vs 0.95.
- Compare category-specific Fireworks prompts.
- Compare allowed model preference by category once `ALLOWED_MODELS` is known.
- Tune `max_tokens` by category without hurting answer quality.
- Compare always-Fireworks, strict hybrid, and aggressive hybrid router modes on the same dataset.
- Keep router decision logs for experiments so every local-vs-Fireworks choice can be audited.
- Test adversarial examples for every category before promoting a local solver, validator, prompt policy, or model choice.
- Maintain tiered golden datasets: smoke, regression, adversarial, and full model matrix.
- Compare candidate eval reports against baselines before changing defaults.
- Test the full risk-engine scenario matrix: risk components, remote modes, router modes, validators, prompt policies, and model maps.
- Test timeout, retry, fallback, and answer-normalization behavior as first-class quality gates.
- Test hard-task Fireworks accuracy mode.
- Run Docker with mounted `/input` and `/output` on `linux/amd64`.

## Submission Optimization Loop

Use official submissions only after local evidence selects a candidate.

1. Run local smoke tests and JSON validation.
2. Run `eval/router_config_sweep.py` and select the best eligible config by accuracy first, tokens second.
3. Run the allowed-model matrix for any changed model/prompt settings.
4. Build and test the Docker image locally.
5. Submit one candidate image.
6. Record the official result and change only one major variable before the next attempt.

This lets us use the submission limit as measured feedback while avoiding random leaderboard poking.

Detailed rules:

- implementation order: `docs/implementation-phases.md`
- official submission decisions: `docs/official-submission-decision-tree.md`
- live Fireworks spend: `docs/live-eval-budget-plan.md`
- risks and mitigations: `docs/risk-register.md`
- eval field definitions: `docs/eval-field-glossary.md`

## Current Assumptions

- The hidden benchmark uses unseen variants in the same general task categories. Source-backed unseen-variant fact: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- The exact accuracy threshold is unknown, so the local threshold must remain configurable.
- Final evaluator GPU access for local LLM inference inside the submitted Docker container is not confirmed. Therefore, the final image should remain CPU-safe and should not require a GPU to run correctly.
- Native.Builder is optional support infrastructure and is not part of the plan for now. Source for Builder option: `Guides/Hackathon Act II.txt`.

## Stop Conditions

- Do not optimize token use if accuracy drops below the gate.
- Do not introduce a heavy local model if it threatens image size, startup time, runtime, or per-response limits.
- Do not call any model outside `ALLOWED_MODELS`.
