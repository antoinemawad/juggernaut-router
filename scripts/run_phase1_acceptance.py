import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "eval_runs"


def run(cmd: list[str]) -> dict:
    print("$ " + " ".join(cmd))
    started = datetime.now(timezone.utc)
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(completed.stdout)
    result = {
        "cmd": cmd,
        "returncode": completed.returncode,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    if completed.returncode != 0:
        result["output_tail"] = completed.stdout[-4000:]
    return result


def write_report(results: list[dict], status: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "phase1_acceptance_latest.json"
    payload = {
        "phase": "phase1-production-safe-runtime",
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": results,
        "acceptance_criteria": [
            "local quality gate passes",
            "official output shape is valid",
            "malformed input and telemetry tests pass",
            "Fireworks failure tests pass",
            "Docker guard passes when included",
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Phase 1 acceptance report: {path}")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 1 production-runtime acceptance checks.")
    parser.add_argument(
        "--include-docker",
        action="store_true",
        help="Also run Docker architecture, size, mounted IO, and output validation guard.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="When --include-docker is set, use the existing Docker image.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    py = sys.executable
    checks = [run([py, "scripts/run_local_quality_gate.py"])]

    if args.include_docker:
        docker_cmd = [py, "scripts/check_docker_runtime.py"]
        if args.skip_build:
            docker_cmd.append("--skip-build")
        checks.append(run(docker_cmd))

    failed = [check for check in checks if check["returncode"] != 0]
    status = "failed" if failed else "passed"
    write_report(checks, status)
    if failed:
        return failed[0]["returncode"]
    print("OK: Phase 1 acceptance passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
