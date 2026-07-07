# Official Submission Decision Tree

Purpose: use the 10-submissions-per-hour limit as measured feedback, not random probing.

## Before Any Official Submission

Run:

```bash
python3 scripts/run_local_quality_gate.py
```

Then verify Docker build/run and public image pull.

## Attempt Sequence

1. Submit conservative or strict-hybrid baseline.
2. Record official result in `docs/official-submission-log.md`.
3. Change one major variable only.

## If Official Result Fails Accuracy

- Increase router conservatism.
- Route more categories to Fireworks.
- Use `remote_accuracy` for hard math, logic, code, and ambiguous factual tasks.
- Increase `max_tokens` only for failed/truncated categories.
- Inspect format failures before changing models.

## If Official Result Passes Accuracy But Tokens Are High

- Increase safe local coverage only where validators prove correctness.
- Try lower `max_tokens` for verbose categories.
- Try `answer_only` or compact prompt policy only where matrix results show no accuracy loss.
- Try cheaper passing model by category.

## If Official Result Shows Format Problems

- Add/strengthen verifier.
- Use `remote_format_strict`.
- Normalize output.
- Retry once only for fixable format failures.

## If Official Result Shows Runtime/Pull Failure

- Stop submitting.
- Fix Docker, env handling, output shape, or registry pullability locally.
- Re-run local quality gate and Docker smoke before another attempt.

## Logging Rule

Every official attempt should record:

- image tag/digest,
- router config,
- local report paths,
- official pass/fail if shown,
- official token usage if shown,
- one variable changed,
- next decision.
