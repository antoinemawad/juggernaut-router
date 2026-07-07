import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd, env=None):
    print("$ " + " ".join(str(part) for part in cmd))
    completed = subprocess.run(
        [str(part) for part in cmd],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(completed.stdout)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main():
    py = sys.executable
    compile_targets = [
        "app/main.py",
        "app/agent.py",
        "app/fireworks_client.py",
        "app/solvers/basic.py",
        "eval/model_matrix.py",
        "eval/router_config_sweep.py",
        "scripts/check_eval_coverage.py",
        "scripts/validate_submission_io.py",
    ]

    run([py, "-m", "py_compile", *compile_targets])
    run([py, "scripts/check_eval_coverage.py"])

    local_env = os.environ.copy()
    local_env["INPUT_PATH"] = "local_test/input/tasks.json"
    local_env["OUTPUT_PATH"] = "local_test/output/results.json"
    run([py, "-m", "app.main"], env=local_env)
    run([py, "scripts/validate_submission_io.py", "local_test/output/results.json"])

    run([py, "eval/router_config_sweep.py", "--accuracy-threshold", "0.85"])
    run([py, "eval/model_matrix.py", "--prompt-policies", "all"])

    print("OK: local quality gate passed")


if __name__ == "__main__":
    main()
