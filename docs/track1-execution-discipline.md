# Track 1 Execution Discipline

Purpose: apply only the prior hackathon lessons that directly improve AMD Track 1 score, reproducibility, and submission quality.

## Rules We Keep

### Requirements Become Evidence

Every critical Track 1 rule must have a source and verification path.

Use:

- `docs/requirements.md`
- `docs/source-notes/requirements-inventory.md`
- `docs/submission-checklist.md`

Do not mark a requirement complete unless there is command output, code reference, report, or manual inspection evidence.

### Comparisons Must Be Measured

Planning alternatives does not count. Model, prompt, threshold, and router-mode choices must come from executed comparisons.

Use:

- `eval/model_matrix.py`
- `eval/router_config_sweep.py`
- `eval_runs/*.md`
- `docs/experiments.md`
- `docs/official-submission-log.md`

Final choices should cite the latest selected reports.

### Manual Verification Is Required

Before Docker push or official submission, manually inspect representative outputs and failure cases.

Minimum manual checks:

- `local_test/output/results.json` is valid and contains only `task_id` and `answer`.
- Answers respect requested format: no extra markdown, no explanations when forbidden, code-only when requested.
- Latest model matrix and router sweep reports are reviewed.
- Weak/wrong outputs are noted in `docs/experiments.md` or `docs/official-submission-log.md`.
- README commands match commands that actually ran.

### Evidence Beats Confidence

The final submission should show:

- valid IO,
- Docker readiness,
- model/prompt comparison,
- always-Fireworks vs hybrid comparison,
- token/latency/accuracy tradeoffs,
- failure analysis,
- official submission attempt notes.

### Reproducibility Is Mandatory

Before final submission:

- run local smoke test,
- run eval coverage checker,
- run router config sweep,
- run model matrix mock or selected live slice,
- build and run Docker with mounted `/input` and `/output`,
- confirm no secrets or `.env` files are committed or bundled.

## What We Do Not Need From Prior Hackathon Lessons

- No separate interview-prep process unless the final event explicitly requires it.
- No heavyweight generic project-management docs.
- No process document that does not affect score, reproducibility, evidence, or submission quality.

## Final Rule

Do not submit based on confidence. Submit based on verified evidence.
