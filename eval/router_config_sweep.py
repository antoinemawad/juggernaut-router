import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.solvers.basic import try_basic_solver
from eval.model_matrix import (
    DEFAULT_OUT_DIR,
    DEFAULT_SCENARIOS,
    estimate_tokens,
    load_scenarios,
    mock_answer,
    prompt_for_policy,
    score_answer,
)


DEFAULT_CONFIGS = [
    {
        "name": "always_fireworks_baseline",
        "local_enabled": False,
        "fallback_model": "minimax-m3",
        "prompt_policy": "original",
        "max_tokens": 256,
        "local_min_score": 1.0,
    },
    {
        "name": "strict_hybrid",
        "local_enabled": True,
        "fallback_model": "minimax-m3",
        "prompt_policy": "original",
        "max_tokens": 192,
        "local_min_score": 1.0,
    },
    {
        "name": "balanced_hybrid",
        "local_enabled": True,
        "fallback_model": "minimax-m3",
        "prompt_policy": "answer_only",
        "max_tokens": 160,
        "local_min_score": 0.75,
    },
    {
        "name": "aggressive_local",
        "local_enabled": True,
        "fallback_model": "minimax-m3",
        "prompt_policy": "compact",
        "max_tokens": 128,
        "local_min_score": 0.5,
    },
]


def estimate_remote_tokens(config, scenario, answer):
    prompt = prompt_for_policy(scenario, config["prompt_policy"])
    return min(config["max_tokens"], estimate_tokens(prompt) + estimate_tokens(answer))


def run_scenario(config, scenario):
    local_answer = try_basic_solver(scenario["prompt"]) if config["local_enabled"] else None
    local_passed = False
    local_score = 0.0
    local_notes = []

    if local_answer:
        local_passed, local_score, local_notes = score_answer(local_answer, scenario)

    use_local = bool(local_answer) and local_score >= config["local_min_score"]
    if use_local:
        answer = local_answer
        route = "local"
        model = None
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0
        route_reason = f"local_score={local_score:.3f} >= {config['local_min_score']:.3f}"
    else:
        model = config["fallback_model"]
        answer = mock_answer(model, scenario)
        route = "fireworks_mock"
        prompt = prompt_for_policy(scenario, config["prompt_policy"])
        prompt_tokens = estimate_tokens(prompt)
        completion_tokens = estimate_tokens(answer)
        total_tokens = estimate_remote_tokens(config, scenario, answer)
        if not local_answer:
            route_reason = "no_local_answer"
        else:
            route_reason = f"local_score={local_score:.3f} < {config['local_min_score']:.3f}"

    passed, score, notes = score_answer(answer, scenario)
    return {
        "config": config["name"],
        "task_id": scenario["task_id"],
        "category": scenario["category"],
        "difficulty": scenario.get("difficulty"),
        "scenario_class": scenario.get("scenario_class"),
        "intent": scenario.get("intent"),
        "answer_shape": scenario.get("answer_shape"),
        "constraints": scenario.get("constraints", []),
        "risk_components": scenario.get("risk_components", []),
        "output_constraints": scenario.get("output_constraints", []),
        "expected_route": scenario.get("expected_route"),
        "remote_mode_hint": scenario.get("remote_mode_hint"),
        "verifier": scenario.get("verifier"),
        "retry_policy": scenario.get("retry_policy"),
        "failure_taxonomy": scenario.get("failure_taxonomy", []),
        "route": route,
        "route_reason": route_reason,
        "model": model,
        "prompt_policy": config["prompt_policy"],
        "max_tokens": config["max_tokens"],
        "local_min_score": config["local_min_score"],
        "local_answer_present": bool(local_answer),
        "local_score": round(local_score, 3),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "passed": passed,
        "score": score,
        "answer": answer,
        "expected_answer": scenario.get("expected_answer", ""),
        "notes": notes or local_notes,
    }


def summarize(rows, accuracy_threshold):
    by_config = defaultdict(lambda: {"cases": 0, "passed": 0, "score": 0.0, "tokens": 0, "local": 0})
    by_config_category = defaultdict(lambda: {"cases": 0, "passed": 0, "score": 0.0, "tokens": 0, "local": 0})

    for row in rows:
        for bucket in (by_config[row["config"]], by_config_category[(row["config"], row["category"])]):
            bucket["cases"] += 1
            bucket["passed"] += int(row["passed"])
            bucket["score"] += row["score"]
            bucket["tokens"] += row["total_tokens"]
            bucket["local"] += int(row["route"] == "local")

    ranked = sorted(
        by_config.items(),
        key=lambda item: (
            -(item[1]["passed"] / item[1]["cases"]),
            -(item[1]["score"] / item[1]["cases"]),
            item[1]["tokens"],
        ),
    )
    eligible = [
        (name, data)
        for name, data in ranked
        if data["passed"] / data["cases"] >= accuracy_threshold
    ]
    winner = eligible[0][0] if eligible else ranked[0][0]
    return by_config, by_config_category, ranked, eligible, winner


def write_report(path, rows, accuracy_threshold):
    by_config, by_config_category, ranked, eligible, winner = summarize(rows, accuracy_threshold)
    lines = [
        "# Router Config Sweep Report",
        "",
        f"Accuracy threshold: {accuracy_threshold:.2%}",
        f"Recommended config: `{winner}`",
        "",
        "## Summary by Config",
        "",
        "| Config | Cases | Pass Rate | Avg Score | Total Tokens | Avg Tokens | Local Route Rate | Eligible |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    eligible_names = {name for name, _data in eligible}
    for name, data in ranked:
        cases = data["cases"]
        lines.append(
            f"| {name} | {cases} | {data['passed'] / cases:.1%} | "
            f"{data['score'] / cases:.3f} | {data['tokens']} | "
            f"{data['tokens'] / cases:.1f} | {data['local'] / cases:.1%} | "
            f"{'yes' if name in eligible_names else 'no'} |"
        )

    lines.extend([
        "",
        "## Summary by Config and Category",
        "",
        "| Config | Category | Cases | Pass Rate | Avg Score | Total Tokens | Local Route Rate |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for (name, category), data in sorted(by_config_category.items()):
        cases = data["cases"]
        lines.append(
            f"| {name} | {category} | {cases} | {data['passed'] / cases:.1%} | "
            f"{data['score'] / cases:.3f} | {data['tokens']} | {data['local'] / cases:.1%} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Sweep local router configurations before official submissions.")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--accuracy-threshold", type=float, default=0.85)
    args = parser.parse_args()

    scenarios = load_scenarios(args.scenarios)
    run_id = datetime.now(timezone.utc).strftime("router_sweep_%Y%m%d_%H%M%S")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.out_dir / f"{run_id}.jsonl"
    report_path = args.out_dir / f"{run_id}.md"

    rows = []
    with log_path.open("x", encoding="utf-8") as handle:
        for config in DEFAULT_CONFIGS:
            for scenario in scenarios:
                row = run_scenario(config, scenario)
                row["run_id"] = run_id
                row["timestamp"] = datetime.now(timezone.utc).isoformat()
                rows.append(row)
                handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    _by_config, _by_category, _ranked, _eligible, winner = summarize(rows, args.accuracy_threshold)
    write_report(report_path, rows, args.accuracy_threshold)
    print(f"Scenarios: {len(scenarios)}")
    print(f"Configs: {len(DEFAULT_CONFIGS)}")
    print(f"Rows: {len(rows)}")
    print(f"Recommended config: {winner}")
    print(f"Log: {log_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
