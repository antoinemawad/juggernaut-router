# Requirements Inventory

## Source Files Reviewed

- `Guides/AMD Developer Hackathon Participant Guide.txt`
- `Guides/Hackathon Act II.txt`
- `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`
- `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`
- `Guides/Submission Guidelines.txt`

## FACTS

### Track Name and Objective

- We are choosing Track 1 only. Track 1 is described as `General-Purpose AI Agent` in `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt` and as `Hybrid Token-Efficient Routing Agent` in `Guides/Hackathon Act II.txt`.
- Track 1 asks for an AI agent that handles a wide variety of natural language tasks across multiple capability domains while using Fireworks AI models as efficiently as possible. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- The event page describes Track 1 as an agent that completes tasks autonomously by deciding whether to use a local model or call a remote model via Fireworks AI credits, aiming to pick the cheapest option without falling below the accuracy threshold. Source: `Guides/Hackathon Act II.txt`.

### Scoring Method

- Track 1 scoring has two stages: an accuracy gate, then token-efficiency ranking. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- The accuracy gate is evaluated by an LLM judge against expected intent. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Submissions that pass the accuracy gate are ranked ascending by total tokens recorded by the judging proxy. Fewer tokens ranks higher. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### Accuracy Gate

- Submissions below the accuracy threshold are excluded from the leaderboard. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- The exact threshold value is not present in the reviewed `Guides/` files.
- Planning decision: the exact accuracy threshold must be programmable/configurable in our local evaluation harness so we can update it immediately if organizers publish a value.

### Token Efficiency Ranking

- Token efficiency is the leaderboard ranking criterion after passing the accuracy gate. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Tokens are recorded by the judging proxy. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### 8 Task Categories

Track 1 evaluates across all eight categories. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

1. Factual knowledge: concepts, definitions, and how things work.
2. Mathematical reasoning: multi-step arithmetic, percentages, word problems, projections.
3. Sentiment classification: labelling sentiment and justifying the classification.
4. Text summarisation: condensing passages to a specific format or length constraint.
5. Named entity recognition: extracting and labelling person, organization, location, and date entities.
6. Code debugging: identifying bugs in code snippets and providing corrected implementations.
7. Logical / deductive reasoning: constraint-based puzzles where all conditions must be satisfied.
8. Code generation: writing correct, well-structured functions from a spec.

### Input Path and JSON Format

- The container must read tasks from `/input/tasks.json` on startup. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Track 1 input format is a JSON array of objects with `task_id` and `prompt`, for example `{ "task_id": "t1", "prompt": "..." }`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### Output Path and JSON Format

- The container must write results to `/output/results.json` before exiting. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Track 1 output format is a JSON array of objects with `task_id` and `answer`, for example `{ "task_id": "t1", "answer": "..." }`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- `/output/results.json` must be valid JSON; malformed output scores zero. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### Fireworks Environment Variables

- The harness injects `FIREWORKS_API_KEY`, `FIREWORKS_BASE_URL`, and `ALLOWED_MODELS` at runtime. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- `FIREWORKS_API_KEY` is provided by the harness and should be used instead of a participant-owned key. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- `ALLOWED_MODELS` is a comma-separated list of permitted Fireworks AI model IDs published on launch day. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- The submitted container must read these values purely from environment variables. It must not hardcode values or bundle a `.env` file. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### `FIREWORKS_BASE_URL` Rule

- All Fireworks API calls must go through `FIREWORKS_BASE_URL`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Calls that bypass `FIREWORKS_BASE_URL` will not be recorded and the submission will score zero tokens. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Engineering interpretation: local deterministic logic and local model experimentation are allowed under the Track 1 local-token rule. Whenever the router chooses Fireworks, the request must be sent through `FIREWORKS_BASE_URL` so the judging proxy can record token usage. The final agent treats `FIREWORKS_BASE_URL` as the only valid remote inference base URL and selects models only from `ALLOWED_MODELS`.

### `ALLOWED_MODELS` Rule

- Only models in `ALLOWED_MODELS` are permitted. Calls to other models invalidate the submission. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Model IDs must not be hardcoded; they must be read from `ALLOWED_MODELS` at runtime. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### Allowed Track 1 Models

- `Guides/AMD Developer Hackathon Participant Guide.txt` lists these allowed Track 1 models: `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it-nvfp4`.
- `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt` says the exact permitted model IDs are published through `ALLOWED_MODELS` at runtime.
- Current planning model set: `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it-nvfp4`.
- Enforcement decision: the implementation still validates against the runtime `ALLOWED_MODELS` value because that is the harness-provided rule.

### Local Model / Local Token Rule

- The event page states that all models and tokens used locally count as zero toward the final score. Source: `Guides/Hackathon Act II.txt`.
- The participant guide states that local models and tokens used locally count as zero for the final score. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### Docker Image Requirements

- Track 1 submission is a Docker image pushed to a public registry such as GitHub Container Registry or Docker Hub. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- All submissions must be containerized. Source: `Guides/Hackathon Act II.txt`.
- The image must be publicly pullable at submission time. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.

### linux/amd64 Requirement

- The judging VM runs `linux/amd64`; the image must include a `linux/amd64` manifest or it will fail to pull and score zero. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- On Apple Silicon, the guide recommends `docker buildx build --platform linux/amd64 --tag your-image:latest --push .`. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.

### Image Size Limit

- The compressed image size must not exceed 10GB. Larger images are rejected before pulling. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### Runtime Limits

- Maximum runtime is 10 minutes. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Exit code must be 0 on success and non-zero on failure. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### Startup / Per-Response Limits

- The container must start and be ready within 60 seconds. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.
- Response time per request must be under 30 seconds. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.

### Valid JSON Requirement

- `/output/results.json` must be valid JSON; malformed output scores zero. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### No Hardcoding / Cached Answers

- Exact evaluation inputs are intentionally omitted; the agent must be genuinely capable, not hardcoded to specific answers. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.
- Do not hardcode or cache answers; evaluation uses unseen prompt variants. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

### English-Only Response Requirement

- All responses must be in English. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.

### Public Image Requirement

- Container images must be publicly pullable at submission time. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).pdf`.

### GitHub / README / Submission Package Requirements

- Submit through the lablab.ai platform before the deadline. Source: `Guides/Hackathon Act II.txt`.
- Required submission fields include project title, short description, long description, technology/category tags, cover image, video presentation, slide presentation, public GitHub repository, demo application platform, and application URL. Source: `Guides/Hackathon Act II.txt`.
- The GitHub repository must be public and include a README with setup and usage instructions. Source: `Guides/Hackathon Act II.txt`.
- General lablab submission guidance asks for a submission title, short description, long description, main tracks, technologies, cover image, video presentation, GitHub repository, demo platform, demo URL, and additional information. Source: `Guides/Submission Guidelines.txt`.

### AMD Developer Cloud / AMD AI Notebook Role

- The event page states participants work with AMD AI Developer Cloud, ROCm, and Fireworks AI API in the cloud. Source: `Guides/Hackathon Act II.txt`.
- AMD Developer Cloud provides on-demand access to AMD GPUs for training, fine-tuning, benchmarking, and deploying AI workloads. Source: `Guides/Hackathon Act II.txt`.
- The short participant guide points to GPU access through `https://notebooks.amd.com/hackathon`. Source: `Guides/AMD Developer Hackathon Participant Guide.txt`.
- Track 1 final scoring runs on a standardized environment; participants can develop and test on any hardware. Source: `Guides/Hackathon Act II.txt`.

### Credits / Access Notes

- New AMD AI Developer Program sign-ups can claim $100 in AMD Developer Cloud GPU credits, $50 in Fireworks AI API credits, and one month of DeepLearning.AI Pro. Source: `Guides/Hackathon Act II.txt`.
- The event page states all participants receive $50 in Fireworks AI API credits for the hackathon. Source: `Guides/Hackathon Act II.txt`.
- New-member credits follow a separate 2 to 3 day manual approval process. Source: `Guides/Hackathon Act II.txt`.
- Participants who signed up after July 2 can still join, but hackathon credits are allocated from July 7 onward. Source: `Guides/Hackathon Act II.txt`.

### Native.Builder / NativelyAI Notes

- Native.Builder is listed as a supported technology option. Participants can use Fireworks AI credits inside Builder and use models available through the platform. Source: `Guides/Hackathon Act II.txt`.
- Builder model availability may vary based on Builder configuration and track requirements. Source: `Guides/Hackathon Act II.txt`.
- Participants should confirm model and workflow choices match hackathon track requirements. Source: `Guides/Hackathon Act II.txt`.
- Current decision: do not use Native.Builder in the implementation path for now. Keep it as optional prototyping support only.

### Deadline

- The event page lists the submission deadline as July 11, 7:00 PM EEST. Source: `Guides/Hackathon Act II.txt`.
- The event schedule lists `Jul 11 7:00 PM Eastern European Summer Time` as `End of Submissions!`. Source: `Guides/Hackathon Act II.txt`.

### Submission Rate Limit

- Submissions are rate-limited to 10 per hour per team. Source: `Guides/Participant Guide_ AMD Developer Hackathon (ACT II).txt`.

## ASSUMPTIONS

- The exact accuracy threshold is not shown in the reviewed files; assume it is high enough that aggressive zero-token guessing is dangerous.
- The final hidden benchmark will use the same input/output shape but unseen prompt variants.
- The published allowed-model list is currently clear: `minimax-m3`, `kimi-k2p7-code`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it-nvfp4`.
- `ALLOWED_MODELS` at runtime remains the enforcement source because the harness injects it.
- Native.Builder is useful for prototyping but will not be used for now.
- AMD Developer Cloud / AMD AI Notebooks are useful for validation and evidence, but the final Track 1 Docker container should remain CPU-safe unless local model use is explicitly justified within the standardized environment.

## DECISIONS

- Optimize for the accuracy gate first; token minimization is only valuable after passing the gate.
- Make the local evaluation accuracy threshold configurable so the value can be changed without code refactors.
- Use local deterministic/high-confidence solvers only where failure risk is low.
- Use Fireworks fallback for risky categories, low confidence, schema uncertainty, code tasks, and logic/math uncertainty.
- Read model choices exclusively from `ALLOWED_MODELS`; never hardcode final model IDs.
- Local deterministic logic and local model experimentation are allowed under the Track 1 local-token rule. Whenever the router chooses Fireworks, the request must be sent through `FIREWORKS_BASE_URL` so the judging proxy can record token usage. The final agent treats `FIREWORKS_BASE_URL` as the only valid remote inference base URL and selects models only from `ALLOWED_MODELS`.
- Keep the submitted image small, public, `linux/amd64`, and free of `.env` files or secrets.
- Treat AMD Developer Cloud / AMD AI Notebooks as validation/evidence infrastructure, not a required final runtime path unless confirmed by organizers.
- Do not use Native.Builder for now; revisit only if it clearly helps with prototyping while preserving Track 1 compliance.
- Keep Track 1 docs separate from Track 2 and Track 3 to avoid scope creep.

## OPEN QUESTIONS

- What is the exact accuracy threshold for the Track 1 gate?
- Are prompts evaluated one batch per container run only, or can the harness send multiple request batches to a long-running container?
- Does the 30-second per-response limit apply per task in batch mode, or to any internal request/answer step?
- Are local CPU-only deterministic solvers always allowed?
- Are local LLMs allowed inside the final container if they fit runtime and image-size limits?
- Final evaluator GPU access for local LLM inference inside the submitted Docker container is not confirmed. Therefore, the final image should remain CPU-safe and should not require a GPU to run correctly.
- How is token count recorded for failed Fireworks calls, retries, streaming, or truncated responses?
- Are participants required to use Gemma for partner prize eligibility on Track 1, or merely to use Gemma through Fireworks?
- Is the Docker image URL the only required executable artifact for Track 1, or is a demo URL also required by the lablab form?

## OUT OF SCOPE

- Track 2 Video Captioning is out of scope because we are choosing Track 1 only. It is noted only because the participant guide contains Track 2 requirements.
- Track 3 Unicorn Track is out of scope because we are choosing Track 1 only. It is noted only because the event page and participant guide include Track 3 details.
- Referral prizes, non-Track-1 prize strategy, and startup/product pitch criteria are out of scope for this Track 1 build.
