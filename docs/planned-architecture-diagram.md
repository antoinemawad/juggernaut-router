# Planned Architecture Diagram

Purpose: provide a reviewable picture of the intended Track 1 runtime before implementation. The design goal is to maximize accuracy first, then minimize recorded Fireworks tokens.

## End-to-End Runtime

```mermaid
%%{init: {"flowchart": {"htmlLabels": true}, "themeVariables": {"fontSize": "16px"}}}%%
flowchart TD
    H[Judging Harness] -->|mounts /input/tasks.json| M[app/main.py]
    M --> CFG[app/config.py]
    M --> D[app/deadline.py<br/>10 min batch budget<br/>60s safety margin]
    M --> IV[Input Validation<br/>JSON array + task_id + prompt]
    IV -->|usable task| A[app/agent.py<br/>routing coordinator]
    IV -->|malformed task| F1[Safe fallback answer<br/>continue batch]

    A --> C[app/classifier.py<br/>local only]
    C --> RISK[Risk Engine<br/>category + confidence + answer shape<br/>ambiguity + reasoning depth<br/>format strictness + code risk<br/>factual freshness + validator weakness]

    RISK --> LS[Local Solver Registry<br/>math, sentiment, simple NER,<br/>simple logic, tiny templates]
    LS --> SR[Structured Solver Result<br/>answer + confidence + evidence<br/>failure reason + needs_fireworks]
    SR --> V[app/validators.py<br/>category-specific checks]

    V --> RD{Route Decision}
    RD -->|proved safe| LOCAL[Local answer<br/>zero recorded Fireworks tokens]
    RD -->|risky / unsupported / low confidence / invalid| RM[Remote Mode Selection<br/>concise / accuracy / format_strict / code]

    RM --> DC{Deadline permits<br/>remote call or retry?}
    DC -->|no| F2[Best validated fallback<br/>skip retry / preserve output]
    DC -->|yes| FW[app/fireworks_client.py]

    FW --> ENV[Runtime env only<br/>FIREWORKS_API_KEY<br/>FIREWORKS_BASE_URL<br/>ALLOWED_MODELS]
    ENV --> URL[Build URL from FIREWORKS_BASE_URL<br/>/chat/completions]
    ENV --> MODEL[Select only from ALLOWED_MODELS<br/>category/model map]
    URL --> CALL[Fireworks judging proxy call<br/>bounded timeout below 30s]
    MODEL --> CALL

    CALL --> RV[Remote Output Verifier<br/>format + syntax + answer-shape checks]
    RV -->|fixable format failure and retry allowed| RM
    RV -->|accepted| N[app/normalization.py]
    LOCAL --> N
    F1 --> N
    F2 --> N

    N --> OUT[Official result object<br/>task_id + answer only]
    OUT --> W[Write /output/results.json<br/>valid JSON array]
    W --> H

    A -. optional .-> T[app/telemetry.py JSONL<br/>route, risk, model, tokens,<br/>latency, validator notes, deadline decisions<br/>no secrets]
    FW -. optional .-> T
    D -. optional .-> T
```

## Component Responsibilities

| Component | Responsibility | Must Not Do |
| --- | --- | --- |
| `app/main.py` | Read official input, validate tasks, call agent, write official output. | Crash whole batch on one bad task or write extra fields to `/output/results.json`. |
| `app/config.py` | Load runtime config from environment with safe defaults. | Require `.env` in final container or log secrets. |
| `app/deadline.py` | Track 10-minute batch budget, safety margin, retry eligibility, and remaining remote-call time. | Sleep, block, or rely on real-time waits in tests. |
| `app/classifier.py` | Classify locally before any Fireworks call. Extract category, confidence, answer shape, constraints, and risks. | Call Fireworks or make final answers directly. |
| `app/solvers/*` | Produce high-confidence local answers with evidence when deterministic. | Guess when confidence or validation is weak. |
| `app/validators.py` | Prove local answers and check remote outputs by category/format. | Accept unverifiable local answers for risky tasks. |
| `app/agent.py` | Own route decision, remote mode choice, deadline checks, retries, and structured result. | Route directly to Fireworks before local classification. |
| `app/fireworks_client.py` | Call Fireworks through injected `FIREWORKS_BASE_URL`, using only `ALLOWED_MODELS`. | Hardcode `https://api.fireworks.ai/...`, bundle keys, or force a fixed model. |
| `app/normalization.py` | Convert final answer to a valid concise string while preserving requested format. | Add metadata to official output. |
| `app/telemetry.py` | Write optional JSONL decision logs for eval/debug/demo evidence. | Leak API keys or change official output. |

## Route Decision Logic

```mermaid
flowchart TD
    P[Prompt] --> C[Local classification]
    C --> S{Supported category<br/>and confident?}
    S -->|no| RF[Route Fireworks]
    S -->|yes| X[Extract constraints<br/>answer shape + format rules]
    X --> R{Risk acceptable<br/>for router mode?}
    R -->|no| RF
    R -->|yes| L[Try local solver]
    L --> E{Evidence strong?}
    E -->|no| RF
    E -->|yes| V{Independent validator<br/>proves answer?}
    V -->|no| RF
    V -->|yes| F{Format validator<br/>passes after normalization?}
    F -->|no| RF
    F -->|yes| T{Trap guard clear?<br/>sarcasm, ambiguity, current facts,<br/>multi-step, nontrivial code}
    T -->|no| RF
    T -->|yes| K{Cheap cross-check passes<br/>inside local proof budget?}
    K -->|no| RF
    K -->|yes| LA[Accept local answer]
    RF --> M[Choose remote mode + model]
    M --> D{Deadline allows call?}
    D -->|yes| RA[Remote answer + verify]
    D -->|no| FB[Safe fallback]
```

Local acceptance requires all of these to pass:

- category confidence,
- solver confidence,
- risk threshold for selected router mode,
- category validator,
- output-format validator,
- trap guard,
- cheap independent cross-check,
- local proof time budget,
- deadline-safe execution path.

## Remote Call Compliance

```mermaid
flowchart LR
    A[Agent remote request] --> B[Allowed model resolver]
    B --> C{model in ALLOWED_MODELS?}
    C -->|no| D[Try next allowed model<br/>or fallback]
    C -->|yes| E[Build base URL from FIREWORKS_BASE_URL]
    E --> F[POST /chat/completions]
    F --> G[Parse choices + usage]
    G --> H[Verify output]
    H --> I[Return structured remote result]
```

Compliance invariants:

- `FIREWORKS_BASE_URL` is the only valid remote inference base URL.
- `ALLOWED_MODELS` is the only model source.
- `FIREWORKS_API_KEY` is read from environment only.
- Missing env, timeout, HTTP error, invalid JSON, missing `choices`, missing `usage`, and disallowed model are handled without crashing the batch.

## Deadline and Concurrency

```mermaid
flowchart TD
    START[Container start] --> TIMER[Start monotonic timer]
    TIMER --> READ[Read and validate tasks]
    READ --> CLASSIFY[Classify tasks locally]
    CLASSIFY --> SPLIT{Route type}
    SPLIT -->|local safe| LOCAL[Answer immediately]
    SPLIT -->|remote needed| QUEUE[Bounded remote queue]
    QUEUE --> WORKERS[REMOTE_WORKER_COUNT workers]
    WORKERS --> BUDGET{remaining time > safety margin<br/>and per-call timeout available?}
    BUDGET -->|yes| REMOTE[Fireworks call]
    BUDGET -->|no| SKIP[Skip retry / fallback]
    REMOTE --> VERIFY[Verify answer]
    VERIFY --> WRITE[Normalize and write output]
    LOCAL --> WRITE
    SKIP --> WRITE
```

Deadline defaults should be conservative:

- `BATCH_DEADLINE_SECONDS=600`
- `DEADLINE_SAFETY_MARGIN_SECONDS=60`
- `FIREWORKS_TIMEOUT_SECONDS` below 30 seconds
- small `REMOTE_WORKER_COUNT`, tuned by tests
- retries only when time remains after safety margin

## Eval Feedback Loop

```mermaid
flowchart TD
    PLAN[Architecture + category playbooks] --> DATA[Golden eval tiers<br/>smoke + regression + adversarial + core matrix]
    DATA --> SWEEP[Router config sweep<br/>conservative / balanced / aggressive]
    DATA --> MATRIX[Model matrix<br/>allowed models + prompt policies]
    SWEEP --> REPORTS[JSONL + markdown reports]
    MATRIX --> REPORTS
    REPORTS --> COMPARE[scripts/compare_eval_reports.py]
    COMPARE --> DECIDE{Accuracy gate first<br/>tokens second}
    DECIDE -->|promote| CONFIG[Update router config defaults]
    DECIDE -->|fail| FIX[Classifier / validator / prompt / model-map fix]
    FIX --> DATA
    CONFIG --> SUBMIT[Official submission candidate]
    SUBMIT --> LOG[docs/official-submission-log.md]
    LOG --> DECIDE
```

## Main Assessment Questions

Use this list when reviewing whether the architecture is strong enough:

- Does every task get classified locally before Fireworks?
- Are local answers accepted only when there is proof or a strong validator?
- Are hard categories remote by default until tests justify local handling?
- Does every Fireworks call go through `FIREWORKS_BASE_URL`?
- Does model selection come only from `ALLOWED_MODELS`?
- Can one bad task, timeout, or malformed remote response fail the whole batch?
- Can the system write valid output before the 10-minute limit?
- Are route decisions logged well enough to debug failures?
- Do tests cover safe local, risky remote, adversarial, and exact-format cases?
- Can official submission results be traced back to a commit, config, and eval report?
