import os
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "eval_runs"


def run(cmd, env=None):
    print("$ " + " ".join(str(part) for part in cmd))
    started = datetime.now(timezone.utc)
    completed = subprocess.run(
        [str(part) for part in cmd],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(completed.stdout)
    result = {
        "cmd": [str(part) for part in cmd],
        "returncode": completed.returncode,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    if completed.returncode != 0:
        write_summary([result], "failed")
        raise SystemExit(completed.returncode)
    return result


def write_summary(results, status):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "local_quality_gate_latest.json"
    payload = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commands": results,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Quality gate summary: {path}")


def main():
    py = sys.executable
    results = []
    compile_targets = [
        "app/main.py",
        "app/agent.py",
        "app/fireworks_client.py",
        "app/solvers/basic.py",
        "eval/model_matrix.py",
        "eval/router_config_sweep.py",
        "scripts/check_eval_coverage.py",
        "scripts/compare_eval_reports.py",
        "scripts/validate_submission_io.py",
    ]

    results.append(run([py, "-m", "py_compile", *compile_targets]))
    results.append(run([py, "scripts/check_eval_coverage.py"]))
    results.append(run([py, "scripts/check_eval_coverage.py", "eval/golden_tier_2_regression.jsonl", "--profile", "tier"]))
    results.append(run([py, "scripts/check_eval_coverage.py", "eval/golden_tier_3_adversarial.jsonl", "--profile", "tier"]))

    local_env = os.environ.copy()
    local_env["INPUT_PATH"] = "local_test/input/tasks.json"
    local_env["OUTPUT_PATH"] = "local_test/output/results.json"
    results.append(run([py, "-m", "app.main"], env=local_env))
    results.append(run([py, "scripts/validate_submission_io.py", "local_test/output/results.json"]))

    results.append(run([py, "eval/router_config_sweep.py", "--accuracy-threshold", "0.85"]))
    results.append(run([py, "eval/model_matrix.py", "--prompt-policies", "all"]))

    write_summary(results, "passed")
    print("OK: local quality gate passed")


if __name__ == "__main__":
    main()
