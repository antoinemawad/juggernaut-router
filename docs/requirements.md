# Track 1 Requirements

This checklist is source-backed by the current `Guides/` folder and should be updated whenever those files change.

## Functional Requirements

- [ ] Build Track 1 only: Hybrid Token-Efficient Routing Agent / General-Purpose AI Agent. Sources: `Guides/Hackathon Act II.txt`, `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Handle all 8 task categories: factual knowledge, math reasoning, sentiment classification, summarization, named entity recognition, code debugging, logical/deductive reasoning, and code generation. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Classify each task locally before any Fireworks call.
- [ ] Decide local-vs-Fireworks routing from local classification, local solver confidence, validation, and category risk.
- [ ] Keep safe deterministic/high-confidence tasks local.
- [ ] Call Fireworks only when local classification/validation says remote inference is needed.
- [ ] Read `/input/tasks.json` on startup. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Accept JSON array input items with `task_id` and `prompt`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Write `/output/results.json` before exiting. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Output JSON array items with `task_id` and `answer`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Return English-only answers. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- [ ] Exit with code 0 on success and non-zero on failure. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

## Fireworks / API Requirements

- [ ] Read `FIREWORKS_API_KEY` from the environment. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Read `FIREWORKS_BASE_URL` from the environment. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Route all Fireworks calls through `FIREWORKS_BASE_URL`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Build the chat completions URL from `FIREWORKS_BASE_URL`; never hardcode `https://api.fireworks.ai/...`.
- [ ] Read `ALLOWED_MODELS` from the environment and split it as the runtime-authoritative model list. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Use only models in `ALLOWED_MODELS`; calls to other models invalidate the submission. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Current allowed-model planning set: `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it-nvfp4`. Source: `Guides/AMD Developer Hackathon Participant Guide.txt`.
- [ ] Do not use a personal Fireworks key in the final container; use the harness-provided key. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Allow local deterministic logic and local model experimentation under the local-token rule, but route every remote Fireworks call through `FIREWORKS_BASE_URL`.

## Docker / Runtime Requirements

- [ ] Submit a Docker image pushed to a public registry. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Ensure the image is publicly pullable at submission time. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- [ ] Include a `linux/amd64` manifest. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- [ ] Keep compressed image size at or below 10GB. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Finish within the 10-minute maximum runtime. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Start and be ready within 60 seconds. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- [ ] Keep per-response time under 30 seconds. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- [ ] Build on Apple Silicon with `docker buildx build --platform linux/amd64 ... --push .` if needed. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.

## Scoring Requirements

- [ ] Prioritize passing the LLM-judge accuracy gate. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Keep the local evaluation accuracy threshold programmable/configurable because the exact official threshold is not present in the current `Guides/`.
- [ ] Minimize total tokens recorded by the judging proxy after the accuracy gate is satisfied. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Treat malformed `/output/results.json` as catastrophic because it scores zero. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Treat local tokens as zero-cost for final scoring. Sources: `Guides/Hackathon Act II.txt`, `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Avoid unrecorded Fireworks calls; bypassing `FIREWORKS_BASE_URL` results in zero recorded tokens. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

## Submission Requirements

- [ ] Submit through lablab.ai before the deadline. Source: `Guides/Hackathon Act II.txt`.
- [ ] Deadline: July 11, 7:00 PM EEST. Source: `Guides/Hackathon Act II.txt`.
- [ ] Public GitHub repository. Source: `Guides/Hackathon Act II.txt`.
- [ ] README with setup and usage instructions. Source: `Guides/Hackathon Act II.txt`.
- [ ] Docker image URL. Sources: `Guides/Hackathon Act II.txt`, `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Project title, short description, long description, technology/category tags. Sources: `Guides/Hackathon Act II.txt`, `Guides/Submission Guidelines.txt`.
- [ ] Cover image, video presentation, and slide presentation. Source: `Guides/Hackathon Act II.txt`.
- [ ] Demo application platform and application URL if the lablab submission form requires them. Source: `Guides/Submission Guidelines.txt`.
- [ ] Respect the 10 submissions per hour per team rate limit. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

## Prohibited Behavior

- [ ] Do not hardcode or cache answers. Sources: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`, `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- [ ] Do not commit or bundle `.env` files in the image. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Do not hardcode Fireworks credentials, base URL, or final model IDs. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Do not call models outside `ALLOWED_MODELS`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Do not bypass `FIREWORKS_BASE_URL` for Fireworks calls. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- [ ] Do not require GPU access for the submitted Docker image unless organizer guidance confirms final evaluator GPU availability.
- [ ] Do not submit malformed JSON. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

## Recommended but Non-Blocking Items

- [ ] Use AMD Developer Cloud / AMD AI Notebooks for validation evidence where useful. Sources: `Guides/Hackathon Act II.txt`, `Guides/AMD Developer Hackathon Participant Guide.txt`.
- [ ] Do not use Native.Builder for now; keep it as optional future prototyping support only. Source: `Guides/Hackathon Act II.txt`.
- [ ] Consider Gemma models when they are present in `ALLOWED_MODELS`, especially for partner-prize eligibility. Sources: `Guides/Hackathon Act II.txt`, `Guides/AMD Developer Hackathon Participant Guide.txt`.
- [ ] Keep local evaluation and Docker smoke tests ready before submission attempts because submissions are rate-limited. Sources: `Guides/AMD Developer Hackathon Participant Guide.txt`, `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
