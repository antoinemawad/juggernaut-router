# Submission Checklist

Final pre-submit checklist for Track 1 only.

## Repository and Documentation

- [ ] Repo is public. Source: `Guides/Hackathon Act II.txt`.
- [ ] README is complete with setup and usage instructions. Source: `Guides/Hackathon Act II.txt`.
- [ ] README documents local test commands.
- [ ] README documents Docker run with mounted `/input` and `/output`.
- [ ] README documents required environment variables.
- [ ] Track 1 execution discipline reviewed: `docs/track1-execution-discipline.md`.
- [ ] Implementation phase status reviewed: `docs/implementation-phases.md`.
- [ ] Risk register reviewed: `docs/risk-register.md`.
- [ ] Category playbooks reviewed: `docs/category-playbooks.md`.
- [ ] Accuracy gates reviewed: `docs/accuracy-gates.md`.
- [ ] Local testing and submission use the same code path; only `INPUT_PATH`, `OUTPUT_PATH`, and runtime environment variables change.
- [ ] Final manual review complete.

## Docker and Runtime

- [ ] Dockerfile builds successfully.
- [ ] Docker runtime guard passes: `python3 scripts/check_docker_runtime.py`.
- [ ] Docker run works with mounted `/input` and `/output`.
- [ ] Container reads `/input/tasks.json` on startup. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Container writes `/output/results.json` before exiting. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Output is valid JSON. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Exit code is 0 on success. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Runtime stays under 10 minutes. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Runtime measurement is treated as total process/container wall-clock time, including startup, imports, input reading, output writing, and shutdown.
- [ ] Runtime reserves a safety margin and never relies on using the full 10 minutes.
- [ ] Startup is under 60 seconds. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- [ ] Startup is treated as a sub-budget inside the 10-minute runtime budget unless official harness behavior proves otherwise.
- [ ] Per-response time is under 30 seconds. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- [ ] Fireworks per-call timeout is configured below the 30-second per-response ceiling.
- [ ] Remote retry policy is disabled/suppressed when the batch deadline is near.
- [ ] Bounded remote worker count is configured and tested.
- [ ] linux/amd64 image built. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- [ ] Image compressed size is under 10GB. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Local image size guard is below the conservative 8GB ceiling before final push.
- [ ] Image is publicly pullable. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.

## Tests and Validation

- [ ] Tests pass.
- [ ] Local quality gate passes: `python3 scripts/run_local_quality_gate.py`.
- [ ] Phase 1 acceptance passes: `python3 scripts/run_phase1_acceptance.py`.
- [ ] Phase 1 Docker acceptance passes before image push: `python3 scripts/run_phase1_acceptance.py --include-docker`.
- [ ] Submission readiness report says `ready_for_live_eval_or_final_submission_prep`: `python3 scripts/submission_readiness_report.py --include-docker`.
- [ ] Eval coverage checker passes: `python3 scripts/check_eval_coverage.py`.
- [ ] Regression tier coverage passes: `python3 scripts/check_eval_coverage.py eval/golden_tier_2_regression.jsonl --profile tier`.
- [ ] Adversarial tier coverage passes: `python3 scripts/check_eval_coverage.py eval/golden_tier_3_adversarial.jsonl --profile tier`.
- [ ] Local fixture test passes.
- [ ] Malformed input tests pass: bad JSON, non-array JSON, missing task fields, non-string prompt.
- [ ] Docker fixture test passes.
- [ ] Docker image architecture and size guard pass.
- [ ] Config/env parsing tests pass for `ROUTER_MODE`, `LOCAL_CONFIDENCE_THRESHOLD`, `FIREWORKS_TIMEOUT_SECONDS`, `FIREWORKS_MAX_RETRIES`, and `ROUTER_LOG_PATH`.
- [ ] Agent test proves classifier runs before any Fireworks call.
- [ ] Agent test proves high-confidence local tasks do not call Fireworks.
- [ ] Agent test proves low-confidence or risky tasks call Fireworks through the wrapper.
- [ ] Risk engine tests cover ambiguity, reasoning depth, format strictness, code risk, factual freshness, and validator weakness.
- [ ] Remote mode tests cover concise, accuracy, format-strict, and code modes where applicable.
- [ ] Router mode tests cover conservative, balanced, and aggressive configurations on the same dataset.
- [ ] Router decision logs include category, confidence, route, selected model, prompt policy, `max_tokens`, route reason, latency, and token usage when available.
- [ ] Router decision logs include risk score, risk components, validator notes, remote mode, final answer length, and errors when present.
- [ ] Answer normalization test passes: no unintended markdown, surrounding whitespace stripped, exact requested formats preserved.
- [ ] Timeout/fallback tests pass without crashing the batch or producing malformed JSON.
- [ ] Deadline manager tests pass: remaining time, safety margin, retry suppression, and valid output near timeout.
- [ ] Fireworks client failure tests pass: missing env, timeout, HTTP error, invalid JSON, missing `choices`, missing `usage`, and disallowed model.
- [ ] Structured routing result tests pass while final `/output/results.json` still contains only `task_id` and `answer`.
- [ ] Optional telemetry test passes and confirms no API key/secret is logged.
- [ ] Production readiness failure matrix reviewed.
- [ ] Always-Fireworks baseline compared against final hybrid router on the same dataset.
- [ ] Candidate eval reports compared against accepted baseline with `scripts/compare_eval_reports.py`.
- [ ] Router config sweep report reviewed and winning config selected.
- [ ] Adversarial routing set passes the configured accuracy target.
- [ ] No tier 3 adversarial scenario is accepted locally without a proof/verifier.
- [ ] New routing features have both positive scenarios and adversarial fail-safe scenarios.
- [ ] Valid JSON output verified manually.
- [ ] Representative output formats manually inspected: exact numeric, label, summary, entity list, code, and corrected code.
- [ ] Latest model matrix and router sweep reports reviewed before Docker push/submission.
- [ ] Weak or wrong outputs recorded in `docs/experiments.md` or `docs/official-submission-log.md`.
- [ ] All 8 Track 1 categories have at least one local test example.
- [ ] No regression after final image build.

## Secrets and Environment

- [ ] No secrets in repo.
- [ ] No `.env` committed.
- [ ] No `.env` bundled in image. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Fireworks env vars handled: `FIREWORKS_API_KEY`, `FIREWORKS_BASE_URL`, `ALLOWED_MODELS`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] All Fireworks calls use `FIREWORKS_BASE_URL`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Chat completions URL is built from `FIREWORKS_BASE_URL`; no direct `https://api.fireworks.ai/...` URL is hardcoded.
- [ ] Allowed model selection validated from `ALLOWED_MODELS`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Current allowed planning models are recognized: `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it-nvfp4`.
- [ ] Local evaluation accuracy threshold is configurable.
- [ ] Submitted image does not require GPU access to run correctly unless organizer guidance confirms GPU access in final evaluation.

## Prohibited Behavior Checks

- [ ] No hardcoded answers.
- [ ] No cached answers.
- [ ] No hardcoded final model IDs.
- [ ] No hardcoded mandatory model choice.
- [ ] No personal Fireworks key in final runtime.
- [ ] No calls to models outside `ALLOWED_MODELS`.
- [ ] No non-English final responses. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.

## lablab Submission Package

- [ ] lablab title ready. Source: `Guides/Submission Guidelines.txt`.
- [ ] Short description ready. Source: `Guides/Submission Guidelines.txt`.
- [ ] Long description ready. Source: `Guides/Submission Guidelines.txt`.
- [ ] Track/category tags ready. Source: `Guides/Submission Guidelines.txt`.
- [ ] Technology tags ready. Source: `Guides/Submission Guidelines.txt`.
- [ ] Cover image ready. Sources: `Guides/Hackathon Act II.txt`, `Guides/Submission Guidelines.txt`.
- [ ] Video plan complete: `docs/video-demo-plan.md`.
- [ ] Video ready. Sources: `Guides/Hackathon Act II.txt`, `Guides/Submission Guidelines.txt`.
- [ ] Slides plan complete: `docs/presentation-plan.md`.
- [ ] Slides ready. Source: `Guides/Hackathon Act II.txt`.
- [ ] Docker image URL ready.
- [ ] Official submission attempt recorded in `docs/official-submission-log.md`.
- [ ] Public GitHub URL ready. Source: `Guides/Hackathon Act II.txt`.
- [ ] Demo platform / application URL ready if required by form. Source: `Guides/Submission Guidelines.txt`.
- [ ] Submit before July 11, 7:00 PM EEST. Source: `Guides/Hackathon Act II.txt`.
- [ ] Respect 10 submissions per hour per team. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

## Presentation and Demo Evidence

- [ ] Architecture flow captured.
- [ ] Runtime contract captured.
- [ ] Local-first routing explanation captured.
- [ ] Model matrix report selected for slides.
- [ ] Token comparison table selected for slides.
- [ ] Failure analysis selected for slides/demo if it strengthens the evidence story.
- [ ] Docker run proof captured.
- [ ] Valid output JSON proof captured.
- [ ] No secrets visible in screenshots or recordings.
