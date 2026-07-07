# Video Demo Plan

Purpose: prepare a concise video that proves Juggernaut Router is compliant, working, and rank-oriented.

Target length: under 5 minutes, matching general lablab guidance in `Guides/Submission Guidelines.txt`.

## Demo Goals

- Show the project solves Track 1 only.
- Show the local-first routing idea.
- Show valid input/output behavior.
- Show Fireworks env handling without revealing secrets.
- Show model-matrix evidence.
- Show Docker readiness.

## Recommended Structure

### 0:00-0:20 - Hook

Say:

> Juggernaut Router is a Track 1 hybrid routing agent. It classifies every task locally first, answers safe tasks without remote tokens, and uses Fireworks only when accuracy risk requires it.

Show:

- repo name,
- Track 1 docs/checklist,
- architecture flow.

### 0:20-1:00 - Problem and Strategy

Say:

> The leaderboard is accuracy-gated first, then ranked by recorded Fireworks tokens. So the goal is not zero tokens at all costs; the goal is the fewest remote tokens among submissions that pass accuracy.

Show:

- `docs/strategy-plan.md`,
- local-first decision policy,
- category strategy table.

### 1:00-1:45 - Runtime Contract

Show:

- `app/main.py`,
- `/input/tasks.json`,
- `/output/results.json`,
- `scripts/validate_submission_io.py`.

Run or show:

```bash
INPUT_PATH=local_test/input/tasks.json \
OUTPUT_PATH=local_test/output/results.json \
python3 -m app.main

python3 scripts/validate_submission_io.py local_test/output/results.json
```

Expected proof:

- `OK: <n> results in local_test/output/results.json`
- output contains only `task_id` and `answer`.

### 1:45-2:30 - Routing Architecture

Show:

- local classifier before Fireworks,
- local solver/validator,
- Fireworks fallback wrapper,
- no direct `https://api.fireworks.ai/...` hardcoding,
- env vars: `FIREWORKS_API_KEY`, `FIREWORKS_BASE_URL`, `ALLOWED_MODELS`.

Do not show real secrets.

### 2:30-3:20 - Model Matrix Evidence

Show:

- `docs/model-matrix-evaluation.md`,
- `eval/model_matrix.py`,
- latest `eval_runs/<run_id>.md`.

Say:

> We test each allowed model against every Track 1 category, log tokens, latency, score, pass/fail, and use that evidence to choose per-category defaults.

Run mock if needed:

```bash
python3 eval/model_matrix.py
```

For final video, prefer showing a real live report if credits and env vars are available.

### 3:20-4:15 - Docker / Submission Readiness

Show:

```bash
docker build -t juggernaut-router:local .

docker run --rm \
  -v "$PWD/local_test/input:/input:ro" \
  -v "$PWD/local_test/output:/output" \
  juggernaut-router:local
```

Then show final build command:

```bash
docker buildx build --platform linux/amd64 \
  --tag <public-registry>/juggernaut-router:latest \
  --push .
```

Mention:

- final image must be public,
- `linux/amd64`,
- no `.env`,
- no secrets,
- no cached answers.

### 4:15-5:00 - Results and Closing

Fill after final experiments:

- always-Fireworks baseline tokens:
- hybrid tokens:
- token reduction:
- accuracy estimate:
- best model/category table:

Say:

> The final router is designed to be boringly compliant and aggressively measured: local-first for token savings, Fireworks fallback for accuracy, and model choice backed by logs.

## Recording Checklist

- [ ] Hide secrets and `.env`.
- [ ] Use large readable terminal font.
- [ ] Keep browser tabs clean.
- [ ] Show repo and docs.
- [ ] Show local smoke test.
- [ ] Show output validation.
- [ ] Show model matrix report.
- [ ] Show Docker command or successful output.
- [ ] Show final GitHub URL.
- [ ] Show final Docker image URL if available.
- [ ] Keep under 5 minutes.

## Assets Needed Before Recording

- Final README.
- Final architecture doc.
- Final model matrix report.
- Final Docker image URL.
- Final GitHub URL.
- Optional cover image.
- Optional slides PDF.

## Demo Risks

- Accidentally showing API keys.
- Spending Fireworks credits during recording.
- Docker daemon not running.
- Terminal output too small.
- Overexplaining implementation details instead of showing compliance/results.
