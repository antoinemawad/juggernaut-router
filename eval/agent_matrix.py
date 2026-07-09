import argparse
import json
import os
import sys
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import app.agent as agent_module
from app.agent import answer_task
from app.config import RuntimeConfig
from app.deadline import DeadlineManager
from app.fireworks_client import ask_fireworks_structured as original_ask_fireworks_structured
from app.fireworks_client import select_allowed_model
from eval.model_matrix import (
    ALLOWED_TRACK1_MODELS,
    DEFAULT_OUT_DIR,
    DEFAULT_SCENARIOS,
    filter_scenarios_by_categories,
    limit_scenarios,
    load_scenarios,
    parse_categories,
    provider_model_for,
    score_answer,
)
from scripts.check_live_eval_env import validate_live_eval_env


def run_case(scenario: dict, config: RuntimeConfig, deadline: DeadlineManager) -> dict:
    result = answer_task(scenario["task_id"], scenario["prompt"], config=config, deadline=deadline)
    passed, score, notes = score_answer(result.answer, scenario)
    if result.error:
        notes.append(result.error)
    return {
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
        "route": result.route,
        "route_reason": result.route_reason,
        "selected_model": result.selected_model,
        "remote_mode": result.remote_mode,
        "prompt_policy": result.prompt_policy,
        "prompt_tokens": result.remote_prompt_token_estimate or result.prompt_token_estimate,
        "completion_tokens": result.completion_tokens or 0,
        "total_tokens": result.total_tokens or 0,
        "latency_ms": result.timings.task_elapsed_ms,
        "remote_elapsed_ms": result.timings.remote_elapsed_ms,
        "passed": passed and not result.error,
        "score": 0.0 if result.error else score,
        "answer": result.answer,
        "expected_answer": scenario.get("expected_answer"),
        "notes": notes,
        "error": result.error,
    }


@contextmanager
def normal_fireworks_dev_model_mapping(enabled: bool):
    if not enabled:
        yield
        return

    def mapped_ask_fireworks_structured(prompt, config=None, deadline=None, preferred_models=None, system_prompt=None):
        config = config or RuntimeConfig.from_env()
        alias = select_allowed_model(config, preferred_models)
        if alias is None:
            return original_ask_fireworks_structured(
                prompt,
                config=config,
                deadline=deadline,
                preferred_models=preferred_models,
                system_prompt=system_prompt,
            )
        provider_model = provider_model_for(alias, allow_normal_fireworks_dev=True)
        mapped_config = replace(config, allowed_models=(provider_model,))
        result = original_ask_fireworks_structured(
            prompt,
            config=mapped_config,
            deadline=deadline,
            preferred_models=(provider_model,),
            system_prompt=system_prompt,
        )
        if result.model == provider_model:
            result.model = alias
        return result

    previous = agent_module.ask_fireworks_structured
    agent_module.ask_fireworks_structured = mapped_ask_fireworks_structured
    try:
        yield
    finally:
        agent_module.ask_fireworks_structured = previous


def summarize(rows: list[dict]) -> tuple[dict, dict]:
    by_category = defaultdict(lambda: {"cases": 0, "passed": 0, "score": 0.0, "tokens": 0, "latency": 0.0})
    by_route = defaultdict(lambda: {"cases": 0, "passed": 0, "score": 0.0, "tokens": 0})
    for row in rows:
        category_row = by_category[row["category"]]
        category_row["cases"] += 1
        category_row["passed"] += int(row["passed"])
        category_row["score"] += row["score"]
        category_row["tokens"] += row["total_tokens"]
        category_row["latency"] += row["latency_ms"]

        route_row = by_route[row["route"]]
        route_row["cases"] += 1
        route_row["passed"] += int(row["passed"])
        route_row["score"] += row["score"]
        route_row["tokens"] += row["total_tokens"]
    return by_category, by_route


def write_report(path: Path, rows: list[dict], live: bool) -> None:
    by_category, by_route = summarize(rows)
    total_passed = sum(1 for row in rows if row["passed"])
    total_score = sum(row["score"] for row in rows)
    total_tokens = sum(int(row.get("total_tokens") or 0) for row in rows)
    lines = [
        "# Track 1 Agent Matrix Report",
        "",
        f"Mode: {'live Fireworks' if live else 'local/runtime'}",
        f"Rows: {len(rows)}",
        f"Pass rate: {total_passed / len(rows):.1%}" if rows else "Pass rate: 0.0%",
        f"Avg score: {total_score / len(rows):.3f}" if rows else "Avg score: 0.000",
        f"Total Fireworks tokens: {total_tokens}",
        "",
        "## Summary by Category",
        "",
        "| Category | Cases | Pass Rate | Avg Score | Total Tokens | Avg Latency ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for category, data in sorted(by_category.items()):
        cases = data["cases"]
        lines.append(
            f"| {category} | {cases} | {data['passed'] / cases:.1%} | "
            f"{data['score'] / cases:.3f} | {data['tokens']} | {data['latency'] / cases:.1f} |"
        )
    lines.extend([
        "",
        "## Summary by Route",
        "",
        "| Route | Cases | Pass Rate | Avg Score | Total Tokens |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for route, data in sorted(by_route.items()):
        cases = data["cases"]
        lines.append(
            f"| {route} | {cases} | {data['passed'] / cases:.1%} | "
            f"{data['score'] / cases:.3f} | {data['tokens']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Track 1 actual-agent matrix experiments.")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N scenarios for smoke tests.")
    parser.add_argument(
        "--categories",
        default=None,
        help="Comma-separated scenario categories to run, e.g. code_generation,text_summarisation.",
    )
    parser.add_argument("--live", action="store_true", help="Require a valid Fireworks environment for remote routes.")
    parser.add_argument(
        "--allow-normal-fireworks-dev",
        action="store_true",
        help="Development only: map Track 1 aliases to provider model IDs against normal Fireworks.",
    )
    args = parser.parse_args()

    if args.live:
        env_errors = validate_live_eval_env(os.environ, allow_normal_fireworks_dev=args.allow_normal_fireworks_dev)
        if env_errors:
            raise SystemExit("--live environment is not ready: " + "; ".join(env_errors))
        if args.allow_normal_fireworks_dev:
            print("WARNING: normal Fireworks dev override is enabled; results are not judging-proxy token data.")

    categories = parse_categories(args.categories)
    scenarios = limit_scenarios(filter_scenarios_by_categories(load_scenarios(args.scenarios), categories), args.limit)
    if not scenarios:
        raise SystemExit("No scenarios matched the requested filters.")

    run_id = datetime.now(timezone.utc).strftime("agent_matrix_%Y%m%d_%H%M%S_%f")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.out_dir / f"{run_id}.jsonl"
    report_path = args.out_dir / f"{run_id}.md"

    config = RuntimeConfig.from_env()
    if args.live and not config.allowed_models:
        config = replace(config, allowed_models=tuple(ALLOWED_TRACK1_MODELS))
    deadline = DeadlineManager(
        total_seconds=config.batch_deadline_seconds,
        safety_margin_seconds=config.deadline_safety_margin_seconds,
    )

    rows = []
    with normal_fireworks_dev_model_mapping(args.live and args.allow_normal_fireworks_dev):
        with log_path.open("x", encoding="utf-8") as handle:
            for scenario in scenarios:
                row = run_case(scenario, config, deadline)
                row["run_id"] = run_id
                row["timestamp"] = datetime.now(timezone.utc).isoformat()
                rows.append(row)
                handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    write_report(report_path, rows, args.live)
    print(f"Mode: {'live' if args.live else 'local/runtime'}")
    print(f"Scenarios: {len(scenarios)}")
    print(f"Rows: {len(rows)}")
    print(f"Log: {log_path}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
