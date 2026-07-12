# Presentation Plan

Purpose: prepare the final slide deck and submission story while engineering work continues.

## Core Story

Juggernaut Router is a Track 1 hybrid routing agent that classifies every task locally first, solves safe deterministic tasks locally, and spends Fireworks tokens only when accuracy risk justifies it.

The message should be:

1. Accuracy gate first.
2. Token efficiency second.
3. Local-first routing prevents waste.
4. Model-matrix evidence chooses the best Fireworks model per category.
5. The final container is compliant, reproducible, and easy for judges to inspect.

## Audience

- Hackathon judges.
- AMD / Fireworks / NativelyAI reviewers.
- Technical evaluators checking Docker, logs, and repo quality.

## Slide Outline

### 1. Title

- Project name: Juggernaut Router.
- Track: Track 1, Hybrid Token-Efficient Routing Agent.
- One-line claim: local-first classification plus evidence-based Fireworks fallback.

### 2. Problem

- Track 1 rewards accuracy first, then lowest recorded token usage.
- Calling Fireworks for every task is accurate but expensive.
- Answering locally for everything is cheap but risks failing the accuracy gate.

### 3. Solution

- Local classifier first.
- Deterministic local solvers for safe tasks.
- Validator/confidence gate.
- Fireworks fallback only when needed.
- Per-category model choice from logged experiments.

### 4. Architecture

Use the flow from `docs/ARCHITECTURE.md`:

`/input/tasks.json -> main.py -> agent.py -> local classifier -> local solver/validator -> route decision -> Fireworks fallback only if needed -> /output/results.json`

Show:

- no hardcoded answers,
- no hardcoded Fireworks URL,
- environment-driven model selection,
- valid JSON output.

### 5. Compliance

Checklist items to mention:

- reads `/input/tasks.json`,
- writes `/output/results.json`,
- valid JSON,
- `linux/amd64`,
- public Docker image,
- all Fireworks calls through `FIREWORKS_BASE_URL`,
- only `ALLOWED_MODELS`,
- no secrets or `.env` in image.

### 6. Model Matrix Evidence

Use final table from `eval_runs/<run_id>.md`.

Show:

- best model by category,
- cheapest passing model by category,
- token and accuracy tradeoffs,
- why final router defaults were chosen.

### 7. Local Solver Coverage

Show which categories can stay local safely:

- clear arithmetic,
- simple sentiment,
- obvious NER,
- simple logic,
- tiny deterministic code templates if validated.

Also show which categories default to Fireworks:

- factual knowledge,
- summarization with constraints,
- code debugging,
- code generation,
- complex logic,
- hard math.

### 8. Results

Fill after experiments:

- always-Fireworks baseline accuracy/tokens,
- hybrid accuracy/tokens,
- token reduction,
- local-only success rate,
- failure categories,
- Docker runtime metrics.

### 9. Demo

Use the exact demo-video flow in `docs/video-demo-plan.md`.

### 10. Closing

- Why it should rank high: accuracy-safe, token-aware, compliant, measured.
- What is novel: local-first route decision plus model/category evidence.

## Required Evidence Assets

- Screenshot or snippet of valid `/output/results.json`.
- Screenshot or snippet of model matrix report.
- Docker build/pull/run command output.
- Token comparison table.
- Failure analysis summary if it helps explain a router improvement.
- Architecture diagram or text flow.
- Public GitHub URL.
- Public Docker image URL.

## Slide Production Checklist

- [ ] Title slide ready.
- [ ] Problem slide ready.
- [ ] Architecture slide ready.
- [ ] Compliance slide ready.
- [ ] Model matrix evidence slide ready.
- [ ] Results slide ready.
- [ ] Demo slide ready.
- [ ] Final URLs slide ready.
- [ ] Export PDF.
- [ ] Confirm file accepted by lablab submission form.

## Open Content Slots

- Final Docker image URL:
- Final GitHub URL:
- Final model matrix run ID:
- Final token reduction:
- Final accuracy estimate:
- Final demo video URL:
