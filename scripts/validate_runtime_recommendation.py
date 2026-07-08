import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVAL_RUNS = ROOT / "eval_runs"
ROUTER_ENV_PREFIXES = ("ROUTER_",)
ROUTER_ENV_NAMES = {
    "FIREWORKS_MAX_TOKENS",
    "LOCAL_CONFIDENCE_THRESHOLD",
}


def load_recommendation(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    exports = payload.get("exports")
    if not isinstance(exports, dict):
        raise ValueError(f"{path} does not contain an exports object")
    evidence_status = payload.get("evidence_status")
    if evidence_status is not None and evidence_status != "passed":
        raise ValueError(f"{path} evidence_status is {evidence_status!r}, not 'passed'")
    return payload


def isolated_env(base_env: dict[str, str], recommendation_path: Path) -> dict[str, str]:
    env = {
        key: value
        for key, value in base_env.items()
        if not key.startswith(ROUTER_ENV_PREFIXES) and key not in ROUTER_ENV_NAMES
    }
    env["ROUTER_RECOMMENDATION_PATH"] = str(recommendation_path)
    return env


def default_commands(py: str) -> list[list[str]]:
    return [
        [py, "-m", "unittest", "discover", "-s", "tests"],
        [py, "scripts/check_submission_static.py"],
        [py, "scripts/check_expected_routes.py", "--config", "strict_hybrid"],
        [py, "scripts/check_expected_routes.py", "--config", "strict_hybrid", "--scenarios", "eval/golden_tier_2_regression.jsonl"],
        [py, "scripts/check_expected_routes.py", "--config", "strict_hybrid", "--scenarios", "eval/golden_tier_3_adversarial.jsonl"],
        [py, "-m", "app.main"],
        [py, "scripts/validate_submission_io.py", "local_test/output/results_recommendation_check.json"],
    ]


def run_command(cmd: list[str], env: dict[str, str]) -> dict:
    started = datetime.now(timezone.utc)
    command_env = env.copy()
    if cmd[1:] == ["-m", "app.main"]:
        command_env["INPUT_PATH"] = "local_test/input/tasks.json"
        command_env["OUTPUT_PATH"] = "local_test/output/results_recommendation_check.json"
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        env=command_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return {
        "cmd": cmd,
        "returncode": completed.returncode,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "output_tail": completed.stdout[-4000:],
    }


def validate_recommendation(
    recommendation_path: Path,
    out_json: Path,
    out_md: Path,
    include_quality_gate: bool = False,
    runner=run_command,
) -> dict:
    payload = load_recommendation(recommendation_path)
    env = isolated_env(os.environ.copy(), recommendation_path)
    py = sys.executable
    commands = default_commands(py)
    if include_quality_gate:
        commands.append([py, "scripts/run_local_quality_gate.py"])

    results = []
    status = "passed"
    for cmd in commands:
        result = runner(cmd, env)
        results.append(result)
        if result["returncode"] != 0:
            status = "failed"
            break

    report = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recommendation_path": str(recommendation_path),
        "applied_exports": payload["exports"],
        "commands": results,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    write_markdown(out_md, report)
    return report


def write_markdown(path: Path, report: dict) -> None:
    lines = [
        "# Runtime Recommendation Validation",
        "",
        f"Status: `{report['status']}`",
        f"Recommendation: `{report['recommendation_path']}`",
        f"Timestamp: {report['timestamp']}",
        "",
        "## Applied Exports",
        "",
        "| Name | Value |",
        "| --- | --- |",
    ]
    for name, value in sorted(report["applied_exports"].items()):
        lines.append(f"| `{name}` | `{'' if value is None else value}` |")
    lines.extend([
        "",
        "## Commands",
        "",
        "| Command | Return Code |",
        "| --- | ---: |",
    ])
    for result in report["commands"]:
        lines.append(f"| `{' '.join(result['cmd'])}` | {result['returncode']} |")
    failing = [result for result in report["commands"] if result["returncode"] != 0]
    if failing:
        lines.extend(["", "## Failure Output", "", "```text", failing[0].get("output_tail", ""), "```"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a generated runtime recommendation in an isolated env.")
    parser.add_argument("recommendation", type=Path, help="Recommendation JSON from recommend_from_model_matrix.py.")
    parser.add_argument("--out-json", type=Path, default=EVAL_RUNS / "runtime_recommendation_validation_latest.json")
    parser.add_argument("--out-md", type=Path, default=EVAL_RUNS / "runtime_recommendation_validation_latest.md")
    parser.add_argument("--include-quality-gate", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = validate_recommendation(
            recommendation_path=args.recommendation,
            out_json=args.out_json,
            out_md=args.out_md,
            include_quality_gate=args.include_quality_gate,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Status: {report['status']}")
    print(f"JSON: {args.out_json}")
    print(f"Markdown: {args.out_md}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
