# Submission Checklist

Final pre-submit checklist for Track 1 only.

## Repository and Documentation

- [ ] Repo is public. Source: `Guides/Hackathon Act II.txt`.
- [ ] README is complete with setup and usage instructions. Source: `Guides/Hackathon Act II.txt`.
- [ ] README documents local test commands.
- [ ] README documents Docker run with mounted `/input` and `/output`.
- [ ] README documents required environment variables.
- [ ] Local testing and submission use the same code path; only `INPUT_PATH`, `OUTPUT_PATH`, and runtime environment variables change.
- [ ] Final manual review complete.

## Docker and Runtime

- [ ] Dockerfile builds successfully.
- [ ] Docker run works with mounted `/input` and `/output`.
- [ ] Container reads `/input/tasks.json` on startup. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Container writes `/output/results.json` before exiting. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Output is valid JSON. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Exit code is 0 on success. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Runtime stays under 10 minutes. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Startup is under 60 seconds. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- [ ] Per-response time is under 30 seconds. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- [ ] linux/amd64 image built. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- [ ] Image compressed size is under 10GB. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Image is publicly pullable. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.

## Tests and Validation

- [ ] Tests pass.
- [ ] Local fixture test passes.
- [ ] Docker fixture test passes.
- [ ] Valid JSON output verified manually.
- [ ] All 8 Track 1 categories have at least one local test example.
- [ ] No regression after final image build.

## Secrets and Environment

- [ ] No secrets in repo.
- [ ] No `.env` committed.
- [ ] No `.env` bundled in image. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Fireworks env vars handled: `FIREWORKS_API_KEY`, `FIREWORKS_BASE_URL`, `ALLOWED_MODELS`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] All Fireworks calls use `FIREWORKS_BASE_URL`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Chat completions URL is built from `FIREWORKS_BASE_URL`; no direct `https://api.fireworks.ai/...` URL is hardcoded.
- [ ] Allowed model selection validated from `ALLOWED_MODELS`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Current allowed planning models are recognized: `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it-nvfp4`.
- [ ] Local evaluation accuracy threshold is configurable.
- [ ] Submitted image does not require GPU access to run correctly unless organizer guidance confirms GPU access in final evaluation.

## Prohibited Behavior Checks

- [ ] No hardcoded answers.
- [ ] No cached answers.
- [ ] No hardcoded final model IDs.
- [ ] No hardcoded mandatory model choice.
- [ ] No personal Fireworks key in final runtime.
- [ ] No calls to models outside `ALLOWED_MODELS`.
- [ ] No non-English final responses. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.

## lablab Submission Package

- [ ] lablab title ready. Source: `Guides/Submission Guidelines.txt`.
- [ ] Short description ready. Source: `Guides/Submission Guidelines.txt`.
- [ ] Long description ready. Source: `Guides/Submission Guidelines.txt`.
- [ ] Track/category tags ready. Source: `Guides/Submission Guidelines.txt`.
- [ ] Technology tags ready. Source: `Guides/Submission Guidelines.txt`.
- [ ] Cover image ready. Sources: `Guides/Hackathon Act II.txt`, `Guides/Submission Guidelines.txt`.
- [ ] Video ready. Sources: `Guides/Hackathon Act II.txt`, `Guides/Submission Guidelines.txt`.
- [ ] Slides ready. Source: `Guides/Hackathon Act II.txt`.
- [ ] Docker image URL ready.
- [ ] Public GitHub URL ready. Source: `Guides/Hackathon Act II.txt`.
- [ ] Demo platform / application URL ready if required by form. Source: `Guides/Submission Guidelines.txt`.
- [ ] Submit before July 11, 7:00 PM EEST. Source: `Guides/Hackathon Act II.txt`.
- [ ] Respect 10 submissions per hour per team. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
