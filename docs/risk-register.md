# Risk Register

Purpose: keep the biggest Track 1 failure modes visible and tied to mitigation.

| Risk | Impact | Likelihood | Mitigation | Evidence / Check |
| --- | --- | --- | --- | --- |
| Hidden benchmark differs from local fixtures | Accuracy gate failure | High | Expand adversarial scenarios; avoid hardcoded answers; prefer conservative routing for uncertainty | `eval/model_matrix_scenarios.jsonl`, `docs/test-eval-coverage-plan.md` |
| Over-local routing returns wrong zero-token answers | Accuracy gate failure | High | Require local proof and validators; route uncertainty to Fireworks | Phase 2 in `docs/implementation-phases.md` |
| Malformed `/output/results.json` | Zero score | Medium | Output validator, normalization, production-safe main loop | `scripts/validate_submission_io.py` |
| Fireworks call bypasses judging proxy | Invalid/zero-token scoring issue | Low/Medium | Use only `FIREWORKS_BASE_URL`; no hardcoded normal API URL | `app/fireworks_client.py`, code review |
| Model outside `ALLOWED_MODELS` | Invalid submission | Medium | Runtime allowed-model validation | Fireworks client tests |
| Docker image lacks linux/amd64 manifest | Pull failure / zero score | Medium | Build with `--platform linux/amd64`; verify public pull | Docker smoke before submission |
| Fireworks timeout or invalid response crashes batch | Malformed/missing output | Medium | Bounded timeout, one retry, safe fallback | Production readiness failure matrix |
| `max_tokens` too low | Truncated/wrong answers | Medium | Per-category max-token tuning; failure taxonomy | model matrix reports |
| Prompt compaction loses constraints | Wrong format/answer | Medium | Prompt policy matrix; preserve original when exact wording matters | `eval/model_matrix.py --prompt-policies all` |
| Secrets or `.env` included | Security/compliance failure | Low/Medium | `.gitignore`, `.dockerignore`, final review | `git status`, Docker context review |
| Official submissions wasted randomly | Lost optimization opportunity | Medium | One-variable submission decision tree | `docs/official-submission-log.md` |
| Planning outpaces implementation | Runtime underpowered | High | Follow implementation phases and MVP cutoff | `docs/implementation-phases.md` |
| Gemma forced where it is not cheapest-sufficient | Accuracy or token efficiency loss | Medium | Treat Gemma as a strategic default candidate only where Phase 3 evidence supports it; log skip/escalation cases | `docs/model-matrix-evaluation.md`, `docs/strategy-plan.md` |
| Optional local inference changes final answers or routes incorrectly | Accuracy gate failure despite zero local tokens | Medium/High | Keep disabled by default; test route suggester, format checker, and final answer generator separately before promotion | `docs/optional-local-model-lane.md` |
| Optional local model increases image/startup/runtime risk | Timeout or pull failure despite zero local tokens | Medium | Keep disabled by default; require CPU-safe, image-size, startup, runtime, and accuracy gates before promotion | `docs/optional-local-model-lane.md` |

## Update Rule

When a new failure appears in local eval, Docker, live Fireworks, or official submission, add or update a risk row before trying the next submission.
