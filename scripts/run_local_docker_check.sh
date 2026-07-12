#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-juggernaut-router:local-model}"
INPUT_DIR="${INPUT_DIR:-$(pwd)/local_test/accuracy_gate_input}"
OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)/local_test/output/local_model_check}"
MIN_FIXTURE_PASS_RATE="${MIN_FIXTURE_PASS_RATE:-0}"

mkdir -p "$OUTPUT_DIR"
rm -f "$OUTPUT_DIR/results.json" "$OUTPUT_DIR/router_log.jsonl"

docker_env_args=(
  -e LOCAL_MODEL_ENABLED="${LOCAL_MODEL_ENABLED:-true}"
  -e LOCAL_MODEL_PATH="${LOCAL_MODEL_PATH:-/app/models/local-model.gguf}"
  -e ROUTER_PROFILE="${ROUTER_PROFILE:-accuracy_gate}"
  -e ROUTER_LOG_PATH=/output/router_log.jsonl
)

for name in \
  FIREWORKS_API_KEY \
  FIREWORKS_BASE_URL \
  ALLOWED_MODELS \
  FIREWORKS_DISABLE_MAX_TOKENS \
  FIREWORKS_MAX_TOKENS \
  FIREWORKS_MAX_TOKENS_BY_CATEGORY \
  FIREWORKS_TIMEOUT_SECONDS \
  FIREWORKS_MAX_RETRIES \
  FIREWORKS_DEV_MODEL_MAP \
  LOCAL_MODEL_CATEGORIES \
  LOCAL_MODEL_PATH_BY_CATEGORY \
  REMOTE_VALIDATION_ESCALATION_ENABLED \
  ROUTER_MODE \
  ROUTER_MODELS_BY_CATEGORY \
  ROUTER_MODELS_REMOTE_ACCURACY \
  ROUTER_MODELS_REMOTE_CODE \
  ROUTER_MODELS_REMOTE_CONCISE \
  ROUTER_MODELS_REMOTE_ESCALATION \
  ROUTER_MODELS_REMOTE_FORMAT_STRICT \
  ROUTER_PROMPT_POLICY_BY_CATEGORY \
  ROUTER_PROMPT_POLICY_REMOTE_ACCURACY \
  ROUTER_PROMPT_POLICY_REMOTE_CODE \
  ROUTER_PROMPT_POLICY_REMOTE_CONCISE \
  ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT
do
  if [ -n "${!name:-}" ]; then
    docker_env_args+=("-e" "${name}=${!name}")
  fi
done

started_at="$(date +%s)"
docker run --rm \
  --platform linux/amd64 \
  --memory=4g \
  --cpus=2 \
  "${docker_env_args[@]}" \
  -v "$INPUT_DIR:/input:ro" \
  -v "$OUTPUT_DIR:/output" \
  "$IMAGE"
finished_at="$(date +%s)"
elapsed_seconds=$((finished_at - started_at))

python3 - "$INPUT_DIR/tasks.json" "$OUTPUT_DIR/results.json" "$OUTPUT_DIR/router_log.jsonl" "$elapsed_seconds" <<'PY'
import json
import sys
from collections import Counter
from pathlib import Path

input_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
log_path = Path(sys.argv[3])
container_elapsed_seconds = int(sys.argv[4])

payload = json.loads(input_path.read_text())
tasks = payload["tasks"] if isinstance(payload, dict) and isinstance(payload.get("tasks"), list) else payload
results = json.loads(output_path.read_text())

if not isinstance(results, list):
    raise SystemExit("results.json is not a list")
if not results:
    raise SystemExit("results.json is []")
if len(results) != len(tasks):
    raise SystemExit(f"answer count mismatch: tasks={len(tasks)} answers={len(results)}")

records = []
if log_path.exists():
    records = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]

routes = Counter(record.get("route") for record in records if record.get("task_id"))
remote_calls = sum(1 for record in records if record.get("fireworks_called"))
fallbacks = routes.get("fallback", 0)
local_model = routes.get("local_model", 0)
deterministic = routes.get("local", 0)
finish_records = [record for record in records if record.get("event") == "finish"]
batch_elapsed_ms = finish_records[-1].get("batch_elapsed_ms") if finish_records else None

print(f"tasks_read: {len(tasks)}")
print(f"answers_written: {len(results)}")
print(f"container_elapsed_seconds: {container_elapsed_seconds}")
if batch_elapsed_ms is not None:
    print(f"app_batch_elapsed_seconds: {batch_elapsed_ms / 1000:.3f}")
print(f"deterministic_count: {deterministic}")
print(f"local_llm_count: {local_model}")
print(f"remote_calls: {remote_calls}")
print(f"fallbacks: {fallbacks}")
print("first_5_answers:")
for row in results[:5]:
    print(json.dumps(row, ensure_ascii=False))
PY

python3 scripts/score_submission_fixture.py \
  "$INPUT_DIR/tasks.json" \
  "$OUTPUT_DIR/results.json" \
  --min-pass-rate "$MIN_FIXTURE_PASS_RATE"
