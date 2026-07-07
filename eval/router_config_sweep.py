import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.agent import answer_task
from app.config import RuntimeConfig
from app.fireworks_client import FireworksResult
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
        "router_mode": "conservative",
        "fallback_model": "minimax-m3",
        "prompt_policy": "original",
        "max_tokens": 256,
        "local_confidence_threshold": 1.01,
    },
    {
        "name": "strict_hybrid",
        "local_enabled": True,
        "router_mode": "conservative",
        "fallback_model": "minimax-m3",
        "prompt_policy": "original",
        "max_tokens": 192,
        "local_confidence_threshold": 0.95,
    },
    {
        "name": "balanced_hybrid",
        "local_enabled": True,
        "router_mode": "balanced",
        "fallback_model": "minimax-m3",
        "prompt_policy": "answer_only",
        "max_tokens": 160,
        "local_confidence_threshold": 0.9,
    },
    {
        "name": "aggressive_local",
        "local_enabled": True,
        "router_mode": "aggressive",
        "fallback_model": "minimax-m3",
        "prompt_policy": "compact",
        "max_tokens": 128,
        "local_confidence_threshold": 0.82,
    },
]


def estimate_remote_tokens(config, scenario, answer):
    prompt = prompt_for_policy(scenario, config["prompt_policy"])
    return min(config["max_tokens"], estimate_tokens(prompt) + estimate_tokens(answer))


def runtime_config(config):
    threshold = config["local_confidence_threshold"] if config["local_enabled"] else 1.01
    return RuntimeConfig(
        input_path=Path("/input/tasks.json"),
        output_path=Path("/output/results.json"),
        router_mode=config["router_mode"],
        local_confidence_threshold=threshold,
        fireworks_timeout_seconds=25,
        fireworks_max_retries=0,
        batch_deadline_seconds=600,
        deadline_safety_margin_seconds=60,
        remote_worker_count=1,
        local_proof_budget_ms=100,
        local_cross_check_enabled=True,
        router_log_path=None,
        fireworks_api_key="mock-key",
        fireworks_base_url="https://judge-proxy.example",
        allowed_models=(config["fallback_model"],),
        fireworks_max_tokens=config["max_tokens"],
    )


def route_matches_expected(route, expected_route):
    if not expected_route:
        return True
    if expected_route == "local":
        return route == "local"
    if expected_route.startswith("local_or_remote"):
        return route in {"local", "fireworks"}
    if expected_route.startswith("remote_"):
        return route == "fireworks"
    return route == expected_route


def run_scenario(config, scenario):
    prompt = prompt_for_policy(scenario, config["prompt_policy"])
    remote_answer = mock_answer(config["fallback_model"], scenario)
    remote_completion_tokens = estimate_tokens(remote_answer)
    remote_total_tokens = estimate_remote_tokens(config, scenario, remote_answer)

    def mock_fireworks(remote_prompt, config=None, deadline=None, preferred_models=None):
        return FireworksResult(
            answer=remote_answer,
            model=config.first_allowed_model() if config is not None else None,
            completion_tokens=remote_completion_tokens,
            total_tokens=remote_total_tokens,
            elapsed_ms=1,
        )

    with patch("app.agent.ask_fireworks_structured", side_effect=mock_fireworks):
        result = answer_task(
            task_id=scenario["task_id"],
            prompt=prompt,
            config=runtime_config(config),
        )

    answer = result.answer
    route = result.route
    model = result.selected_model
    local_answer_present = result.metadata.get("solver_confidence") is not None
    local_score = 0.0
    local_notes = []
    if local_answer_present and route == "local":
        _local_passed, local_score, local_notes = score_answer(answer, scenario)

    if route == "local":
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0
    else:
        prompt_tokens = estimate_tokens(prompt)
        completion_tokens = remote_completion_tokens
        total_tokens = remote_total_tokens

    passed, score, notes = score_answer(answer, scenario)
    expected_route = scenario.get("expected_route")
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
        "expected_route": expected_route,
        "expected_route_match": route_matches_expected(route, expected_route),
        "remote_mode_hint": scenario.get("remote_mode_hint"),
        "remote_mode": result.remote_mode,
        "verifier": scenario.get("verifier"),
        "retry_policy": scenario.get("retry_policy"),
        "failure_taxonomy": scenario.get("failure_taxonomy", []),
        "route": route,
        "route_reason": result.route_reason,
        "model": model,
        "prompt_policy": config["prompt_policy"],
        "max_tokens": config["max_tokens"],
        "router_mode": config["router_mode"],
        "local_confidence_threshold": config["local_confidence_threshold"],
        "local_answer_present": local_answer_present,
        "local_score": round(local_score, 3),
        "classification_confidence": result.metadata.get("classification_confidence"),
        "risk_score": result.metadata.get("risk_score"),
        "actual_risk_components": result.metadata.get("risk_components", {}),
        "local_proof_layers_passed": result.metadata.get("local_proof_layers_passed", []),
        "local_proof_layers_failed": result.metadata.get("local_proof_layers_failed", []),
        "validator_notes": result.metadata.get("validator_notes", []),
        "task_elapsed_ms": result.timings.task_elapsed_ms,
        "classification_elapsed_ms": result.timings.classification_elapsed_ms,
        "local_solver_elapsed_ms": result.timings.local_solver_elapsed_ms,
        "validation_elapsed_ms": result.timings.validation_elapsed_ms,
        "local_proof_elapsed_ms": result.timings.local_proof_elapsed_ms,
        "remote_elapsed_ms": result.timings.remote_elapsed_ms,
        "normalization_elapsed_ms": result.timings.normalization_elapsed_ms,
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
    by_config = defaultdict(lambda: {
        "cases": 0,
        "passed": 0,
        "score": 0.0,
        "tokens": 0,
        "local": 0,
        "route_match": 0,
    })
    by_config_category = defaultdict(lambda: {
        "cases": 0,
        "passed": 0,
        "score": 0.0,
        "tokens": 0,
        "local": 0,
        "route_match": 0,
    })

    for row in rows:
        for bucket in (by_config[row["config"]], by_config_category[(row["config"], row["category"])]):
            bucket["cases"] += 1
            bucket["passed"] += int(row["passed"])
            bucket["score"] += row["score"]
            bucket["tokens"] += row["total_tokens"]
            bucket["local"] += int(row["route"] == "local")
            bucket["route_match"] += int(row["expected_route_match"])

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
        "| Config | Cases | Pass Rate | Avg Score | Total Tokens | Avg Tokens | Local Route Rate | Expected Route Match | Eligible |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    eligible_names = {name for name, _data in eligible}
    for name, data in ranked:
        cases = data["cases"]
        lines.append(
            f"| {name} | {cases} | {data['passed'] / cases:.1%} | "
            f"{data['score'] / cases:.3f} | {data['tokens']} | "
            f"{data['tokens'] / cases:.1f} | {data['local'] / cases:.1%} | "
            f"{data['route_match'] / cases:.1%} | "
            f"{'yes' if name in eligible_names else 'no'} |"
        )

    lines.extend([
        "",
        "## Summary by Config and Category",
        "",
        "| Config | Category | Cases | Pass Rate | Avg Score | Total Tokens | Local Route Rate | Expected Route Match |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for (name, category), data in sorted(by_config_category.items()):
        cases = data["cases"]
        lines.append(
            f"| {name} | {category} | {cases} | {data['passed'] / cases:.1%} | "
            f"{data['score'] / cases:.3f} | {data['tokens']} | {data['local'] / cases:.1%} | "
            f"{data['route_match'] / cases:.1%} |"
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
