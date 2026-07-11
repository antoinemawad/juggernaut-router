import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.model_matrix import DEFAULT_SCENARIOS, load_scenarios
from eval.router_config_sweep import DEFAULT_CONFIGS, run_scenario


DEFAULT_OUT_DIR = REPO_ROOT / "eval_runs"


def config_by_name(name: str) -> dict:
    for config in DEFAULT_CONFIGS:
        if config["name"] == name:
            return config
    raise ValueError(f"Unknown router config: {name}")


def check_routes(config: dict, scenarios: list[dict]) -> list[dict]:
    rows = []
    for scenario in scenarios:
        row = run_scenario(config, scenario)
        remote_mode_hint = row.get("remote_mode_hint")
        remote_mode = row.get("remote_mode")
        remote_mode_match = (
            row["route"] != "fireworks"
            or not remote_mode_hint
            or remote_mode == remote_mode_hint
            or _simplified_remote_mode_matches(row["category"], remote_mode_hint, remote_mode)
        )
        rows.append({
            "task_id": row["task_id"],
            "category": row["category"],
            "scenario_class": row.get("scenario_class"),
            "expected_route": row.get("expected_route"),
            "actual_route": row["route"],
            "route_reason": row["route_reason"],
            "remote_mode": row.get("remote_mode"),
            "remote_mode_hint": remote_mode_hint,
            "remote_mode_match": remote_mode_match,
            "prompt_policy": row.get("prompt_policy"),
            "expected_route_match": row["expected_route_match"],
            "local_proof_layers_passed": row.get("local_proof_layers_passed", []),
            "local_proof_layers_failed": row.get("local_proof_layers_failed", []),
            "risk_score": row.get("risk_score"),
            "actual_risk_components": row.get("actual_risk_components", {}),
        })
    return rows


def _simplified_remote_mode_matches(category: str, remote_mode_hint: str, remote_mode: str | None) -> bool:
    if category in {"code_generation", "code_debugging"}:
        return remote_mode == "remote_code"
    return remote_mode == "remote_accuracy"


def write_artifacts(out_dir: Path, config_name: str, rows: list[dict]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_passed = all(row["expected_route_match"] and row["remote_mode_match"] for row in rows)
    payload = {
        "status": "passed" if all_passed else "failed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": config_name,
        "cases": len(rows),
        "matches": sum(1 for row in rows if row["expected_route_match"]),
        "remote_mode_matches": sum(1 for row in rows if row["remote_mode_match"]),
        "mismatches": [row for row in rows if not row["expected_route_match"]],
        "remote_mode_mismatches": [row for row in rows if not row["remote_mode_match"]],
        "rows": rows,
    }
    json_path = out_dir / "expected_routes_latest.json"
    md_path = out_dir / "expected_routes_latest.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    lines = [
        "# Expected Route Assertion Report",
        "",
        f"Config: `{config_name}`",
        f"Status: `{payload['status']}`",
        f"Cases: {payload['cases']}",
        f"Matches: {payload['matches']}",
        f"Remote Mode Matches: {payload['remote_mode_matches']}",
        "",
        "| Task | Category | Expected | Actual | Remote Mode Hint | Remote Mode | Prompt Policy | Route Match | Mode Match | Route Reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['task_id']} | {row['category']} | {row['expected_route']} | "
            f"{row['actual_route']} | {row.get('remote_mode_hint') or ''} | "
            f"{row.get('remote_mode') or ''} | "
            f"{row.get('prompt_policy') or ''} | "
            f"{'yes' if row['expected_route_match'] else 'no'} | "
            f"{'yes' if row['remote_mode_match'] else 'no'} | "
            f"{row['route_reason']} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Assert real router routes against scenario expected_route fields.")
    parser.add_argument("--config", default="strict_hybrid", help="Router config name from eval/router_config_sweep.py.")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    config = config_by_name(args.config)
    rows = check_routes(config, load_scenarios(args.scenarios))
    json_path, md_path = write_artifacts(args.out_dir, args.config, rows)
    mismatches = [row for row in rows if not row["expected_route_match"]]
    mode_mismatches = [row for row in rows if not row["remote_mode_match"]]
    print(f"Config: {args.config}")
    print(f"Scenarios: {len(rows)}")
    print(f"Expected route matches: {len(rows) - len(mismatches)}")
    print(f"Remote mode matches: {len(rows) - len(mode_mismatches)}")
    print(f"JSON: {json_path}")
    print(f"Report: {md_path}")
    if mismatches:
        print("Mismatches:")
        for row in mismatches:
            print(f"- {row['task_id']}: expected={row['expected_route']} actual={row['actual_route']} reason={row['route_reason']}")
        return 1
    if mode_mismatches:
        print("Remote mode mismatches:")
        for row in mode_mismatches:
            print(
                f"- {row['task_id']}: expected_mode={row['remote_mode_hint']} "
                f"actual_mode={row['remote_mode']} route={row['actual_route']}"
            )
        return 1
    print("OK: expected routes matched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
