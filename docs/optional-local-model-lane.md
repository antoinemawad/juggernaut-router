# Optional Local Model Lane

Purpose: preserve the local-LLM idea as a future experiment without making the current CPU-safe runtime depend on it.

## Decision

Do not add a local generative model to the default final container yet.

Keep local model inference as an optional third lane:

```text
deterministic local solver
-> optional local model verifier/specialist when enabled
-> Fireworks through FIREWORKS_BASE_URL when uncertainty remains
```

The current submitted runtime should remain CPU-safe, small, fast to start, and correct without GPU access.

## Candidate Models

Preferred first experiment:

- `Qwen/Qwen3-0.6B` quantized GGUF through `llama.cpp`

Backup candidates:

- `HuggingFaceTB/SmolLM2-360M-Instruct` for cheaper classification/verifier experiments.
- `Qwen/Qwen2.5-0.5B-Instruct` as a conservative small Qwen fallback.
- `google/gemma-3-1b-it` only if license/access, image size, and runtime are proven acceptable.

Avoid larger local models until a smaller model fails and the runtime/image budget has clear slack.

## Intended Role

Use a local model first as a verifier or specialist, not as an unconditional answer authority.

Good first tasks:

- classify whether a prompt is ambiguous,
- decide whether a local deterministic answer is safe,
- check whether an answer obeys exact format constraints,
- verify sentiment edge cases,
- check named-entity label coverage,
- recommend local vs Fireworks route.

Avoid at first:

- current factual questions,
- nontrivial code generation/debugging,
- multi-step math where deterministic code or Fireworks is safer,
- anything that requires high trust without independent validation.

## Promotion Gates

A local model can move from experiment to runtime candidate only if it passes all gates:

- CPU-safe in `linux/amd64`.
- Does not require GPU access.
- Keeps compressed image under the final 10GB limit with large margin.
- Keeps startup under the 60-second startup sub-budget.
- Keeps full batch runtime under the 10-minute wall-clock budget.
- Improves measured Fireworks token use without lowering pass rate.
- Never changes official output schema.
- Can be disabled by environment variable.
- Fails closed to Fireworks or safe fallback.
- Has local quality-gate tests and eval reports.

## Proposed Environment Flags

```text
LOCAL_MODEL_ENABLED=false
LOCAL_MODEL_MODE=verifier
LOCAL_MODEL_PATH=/models/qwen3-0.6b-q4.gguf
LOCAL_MODEL_TIMEOUT_MS=750
LOCAL_MODEL_MAX_TOKENS=32
LOCAL_MODEL_MIN_CONFIDENCE=0.90
```

The default remains disabled.

## Required Tests Before Implementation

- Unit tests for disabled mode preserving current behavior.
- Unit tests for timeout/failure falling back to Fireworks.
- Unit tests that local-model decisions never bypass local proof gates.
- Eval scenarios measuring local-model route recommendation accuracy.
- Docker image size check with the model included.
- Docker startup/runtime check on `linux/amd64`.
- Comparison report: deterministic-only vs deterministic-plus-local-model vs Fireworks.

## Open Questions

- Whether final evaluator GPU access exists.
- Whether local model files are allowed in the final image if the image stays under size limits.
- Whether a tiny model's accuracy gain is worth the startup/runtime/image complexity.
- Whether the official hidden benchmark contains enough locally solvable semantic tasks to justify the lane.
