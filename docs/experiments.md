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
- Log file:
- Report file:
- Models tested:
- Categories covered:
- Accuracy observations:
- Token observations:
- Latency observations:
- Prompt policy observations:
- Failure cases:
- Decision:

## Planned Experiments

### Golden Tier Quality Gate

- Name: Golden Tier Quality Gate
- Date: TBD
- Goal: Keep smoke, regression, adversarial, and core model-matrix coverage passing as router logic changes.
- Strategy tested: Run `scripts/run_local_quality_gate.py`, then compare candidate reports against the previous accepted baseline.
- Dataset: `local_test/input/tasks.json`, `eval/golden_tier_2_regression.jsonl`, `eval/golden_tier_3_adversarial.jsonl`, and `eval/model_matrix_scenarios.jsonl`.
- Local solver coverage: Measured by router sweep.
- Fireworks calls required: Mocked locally by default; live only for selected mini-matrix slices.
- Expected token impact: Prevents token savings from being promoted when accuracy regresses.
- Log file: `eval_runs/local_quality_gate_latest.json`.
- Report file: router/model matrix markdown reports under `eval_runs/`.
- Models tested: Runtime `ALLOWED_MODELS` in live mode.
- Categories covered: all 8 Track 1 categories.
- Accuracy observations: TBD.
- Token observations: TBD.
- Latency observations: TBD.
- Prompt policy observations: TBD.
- Failure cases: Unsafe local acceptance, wrong remote mode, exact-format failure, category regression, token increase without score improvement.
- Decision: Promote only if `docs/accuracy-gates.md` is satisfied.

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

### Always-Fireworks vs Hybrid Router

- Name: Always-Fireworks vs Hybrid Router
- Date: 2026-07-07
- Goal: Prove the final router saves recorded tokens while preserving the accuracy target.
- Strategy tested: Run the same dataset through always-Fireworks, strict hybrid, and aggressive hybrid configurations.
- Dataset: `eval/model_matrix_scenarios.jsonl` with mocked Fireworks answers.
- Local solver coverage: 0% for baseline; strict hybrid local route rate was 25.0%.
- Fireworks calls required: 100% for baseline; strict hybrid routed 75.0% remotely in mock sweep.
- Expected token impact: Hybrid must use fewer recorded tokens than baseline while preserving accuracy.
- Log file: `eval_runs/router_sweep_<timestamp>.jsonl`.
- Report file: `eval_runs/router_sweep_<timestamp>.md`.
- Accuracy observations: Latest mock sweep recommended `strict_hybrid` with 100.0% pass rate and 100.0% expected-route match.
- Token observations: Strict hybrid used 607 mock total tokens versus 731 for always-Fireworks.
- Latency observations: TBD.
- Failure cases: Earlier sweep over-accepted ambiguous NER and exact/weak summaries locally; fixed by trap guards.
- Decision: Keep `strict_hybrid` as the current mock-selected config until live Fireworks/model-matrix data says otherwise.

### Local Deterministic High-Confidence Only

- Name: Local Deterministic High-Confidence Only
- Date: TBD
- Goal: Identify safe zero-token coverage after local classification.
- Strategy tested: Classify locally first, use deterministic local solvers when confidence is high, otherwise Fireworks.
- Dataset: Local synthetic set plus any public examples released by organizers.
- Local solver coverage: TBD by category.
- Fireworks calls required: Expected lower than baseline.
- Expected token impact: Meaningful reduction if sentiment, arithmetic, and simple NER coverage is strong.
- Accuracy observations: TBD.
- Failure cases: TBD.
- Decision: TBD.

### Adversarial Routing Set

- Name: Adversarial Routing Set
- Date: TBD
- Goal: Prevent overconfident zero-token answers from failing the accuracy gate.
- Strategy tested: Include prompts that appear simple but contain sarcasm, multi-step arithmetic, strict formatting, negation, subtle code bugs, or entity ambiguity.
- Dataset: Hand-authored adversarial scenarios across all 8 categories.
- Local solver coverage: Expected low unless validator can prove correctness.
- Fireworks calls required: Expected higher than simple fixtures.
- Expected token impact: Slightly higher than optimistic routing; safer for the accuracy gate.
- Accuracy observations: TBD.
- Token observations: TBD.
- Failure cases: False local acceptance, compact prompt losing constraints, answer-only mode omitting required detail.
- Decision: Any adversarial failure becomes either a validator rule, classifier risk flag, prompt-template change, or model-routing adjustment.

### Risk Engine Coverage Matrix

- Name: Risk Engine Coverage Matrix
- Date: TBD
- Goal: Verify that every routing risk component and remote mode is exercised with metrics.
- Strategy tested: Run scenario groups across ambiguity, reasoning depth, format strictness, code risk, factual freshness, and validator weakness.
- Dataset: Expanded local eval with safe, borderline, adversarial, exact-format, timeout, and malformed-response scenarios.
- Local solver coverage: Measured by category and router mode.
- Fireworks calls required: Mocked first; live only for selected high-value slices.
- Expected token impact: Indirect; improves routing safety and prevents accidental high-token/low-accuracy configs.
- Log file: `eval_runs/risk_engine_<timestamp>.jsonl`.
- Report file: `eval_runs/risk_engine_<timestamp>.md`.
- Models tested: Selected from `ALLOWED_MODELS` when live.
- Categories covered: all 8 Track 1 categories.
- Accuracy observations: TBD.
- Token observations: TBD.
- Latency observations: TBD.
- Prompt policy observations: TBD.
- Failure cases: Missing log fields, untested risk component, unsafe local acceptance, wrong remote mode, invalid normalization.
- Decision: Do not promote router changes until every risk component and remote mode has at least one passing scenario.

### Confidence Threshold Comparison: 0.85 vs 0.90 vs 0.95

- Name: Confidence Threshold Comparison
- Date: TBD
- Goal: Find the safest configurable threshold for accepting local answers and keep the exact accuracy gate programmable/changeable.
- Strategy tested: Run identical datasets through local classifier -> local solver -> validator with accept thresholds at 0.85, 0.90, and 0.95.
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

### Remote Mode Comparison

- Name: Remote Mode Comparison
- Date: TBD
- Goal: Decide when to use `remote_concise`, `remote_accuracy`, `remote_format_strict`, and `remote_code`.
- Strategy tested: Run the same Fireworks-routed scenarios through each compatible remote mode and compare accuracy/tokens.
- Dataset: Hard and format-sensitive scenarios from each Track 1 category.
- Local solver coverage: Not used; this isolates remote routing behavior.
- Fireworks calls required: `remote_modes * selected_scenarios * candidate_models` in live mode.
- Expected token impact: Concise mode should save tokens; accuracy/format/code modes should protect the gate on risky tasks.
- Log file: `eval_runs/remote_mode_<timestamp>.jsonl`.
- Report file: `eval_runs/remote_mode_<timestamp>.md`.
- Models tested: Selected from `ALLOWED_MODELS`.
- Categories covered: all 8 Track 1 categories where applicable.
- Accuracy observations: TBD.
- Token observations: TBD.
- Latency observations: TBD.
- Prompt policy observations: TBD.
- Failure cases: Truncation, verbose answers, invalid JSON/format, code syntax errors, unnecessary accuracy-mode token spend.
- Decision: Promote remote mode defaults by category only when report metrics justify them.

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
- Log file: `eval_runs/<run_id>.jsonl`.
- Report file: `eval_runs/<run_id>.md`.
- Models tested: `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it-nvfp4`.
- Categories covered: all 8 Track 1 categories.
- Accuracy observations: TBD.
- Token observations: TBD.
- Latency observations: TBD.
- Failure cases: TBD.
- Decision: TBD after live run.

### Per-Category Rerun After Prompt Tuning

- Name: Per-Category Rerun After Prompt Tuning
- Date: TBD
- Goal: Re-test only categories where the first matrix shows weak accuracy or excessive tokens.
- Strategy tested: Category-specific prompt and `max_tokens` changes.
- Dataset: Failed or borderline scenarios plus nearby variants.
- Local solver coverage: Not used; this isolates Fireworks prompt/model behavior.
- Fireworks calls required: `candidate_models * affected_category_scenarios`.
- Expected token impact: Lower than full matrix because only affected categories rerun.
- Log file: `eval_runs/<run_id>.jsonl`.
- Report file: `eval_runs/<run_id>.md`.
- Models tested: TBD per category.
- Categories covered: TBD.
- Accuracy observations: TBD.
- Token observations: TBD.
- Latency observations: TBD.
- Failure cases: TBD.
- Decision: Promote improved prompt/model settings if accuracy stays stable and tokens fall.

### Router Config Promotion

- Name: Router Config Promotion
- Date: TBD
- Goal: Convert model matrix evidence into final router configuration.
- Strategy tested: Use per-category default model, accuracy-mode model, and `max_tokens` settings selected from evidence.
- Dataset: Full local eval and Docker fixture eval.
- Local solver coverage: As implemented.
- Fireworks calls required: Only tasks routed to Fireworks.
- Expected token impact: Lower than always-Fireworks baseline.
- Log file: TBD.
- Report file: TBD.
- Models tested: Selected per category.
- Categories covered: all 8 Track 1 categories.
- Accuracy observations: TBD.
- Token observations: TBD.
- Latency observations: TBD.
- Failure cases: TBD.
- Decision: Accept only if accuracy target is met and token usage improves over all-Fireworks baseline.

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

### Prompt Policy Comparison

- Name: Prompt Policy Comparison
- Date: TBD
- Goal: Decide when to send original input, compact prompt, or answer-only prompt to Fireworks.
- Strategy tested: `original` vs `compact` vs `answer_only` prompt policies in `eval/model_matrix.py`.
- Dataset: Category-balanced scenarios, with emphasis on exact-wording-sensitive categories.
- Local solver coverage: Not used; this isolates Fireworks prompt-policy behavior.
- Fireworks calls required: `models * scenarios * prompt_policies` in live mode.
- Expected token impact: `answer_only` may reduce completion tokens; `compact` may improve format adherence; `original` may protect accuracy on exact-detail tasks.
- Log file: `eval_runs/<run_id>.jsonl`.
- Report file: `eval_runs/<run_id>.md`.
- Models tested: all allowed models or selected candidates after initial matrix.
- Categories covered: all 8 Track 1 categories.
- Accuracy observations: TBD.
- Token observations: TBD.
- Latency observations: TBD.
- Prompt policy observations: TBD.
- Failure cases: Loss of constraints, missing exact details, over-short answers, malformed code.
- Decision: Promote prompt policy by category only when accuracy stays at target and token usage improves.

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

### Timeout and Fallback Test

- Name: Timeout and Fallback Test
- Date: TBD
- Goal: Ensure one slow or failed Fireworks request does not break the whole batch.
- Strategy tested: Mock Fireworks timeout, HTTP error, invalid JSON response, and missing usage fields.
- Dataset: Small local fixture with one forced failure and several normal tasks.
- Local solver coverage: Mixed.
- Fireworks calls required: Mocked.
- Expected token impact: Not measured; this is reliability/compliance protection.
- Accuracy observations: TBD.
- Failure cases: Batch crash, malformed `/output/results.json`, repeated retries wasting time.
- Decision: Accept only if output remains valid JSON and successful tasks still return answers.

### Production Readiness Failure Matrix

- Name: Production Readiness Failure Matrix
- Date: TBD
- Goal: Prove the container keeps valid output under common runtime failures.
- Strategy tested: Mock or fixture-test malformed input, malformed task items, missing env vars, Fireworks timeout, HTTP error, invalid JSON response, missing `choices`, missing `usage`, disallowed models, normalization failures, and telemetry writes.
- Dataset: Small local fixture set plus synthetic malformed files/tasks.
- Local solver coverage: Mixed.
- Fireworks calls required: Mocked only for failure scenarios.
- Expected token impact: None directly; protects against zero-score failures.
- Log file: `eval_runs/production_readiness_<timestamp>.jsonl` or test output.
- Report file: `eval_runs/production_readiness_<timestamp>.md` or test summary.
- Models tested: Mocked allowed/disallowed model selection.
- Categories covered: IO/runtime failure cases plus at least one normal task.
- Accuracy observations: TBD.
- Token observations: TBD.
- Latency observations: TBD.
- Prompt policy observations: Not applicable.
- Failure cases: Batch crash, malformed final JSON, leaked secret, retry loop, empty answer, telemetry corrupts official output.
- Decision: Required before final Docker push.

## Source-Backed Constraints for Experiments

- Evaluation uses unseen variants; do not tune to exact public examples. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Submissions are rate-limited to 10 per hour per team, so local and Docker testing must happen before repeated submission. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Fireworks calls must use `FIREWORKS_BASE_URL` and models from `ALLOWED_MODELS`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Current planning model set is `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, and `gemma-4-31b-it-nvfp4`. Source: `Guides/AMD Developer Hackathon Participant Guide.txt`.
- Native.Builder is not part of the experiment plan for now; revisit only if it helps prototype without changing final runtime compliance.

## Official Submission Attempt Strategy

- Treat the 10-submissions-per-hour limit as a scarce optimization loop, not the main test harness.
- Before each official submission, run local smoke tests, router config sweep, model matrix checks, and Docker fixture validation.
- Use official submissions only for the best locally ranked candidate images.
- After each official result, record timestamp, image tag/digest, router config, local report paths, official accuracy/pass status if shown, official token usage if shown, and observed failure notes.
- Change only one major variable per official submission when possible: router threshold, model map, prompt policy, `max_tokens`, or local solver coverage.
- Stop submitting immediately if output format, pullability, or env handling fails; fix compliance locally before spending another attempt.

## Logging and Testing Integrity Rule

- Every scenario row must include enough data to reproduce the routing decision: category, risk score, risk components, local confidence, validator status, route, route reason, remote mode, model, prompt policy, `max_tokens`, latency, token fields, score/pass result, and error if present.
- Every markdown report must aggregate by category, router mode, remote mode, prompt policy, and model when those dimensions are present.
- Any new router feature must add or update at least one scenario proving it works and one adversarial scenario proving it fails safely.
