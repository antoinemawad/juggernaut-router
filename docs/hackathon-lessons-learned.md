# Hackathon Lessons Applied

Source: prior HackerRank hackathon retrospective provided by the team.

Purpose: turn prior process mistakes into explicit AMD Track 1 operating rules.

## Operating Rules

### 1. Requirements Become Checklists

Every rule from the challenge guide, rubric, PDF, FAQ, Discord clarification, or organizer message must become a checklist or traceability item.

Applied here:

- `docs/requirements.md`
- `docs/submission-checklist.md`
- `docs/source-notes/requirements-inventory.md`
- `docs/requirements-traceability.md`

### 2. Comparisons Must Be Executed, Measured, and Documented

Planning discussions do not count as comparison evidence.

Applied here:

- `eval/model_matrix.py` for allowed-model and prompt-policy comparisons.
- `eval/router_config_sweep.py` for router configuration comparisons.
- `eval_runs/*.md` reports for showable evidence.
- `docs/experiments.md` for experiment plans and decisions.

### 3. Manual Verification Is Required

Automated test success is not enough before submission.

Applied here:

- `docs/manual-verification-log.md`
- AMD AI Notebook checkpoint pauses before live/submission steps.
- `docs/submission-checklist.md` requires manual output inspection.

### 4. The Submission Must Show the Reasoning

Private chats and hidden reasoning do not count. Important decisions must appear in repo docs, reports, README, slides, or demo script.

Applied here:

- `README.md`
- `docs/elite-routing-plan.md`
- `docs/model-matrix-evaluation.md`
- `docs/presentation-plan.md`
- `docs/video-demo-plan.md`
- `docs/official-submission-log.md`

### 5. Build Evidence, Not Just Functionality

The final submission should prove accuracy, token savings, compliance, and reproducibility.

Applied here:

- local smoke commands,
- output JSON validator,
- model matrix reports,
- router config sweep reports,
- Docker smoke plan,
- official submission log,
- AMD infrastructure proof.

### 6. Reproducibility Is a Product Feature

Judges should be able to understand and reproduce the core flow quickly.

Applied here:

- documented env vars,
- local sample input/output,
- Docker run commands,
- AMD Notebook checkpoint,
- no committed `.env`,
- no hidden local assumptions in final runtime.

### 7. Production Gaps Are Early Work, Not Last-Minute Work

Reliability concerns must be designed before final submission.

Applied here:

- timeout/fallback plan,
- one-retry policy,
- output normalization,
- Fireworks base URL enforcement,
- allowed model validation,
- malformed output checks,
- failure taxonomy.

### 8. README Is Part of the Product

The README must explain and prove the solution quickly.

Applied here:

- runtime contract,
- smoke tests,
- Docker build/run,
- config sweep,
- submission docs,
- AMD proof.

Before final submission, README should include final results and links to selected reports.

### 9. Interview Answers Must Match Implementation

Do not overclaim planned features. Distinguish implemented, planned, and tested.

Applied here:

- `docs/judge-interview-prep.md`
- final audit requires checking claims against code.

### 10. Token, Cost, and Latency Are Competitive Evidence

Efficiency claims must be numeric.

Applied here:

- model matrix logs token usage and latency,
- router sweep compares token estimates and local route rate,
- final slides must show always-Fireworks vs hybrid comparison.

### 11. Final Submission Is a Release

No submission should happen on confidence alone.

Applied here:

- `docs/final-release-audit.md`
- `docs/submission-checklist.md`
- `docs/official-submission-log.md`

Final rule: submit based on verified evidence, not confidence.
