#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE="${IMAGE:-juggernaut-router:demo}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/juggernaut-demo-output}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: missing required command: $1" >&2
    exit 2
  fi
}

require_command docker
require_command python3

mkdir -p "${OUTPUT_DIR}"
rm -f "${OUTPUT_DIR}/results.json" "${OUTPUT_DIR}/router_log.jsonl"

cd "${REPO_ROOT}"

echo "Building ${IMAGE}..."
docker build --platform linux/amd64 -t "${IMAGE}" .

echo "Running demo fixture..."
docker run --rm --platform linux/amd64 \
  -v "${REPO_ROOT}/examples:/input:ro" \
  -v "${OUTPUT_DIR}:/output" \
  -e INPUT_PATH=/input/sample_tasks.json \
  -e ROUTER_LOG_PATH=/output/router_log.jsonl \
  "${IMAGE}"

echo "Validating output schema..."
python3 scripts/validate_submission_io.py "${OUTPUT_DIR}/results.json"

echo "Demo output:"
cat "${OUTPUT_DIR}/results.json"

echo
echo "Route log:"
cat "${OUTPUT_DIR}/router_log.jsonl"
