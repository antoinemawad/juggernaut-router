# Experiments

This is the living experiment log for Track 1 strategy selection. Do not record private keys or hidden benchmark data here.

## Experiment Template

- Name:
- Date:
- Goal:
- Strategy tested:
- Dataset:
- Local solver coverage:
- Fireworks calls required:
- Expected token impact:
- Accuracy observations:
- Failure cases:
- Decision:

## Planned Experiments

### Baseline Fireworks All

- Name: Baseline Fireworks All
- Date: TBD
- Goal: Establish maximum-accuracy / high-token baseline.
- Strategy tested: Send every task to Fireworks using allowed runtime models.
- Dataset: Local synthetic set covering all 8 Track 1 categories.
- Local solver coverage: 0%.
- Fireworks calls required: 100% of tasks.
- Expected token impact: Highest token use; useful as accuracy floor for final routing.
- Accuracy observations: TBD.
- Failure cases: TBD.
- Decision: TBD.

### Local Deterministic High-Confidence Only

- Name: Local Deterministic High-Confidence Only
- Date: TBD
- Goal: Identify safe zero-token coverage.
- Strategy tested: Use only deterministic local solvers when confidence is high; otherwise Fireworks.
- Dataset: Local synthetic set plus any public examples released by organizers.
- Local solver coverage: TBD by category.
- Fireworks calls required: Expected lower than baseline.
- Expected token impact: Meaningful reduction if sentiment, arithmetic, and simple NER coverage is strong.
- Accuracy observations: TBD.
- Failure cases: TBD.
- Decision: TBD.

### Confidence Threshold Comparison: 0.85 vs 0.90 vs 0.95

- Name: Confidence Threshold Comparison
- Date: TBD
- Goal: Find the safest configurable threshold for accepting local answers and keep the exact accuracy gate programmable/changeable.
- Strategy tested: Run identical datasets with local accept thresholds at 0.85, 0.90, and 0.95.
- Dataset: Category-balanced local eval.
- Local solver coverage: Varies by threshold.
- Fireworks calls required: Increases as threshold rises.
- Expected token impact: Lower threshold saves more tokens but risks accuracy gate.
- Accuracy observations: TBD.
- Failure cases: TBD.
- Decision: TBD.

### Category-Specific Prompt Comparison

- Name: Category-Specific Prompt Comparison
- Date: TBD
- Goal: Improve Fireworks accuracy and reduce output verbosity by category.
- Strategy tested: Generic prompt vs category-specific prompt templates.
- Dataset: Hard examples from each Track 1 category.
- Local solver coverage: Not the focus.
- Fireworks calls required: 100% for compared tasks.
- Expected token impact: Lower completion tokens if prompts constrain answer shape.
- Accuracy observations: TBD.
- Failure cases: TBD.
- Decision: TBD.

### Model Preference Comparison by Category

- Name: Model Preference Comparison by Category
- Date: TBD, after harness `ALLOWED_MODELS` is confirmed at runtime.
- Goal: Select best allowed model per category.
- Strategy tested: Route each category to candidate models from `ALLOWED_MODELS`.
- Dataset: Category-balanced local eval.
- Local solver coverage: Not the focus.
- Fireworks calls required: Multiple calls per task during experiment only.
- Expected token impact: Final model map may reduce tokens or improve accuracy.
- Accuracy observations: TBD.
- Failure cases: TBD.
- Decision: Use `eval/model_matrix.py` to generate JSONL logs and a markdown report, then choose per-category model defaults by score first and token usage second.

### Allowed Model Matrix Across All Categories

- Name: Allowed Model Matrix Across All Categories
- Date: TBD
- Goal: Try each allowed model across all eight Track 1 categories and produce a showable report.
- Strategy tested: Every model against every scenario in `eval/model_matrix_scenarios.jsonl`.
- Dataset: `eval/model_matrix_scenarios.jsonl`, expanded as new public-style examples appear.
- Local solver coverage: Not used; this isolates Fireworks model behavior.
- Fireworks calls required: `allowed_models_count * scenario_count` in live mode.
- Expected token impact: Experiment-only token spend; informs final category/model routing.
- Accuracy observations: TBD.
- Failure cases: TBD.
- Decision: TBD after live run.

### max_tokens Tuning

- Name: max_tokens Tuning
- Date: TBD
- Goal: Minimize completion tokens while preserving accuracy.
- Strategy tested: Category-specific `max_tokens` values.
- Dataset: Local eval with expected concise outputs.
- Local solver coverage: Not the focus.
- Fireworks calls required: Fireworks tasks only.
- Expected token impact: Lower completion tokens, especially summarization, code, and reasoning.
- Accuracy observations: TBD.
- Failure cases: Truncated answers, missing justification, invalid code.
- Decision: TBD.

### Hard-Task Fireworks Accuracy Mode

- Name: Hard-Task Fireworks Accuracy Mode
- Date: TBD
- Goal: Protect the accuracy gate on risky categories.
- Strategy tested: More explicit Fireworks prompt for code debugging, logical reasoning, code generation, hard math, and ambiguous factual tasks.
- Dataset: Hard local eval examples.
- Local solver coverage: Low by design.
- Fireworks calls required: High for risky categories.
- Expected token impact: Higher than concise mode but safer for gate.
- Accuracy observations: TBD.
- Failure cases: Overlong answers, unnecessary explanations, token waste.
- Decision: TBD.

### Docker Runtime Test

- Name: Docker Runtime Test
- Date: TBD
- Goal: Verify final runtime compliance.
- Strategy tested: Build and run image with mounted `/input` and `/output`.
- Dataset: `local_test/input/tasks.json` plus expanded category fixtures.
- Local solver coverage: As implemented.
- Fireworks calls required: Mocked locally first; real harness-style env later.
- Expected token impact: Not measured unless real Fireworks calls are enabled.
- Accuracy observations: TBD.
- Failure cases: Missing env vars, invalid output path, non-linux/amd64 image, slow startup.
- Decision: TBD.

## Source-Backed Constraints for Experiments

- Evaluation uses unseen variants; do not tune to exact public examples. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Submissions are rate-limited to 10 per hour per team, so local and Docker testing must happen before repeated submission. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Fireworks calls must use `FIREWORKS_BASE_URL` and models from `ALLOWED_MODELS`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Current planning model set is `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, and `gemma-4-31b-it-nvfp4`. Source: `Guides/AMD Developer Hackathon Participant Guide.txt`.
- Native.Builder is not part of the experiment plan for now; revisit only if it helps prototype without changing final runtime compliance.
