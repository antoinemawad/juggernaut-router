# Architecture

Juggernaut Router is a batch-oriented Track 1 agent. It starts once, reads a JSON task file, writes a JSON results file, then exits.

## Components

| Component | File | Responsibility |
| --- | --- | --- |
| Entrypoint | `app/main.py` | Load tasks, run tasks concurrently, write results, emit startup/finish diagnostics |
| Runtime config | `app/config.py` | Parse environment variables and recommendation exports |
| Classifier | `app/classifier.py` | Categorize prompts and infer answer shape, constraints, and risk components |
| Router | `app/agent.py` | Coordinate deterministic, local-model, Fireworks, validation, fallback, and telemetry paths |
| Deterministic solvers | `app/solvers/basic.py` | Return exact answers for recognized safe prompt patterns |
| Local inference | `app/local_model_client.py`, `app/local_llm.py` | Call optional GGUF model through `llama-cpp-python` or external command |
| Remote inference | `app/fireworks_client.py` | Call Fireworks-compatible chat completions through `FIREWORKS_BASE_URL` |
| Normalization | `app/normalization.py` | Normalize model and solver answers into expected shapes |
| Validation | `app/validators.py` | Accept or reject local/remote answers based on task constraints |
| Telemetry | `app/telemetry.py` | Write optional JSONL route and timing records |

## Request Lifecycle

```mermaid
sequenceDiagram
    participant H as Harness
    participant M as app.main
    participant A as app.agent
    participant C as classifier
    participant S as solver
    participant L as local GGUF
    participant F as Fireworks
    participant V as validator

    H->>M: mount /input/tasks.json
    M->>M: parse and coerce tasks
    loop each task
        M->>A: answer_task(task_id, prompt)
        A->>C: classify_prompt(prompt)
        A->>S: try_basic_solver_structured(prompt)
        A->>V: validate_local_answer(...)
        alt deterministic accepted
            A->>M: local answer
        else local model eligible
            A->>L: generate_local_answer(...)
            A->>V: validate_remote_answer(...)
            alt local model accepted
                A->>M: local_model answer
            else Fireworks available
                A->>F: ask_fireworks_structured(...)
                A->>V: validate_remote_answer(...)
                A->>M: remote or escalated answer
            else no remote available
                A->>M: safe fallback
            end
        else Fireworks available
            A->>F: ask_fireworks_structured(...)
            A->>V: validate_remote_answer(...)
            A->>M: remote or escalated answer
        else
            A->>M: safe fallback
        end
    end
    M->>H: write /output/results.json
```

## Routing Decision Flow

```mermaid
flowchart TD
    A["Prompt"] --> B["classify_prompt"]
    B --> C["try_basic_solver_structured"]
    C --> D{"Local deterministic proof accepted?"}
    D -- yes --> E["Normalize and return route=local"]
    D -- no --> F{"Local model enabled and allowed?"}
    F -- yes --> G["Generate with local GGUF"]
    G --> H{"Validation accepted?"}
    H -- yes --> I["Normalize and return route=local_model"]
    H -- no --> J{"Fireworks env complete?"}
    F -- no --> J
    J -- yes --> K["Remote Fireworks call"]
    K --> L{"Validation/escalation result"}
    L --> M["Normalize and return route=fireworks"]
    J -- no --> N["Safe fallback"]
```

## Deterministic vs Model-Based Execution

Deterministic solvers run first. They are intended for recognized, low-risk prompts where the system can produce and validate an exact answer locally.

Local model execution is optional and controlled by `LOCAL_MODEL_ENABLED`, `LOCAL_MODEL_PATH`, `LOCAL_MODEL_CATEGORIES`, and related local-model variables. Local answers still pass through validation before being accepted.

Remote execution uses `FIREWORKS_BASE_URL`, `FIREWORKS_API_KEY`, and `ALLOWED_MODELS`. Model preferences are configurable, but the client only uses models allowed by the runtime environment.

## Failure Handling

- Invalid or missing input logs an `input_error` event and writes a valid empty result array.
- Missing Fireworks configuration prevents remote calls and uses safe fallback when local paths fail.
- Local model failures record metadata such as error, model path, and validation notes.
- Remote errors can trigger fallback or escalation depending on configuration and deadline.
- Output writing always creates the output directory before writing `results.json`.

## Configuration Loading

`RuntimeConfig.from_env()` reads the process environment and optional `ROUTER_RECOMMENDATION_PATH` exports. Explicit environment variables take precedence over recommendation-file values.

## Output Contract

Output is always an array of objects:

```json
[
  {"task_id": "task-id", "answer": "answer text"}
]
```
