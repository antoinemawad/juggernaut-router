import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local container smoke test for Track 1 IO.")
    parser.add_argument("--image", default="juggernaut-router:local")
    parser.add_argument("--input-dir", default="local_test/accuracy_gate_input")
    parser.add_argument("--platform", default="linux/amd64")
    parser.add_argument("--min-pass-rate", type=float, default=0.0)
    args = parser.parse_args()

    repo = Path.cwd()
    input_dir = (repo / args.input_dir).resolve()
    tasks_path = input_dir / "tasks.json"
    if not tasks_path.exists():
        print(f"ERROR: missing fixture {tasks_path}", file=sys.stderr)
        return 2

    expected_count = count_tasks(tasks_path)
    with tempfile.TemporaryDirectory(prefix="juggernaut-router-output-") as output_tmp:
        output_dir = Path(output_tmp)
        cmd = [
            "docker",
            "run",
            "--rm",
            "--platform",
            args.platform,
            "-e",
            "ROUTER_LOG_PATH=/output/router_log.jsonl",
            "-v",
            f"{input_dir}:/input:ro",
            "-v",
            f"{output_dir}:/output",
            args.image,
        ]
        started = time.monotonic()
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
        container_elapsed_seconds = time.monotonic() - started
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        if proc.returncode != 0:
            print(f"ERROR: container exited with {proc.returncode}", file=sys.stderr)
            return proc.returncode

        results_path = output_dir / "results.json"
        if not results_path.exists():
            print("ERROR: /output/results.json was not written", file=sys.stderr)
            return 3
        try:
            results = json.loads(results_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"ERROR: results.json is invalid JSON: {exc}", file=sys.stderr)
            return 4
        if not isinstance(results, list):
            print("ERROR: results.json is not an array", file=sys.stderr)
            return 5

        telemetry = load_jsonl(output_dir / "router_log.jsonl")
        remote_calls = sum(1 for row in telemetry if row.get("route") == "fireworks")
        fallbacks = sum(1 for row in telemetry if row.get("route") == "fallback")
        finish_rows = [row for row in telemetry if row.get("event") == "finish"]
        batch_elapsed_ms = finish_rows[-1].get("batch_elapsed_ms") if finish_rows else None

        print(f"tasks_read: {expected_count}")
        print(f"answers_written: {len(results)}")
        print(f"container_elapsed_seconds: {container_elapsed_seconds:.3f}")
        if batch_elapsed_ms is not None:
            print(f"app_batch_elapsed_seconds: {batch_elapsed_ms / 1000:.3f}")
        print(f"remote_calls: {remote_calls}")
        print(f"fallbacks: {fallbacks}")
        print("first_5_answers:")
        for row in results[:5]:
            print(json.dumps(row, ensure_ascii=False))

        if not results:
            print("ERROR: results.json is empty", file=sys.stderr)
            return 6
        if len(results) != expected_count:
            print(
                f"ERROR: answer count {len(results)} does not match task count {expected_count}",
                file=sys.stderr,
            )
            return 7

        score_cmd = [
            sys.executable,
            str(repo / "scripts" / "score_submission_fixture.py"),
            str(tasks_path),
            str(results_path),
            "--min-pass-rate",
            str(args.min_pass_rate),
        ]
        score_proc = subprocess.run(score_cmd, text=True, capture_output=True, check=False)
        if score_proc.stdout:
            print(score_proc.stdout, end="")
        if score_proc.stderr:
            print(score_proc.stderr, end="", file=sys.stderr)
        if score_proc.returncode != 0:
            return score_proc.returncode
    return 0


def count_tasks(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("tasks", "questions", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
        return 1
    return 0


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
