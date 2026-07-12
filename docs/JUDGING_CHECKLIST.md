# Judging Checklist

## Repository

- [ ] Repository name and project title are correct: Juggernaut Router
- [ ] Working tree is clean before final build
- [ ] No `.env` file is tracked
- [ ] No API keys, tokens, passwords, or private endpoints are committed
- [ ] No GGUF/model weights are committed to Git
- [ ] README links work
- [ ] Documentation references current file paths
- [ ] Final image tag is recorded

## Docker Image

- [ ] Image builds successfully
- [ ] Image is public or accessible to the evaluator
- [ ] Image reference includes a tag
- [ ] Image architecture is `amd64`
- [ ] Image is below the official size limit
- [ ] Container starts without interactive input
- [ ] Container exits after writing output
- [ ] No `.git`, `.env`, docs, tests, notebooks, eval runs, or local scratch files are included in the runtime image

## Track 1 Contract

- [ ] Reads `/input/tasks.json`
- [ ] Writes `/output/results.json`
- [ ] Output is a JSON array
- [ ] Each output item contains `task_id` and `answer`
- [ ] Number of answers equals number of tasks
- [ ] Empty input or invalid input logs a clear error

## Routes

- [ ] Deterministic route works on a known safe task
- [ ] Local-model route works when local model is enabled and bundled
- [ ] Remote route works when `FIREWORKS_API_KEY`, `FIREWORKS_BASE_URL`, and `ALLOWED_MODELS` are set
- [ ] Fallback route works when no model path is available
- [ ] Remote calls use `FIREWORKS_BASE_URL`
- [ ] Remote models are selected from `ALLOWED_MODELS`

## Reliability

- [ ] Timeout behavior is acceptable
- [ ] Retry/escalation behavior is documented
- [ ] Logs do not expose secrets
- [ ] Telemetry can be written to `/output/router_log.jsonl`
- [ ] Docker smoke test passes
- [ ] Unit tests pass
- [ ] Static submission guard passes

## Demo

- [ ] `./scripts/demo.sh` runs successfully
- [ ] `examples/sample_tasks.json` is synthetic
- [ ] Demo output is valid
- [ ] Demo can run without remote credentials
- [ ] Optional remote demo path is documented
- [ ] Video script is ready
- [ ] Presentation notes are ready

## Final Submission

- [ ] Final public image tag selected
- [ ] Public pull test completed from a clean environment
- [ ] Final leaderboard metrics recorded manually
- [ ] Submission metadata copied carefully
- [ ] Last resubmission result checked
