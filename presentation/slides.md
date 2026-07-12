# Juggernaut Router

Hybrid routing agent for AMD Developer Hackathon Track 1.

- Accuracy-first task routing across eight categories
- Deterministic answers when the pattern is safe
- Optional local GGUF inference
- Fireworks fallback through the injected base URL

---

# The Problem

Sending every task to the same remote model is simple, but inefficient.

- Easy tasks waste tokens
- Hard tasks need stronger models
- Model output still needs validation
- The evaluator requires exact `/input` and `/output` behavior

---

# The Solution

Juggernaut Router classifies each task, chooses a route, validates the answer, and writes evaluator-compatible JSON.

Route order:

1. Deterministic solver
2. Optional local model
3. Fireworks model fallback
4. Safe fallback only when no model route is available

---

# Track 1 Coverage

The router supports all eight required categories.

- Factual knowledge
- Mathematical reasoning
- Sentiment classification
- Text summarisation
- Named entity recognition
- Code debugging
- Logical reasoning
- Code generation

---

# Reliability

Accuracy comes from routing plus validation.

- Strict numeric and label normalization
- Code-shape validation
- Repetition and malformed-answer rejection
- Startup and finish logs for evaluator diagnostics
- Optional per-task telemetry for route analysis

---

# Efficiency

The system optimizes tokens after correctness is protected.

- Avoid remote calls for locally safe tasks
- Use category-specific model and prompt policies
- Keep Fireworks as the quality path for risky tasks
- Keep Docker reproducible and linux/amd64 compatible

---

# Demo Flow

1. Build the Docker image
2. Run synthetic sample tasks
3. Validate `results.json`
4. Inspect route logs
5. Show the Cloudflare Worker demo page

---

# Closing

Juggernaut Router is practical: classify the work, answer safe tasks cheaply, reserve stronger models for risky work, and validate everything before returning it.
