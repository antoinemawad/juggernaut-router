#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_PATH="${OUTPUT_PATH:-/tmp/juggernaut-smoke-results.json}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: missing required command: $1" >&2
    exit 2
  fi
}

require_command python3

cd "${REPO_ROOT}"

rm -f "${OUTPUT_PATH}"

INPUT_PATH=examples/sample_tasks.json \
OUTPUT_PATH="${OUTPUT_PATH}" \
python3 -m app.main

python3 scripts/validate_submission_io.py "${OUTPUT_PATH}"

echo "Smoke test output:"
cat "${OUTPUT_PATH}"
