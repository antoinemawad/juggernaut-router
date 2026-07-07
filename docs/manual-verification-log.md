# Manual Verification Log

Purpose: record human inspection before commits, live runs, Docker pushes, and official submissions.

Do not paste secrets or hidden benchmark content.

## Verification Template

- Date/time:
- Verifier:
- Git branch/commit:
- What was checked:
- Commands run:
- Files inspected:
- Representative outputs reviewed:
- Edge cases reviewed:
- Weak/wrong outputs found:
- Action taken:
- Result:
- Ready for next step: yes/no

## Required Manual Checks Before Official Submission

- Inspect `local_test/output/results.json`.
- Confirm every item has only `task_id` and `answer`.
- Confirm answers are English.
- Confirm no accidental markdown/code fences when prompt forbids them.
- Inspect latest model matrix report.
- Inspect latest router sweep report.
- Inspect Docker smoke output.
- Check `git status --short`.
- Check no `.env` or secrets are included.
- Check README commands match actual commands.
- Check final submission fields and URLs.

## Entries

### Entry 1

- Date/time: TBD
- Verifier: TBD
- Git branch/commit: TBD
- What was checked: TBD
- Commands run: TBD
- Files inspected: TBD
- Representative outputs reviewed: TBD
- Edge cases reviewed: TBD
- Weak/wrong outputs found: TBD
- Action taken: TBD
- Result: TBD
- Ready for next step: TBD
