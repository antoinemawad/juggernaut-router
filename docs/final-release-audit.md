# Final Release Audit

Purpose: treat the final submission like a release, not a hopeful upload.

No official submission should happen until this audit is complete or a risk is explicitly accepted.

## Release Audit Checklist

### Requirements

- [ ] `docs/requirements.md` reviewed.
- [ ] `docs/requirements-traceability.md` reviewed.
- [ ] All critical requirements have evidence.
- [ ] Open questions do not block Track 1 submission.

### Code and Runtime

- [ ] Fresh clone or clean checkout tested.
- [ ] Local smoke test passes.
- [ ] Output validator passes.
- [ ] Docker build passes.
- [ ] Docker run with mounted `/input` and `/output` passes.
- [ ] `linux/amd64` image built and publicly pullable.
- [ ] Runtime limits checked.

### Experiments and Evidence

- [ ] Eval coverage checker passes.
- [ ] Model matrix report selected.
- [ ] Router config sweep report selected.
- [ ] Always-Fireworks vs hybrid comparison selected.
- [ ] Token usage evidence selected.
- [ ] Failure analysis summarized.
- [ ] Manual verification log updated.

### Security and Compliance

- [ ] No `.env` committed.
- [ ] No secrets in notebooks, screenshots, logs, README, docs, or video.
- [ ] No hardcoded Fireworks API URL.
- [ ] No hardcoded mandatory model.
- [ ] No cached hidden-task answers.
- [ ] Docker image excludes unnecessary local artifacts.

### Submission Package

- [ ] README final results updated.
- [ ] Presentation PDF ready.
- [ ] Demo video ready.
- [ ] Public GitHub URL ready.
- [ ] Docker image URL ready.
- [ ] Official submission log updated.
- [ ] Interview prep reviewed against actual implementation.

## Release Decision

- Release candidate branch:
- Commit SHA:
- Docker image:
- Selected router config:
- Selected model matrix report:
- Selected router sweep report:
- Known risks:
- Decision: submit / hold
- Approver:
