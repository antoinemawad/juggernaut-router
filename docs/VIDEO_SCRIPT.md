# Video Walkthrough Script

Target length: three to five minutes.

## Opening

"This is Juggernaut Router, a hybrid routing agent for the AMD Developer Hackathon Track 1. Instead of sending every task directly to the same remote model, it classifies the task and chooses the cheapest reliable path available."

## Problem

"The challenge is accuracy first, then efficiency. Some tasks are simple enough for deterministic code, some can use a local model, and some need remote Fireworks models. A good agent needs to know the difference."

## Architecture Walkthrough

"The container reads from `/input/tasks.json` and writes to `/output/results.json`. Inside the app, `app/main.py` loads tasks, `app/classifier.py` identifies the category, and `app/agent.py` coordinates the route."

"The route order is deterministic solver first, optional local GGUF model second, and Fireworks fallback when remote inference is configured and needed. Every answer is normalized and validated before it is written."

Show:

```bash
tree -L 2 app scripts docs examples
```

## Terminal Demo

Run:

```bash
./scripts/demo.sh
```

Then show:

```bash
cat /tmp/juggernaut-demo-output/results.json
```

## Route Selection Explanation

"For a simple sentiment task, the system can often answer locally. For a code or reasoning task, it may use a deterministic template if the pattern is recognized. When a task is ambiguous or risky and Fireworks is configured, it falls back to the allowed remote models through the injected base URL."

Show telemetry:

```bash
cat /tmp/juggernaut-demo-output/router_log.jsonl
```

## Output Demonstration

"The output is the exact format required by the evaluator: an array of task IDs and answers. The schema validator confirms that before submission."

Show:

```bash
python3 scripts/validate_submission_io.py /tmp/juggernaut-demo-output/results.json
```

## Closing

"Juggernaut Router is designed to be practical: classify the work, answer safe tasks locally, use remote models when quality matters, and keep the submission Docker image reproducible and AMD64-compatible."

## Safety Notes

Do not show:

- Real API keys
- `.env` contents
- Private evaluator inputs
- Hidden benchmark content
