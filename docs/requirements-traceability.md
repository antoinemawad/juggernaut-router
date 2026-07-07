# Requirements Traceability

Purpose: make every important requirement traceable to source, evidence, owner, status, and verification notes.

Status values: `open`, `in_progress`, `verified`, `blocked`, `not_applicable`.

| Requirement | Source | Evidence Required | Owner | Status | Verification Notes |
| --- | --- | --- | --- | --- | --- |
| Read `/input/tasks.json` on startup | `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt` | Local and Docker run logs showing mounted `/input` | Team | in_progress | Local path override verified; Docker proof pending |
| Write valid `/output/results.json` | `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt` | `scripts/validate_submission_io.py` output | Team | in_progress | Local fixture validator passes |
| Use `FIREWORKS_BASE_URL` for all remote calls | `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt` | Code reference and mocked/live call proof | Team | in_progress | `app/fireworks_client.py` builds URL from env |
| Select only from `ALLOWED_MODELS` | `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt` | Code reference and model matrix logs | Team | in_progress | Eval validates requested models against env/default list |
| No hardcoded or cached answers | `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt` | Code review and scenario diversity | Team | open | Needs final audit |
| Public linux/amd64 Docker image | `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf` | Public image URL and pull/run proof | Team | open | Pending final image |
| Accuracy gate first, token ranking second | `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt` | Experiment reports and final selected config | Team | in_progress | Router sweep ranks accuracy before tokens |
| Local tokens count as zero | `Guides/Hackathon Act II.txt`, participant guide | Architecture docs and local route logs | Team | in_progress | Local deterministic plan documented; runtime logs pending |
| No `.env` committed or bundled | Participant guide | `.gitignore`, `.dockerignore`, final audit | Team | in_progress | Ignore rules present; final audit pending |
| Respect 10 submissions/hour/team | Participant guide | Official submission log | Team | open | Use `docs/official-submission-log.md` |

## Update Rule

When new official guidance appears, add a row here and update `docs/requirements.md` and `docs/submission-checklist.md`.
