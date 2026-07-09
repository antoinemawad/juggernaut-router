import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.summarize_model_matrix_runs import filter_rows, load_jsonl, run_id_for
from eval.model_matrix import ACCESS_FAILURE_STATUSES, classify_access_error


DEFAULT_FALLBACK_MODEL = "minimax-m3"
DEFAULT_FALLBACK_POLICY = "original"
DEFAULT_MAX_TOKENS = 192
DEFAULT_REQUIRED_CATEGORIES = (
    "code_debugging",
    "code_generation",
    "factual_knowledge",
    "logical_deductive_reasoning",
    "mathematical_reasoning",
    "named_entity_recognition",
    "sentiment_classification",
    "text_summarisation",
)


def bucket() -> dict:
    return {
        "rows": 0,
        "runs": set(),
        "passed": 0,
        "score": 0.0,
        "tokens": 0,
        "errors": 0,
    }


def add_row(item: dict, row: dict) -> None:
    item["rows"] += 1
    item["runs"].add(run_id_for(row))
    item["passed"] += int(bool(row.get("passed")))
    item["score"] += float(row.get("score") or 0)
    item["tokens"] += int(row.get("total_tokens") or 0)
    item["errors"] += int(bool(row.get("error")))


def is_access_or_deployment_failure(row: dict) -> bool:
    status = row.get("access_status")
    if not status or status == "ok":
        status = classify_access_error(row.get("error"))
    return bool(row.get("error")) and status in ACCESS_FAILURE_STATUSES


def split_access_failures(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    quality_rows = []
    access_failures = []
    for row in rows:
        if is_access_or_deployment_failure(row):
            access_failures.append(row)
        else:
            quality_rows.append(row)
    return quality_rows, access_failures


def format_bucket(item: dict) -> dict:
    rows = item["rows"] or 1
    return {
        "rows": item["rows"],
        "runs": len(item["runs"]),
        "pass_rate": item["passed"] / rows,
        "avg_score": item["score"] / rows,
        "avg_tokens": item["tokens"] / rows,
        "errors": item["errors"],
    }


def grouped_stats(rows: list[dict]) -> dict:
    grouped = defaultdict(bucket)
    for row in rows:
        category = row.get("category", "unknown")
        model = row.get("model", "unknown")
        policy = row.get("prompt_policy", "original")
        add_row(grouped[(category, model, policy)], row)
    return {key: format_bucket(value) for key, value in grouped.items()}


def is_eligible(data: dict, min_pass_rate: float, min_avg_score: float, min_runs: int) -> bool:
    return (
        data["runs"] >= min_runs
        and data["errors"] == 0
        and data["pass_rate"] >= min_pass_rate
        and data["avg_score"] >= min_avg_score
    )


def eligibility_failures(data: dict, min_pass_rate: float, min_avg_score: float, min_runs: int) -> list[str]:
    failures = []
    if data["runs"] < min_runs:
        failures.append(f"runs<{min_runs}")
    if data["errors"] != 0:
        failures.append("errors>0")
    if data["pass_rate"] < min_pass_rate:
        failures.append(f"pass_rate<{min_pass_rate:.2f}")
    if data["avg_score"] < min_avg_score:
        failures.append(f"avg_score<{min_avg_score:.2f}")
    return failures


def choose_by_category(
    rows: list[dict],
    min_pass_rate: float,
    min_avg_score: float,
    min_runs: int,
    fallback_model: str,
    fallback_policy: str,
) -> dict[str, dict]:
    stats = grouped_stats(rows)
    by_category = defaultdict(list)
    for (category, model, policy), data in stats.items():
        by_category[category].append((model, policy, data))

    recommendations = {}
    for category, candidates in sorted(by_category.items()):
        ranked = sorted(
            candidates,
            key=lambda item: (
                not is_eligible(item[2], min_pass_rate, min_avg_score, min_runs),
                -item[2]["pass_rate"],
                -item[2]["avg_score"],
                item[2]["avg_tokens"],
                item[0],
                item[1],
            ),
        )
        model, policy, data = ranked[0]
        eligible = is_eligible(data, min_pass_rate, min_avg_score, min_runs)
        recommendations[category] = {
            "model": model if eligible else fallback_model,
            "prompt_policy": policy if eligible else fallback_policy,
            "eligible": eligible,
            "eligibility_failures": [] if eligible else eligibility_failures(
                data,
                min_pass_rate,
                min_avg_score,
                min_runs,
            ),
            "observed_best_model": model,
            "observed_best_prompt_policy": policy,
            "pass_rate": round(data["pass_rate"], 4),
            "avg_score": round(data["avg_score"], 4),
            "avg_tokens": round(data["avg_tokens"], 2),
            "runs": data["runs"],
            "rows": data["rows"],
        }
    return recommendations


def model_map_value(recommendations: dict[str, dict], fallback_model: str) -> str:
    parts = []
    for category, item in sorted(recommendations.items()):
        models = [item["model"]]
        if fallback_model not in models:
            models.append(fallback_model)
        parts.append(f"{category}={','.join(models)}")
    return ";".join(parts)


def prompt_policy_map_value(recommendations: dict[str, dict], fallback_policy: str) -> str:
    parts = []
    for category, item in sorted(recommendations.items()):
        policy = item["prompt_policy"]
        if policy != fallback_policy:
            parts.append(f"{category}={policy}")
    return ",".join(parts)


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def exports_for_recommendations(
    recommendations: dict[str, dict],
    fallback_model: str,
    fallback_policy: str,
    max_tokens: int,
) -> list[tuple[str, str | None]]:
    category_models = model_map_value(recommendations, fallback_model)
    category_policies = prompt_policy_map_value(recommendations, fallback_policy)
    return [
        ("ROUTER_MODE", "conservative"),
        ("LOCAL_CONFIDENCE_THRESHOLD", "0.95"),
        ("FIREWORKS_MAX_TOKENS", str(max_tokens)),
        ("ROUTER_PROMPT_POLICY_REMOTE_ACCURACY", fallback_policy),
        ("ROUTER_PROMPT_POLICY_REMOTE_CODE", fallback_policy),
        ("ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT", fallback_policy),
        ("ROUTER_PROMPT_POLICY_REMOTE_CONCISE", fallback_policy),
        ("ROUTER_PROMPT_POLICY_BY_CATEGORY", category_policies or None),
        ("ROUTER_MODELS_REMOTE_ACCURACY", fallback_model),
        ("ROUTER_MODELS_REMOTE_CODE", fallback_model),
        ("ROUTER_MODELS_REMOTE_FORMAT_STRICT", fallback_model),
        ("ROUTER_MODELS_REMOTE_CONCISE", fallback_model),
        ("ROUTER_MODELS_BY_CATEGORY", category_models or None),
    ]


def parse_required_categories(raw: str) -> tuple[str, ...]:
    if raw is None:
        return DEFAULT_REQUIRED_CATEGORIES
    categories = []
    seen = set()
    for item in raw.split(","):
        category = item.strip()
        if category and category not in seen:
            categories.append(category)
            seen.add(category)
    return tuple(categories)


def evidence_status(recommendations: dict[str, dict], required_categories: tuple[str, ...]) -> dict:
    covered = set(recommendations)
    required = set(required_categories)
    missing = sorted(required - covered)
    ineligible = sorted(
        category
        for category in required & covered
        if not recommendations[category].get("eligible")
    )
    status = "passed" if not missing and not ineligible else "needs_more_evidence"
    return {
        "status": status,
        "required_categories": list(required_categories),
        "covered_categories": sorted(covered),
        "eligible_categories": sorted(category for category, item in recommendations.items() if item.get("eligible")),
        "missing_categories": missing,
        "ineligible_categories": ineligible,
    }


def render_shell(exports: list[tuple[str, str | None]], source_reports: list[Path]) -> str:
    lines = [
        "# Runtime env recommendation from model matrix evidence",
        "# Source reports: " + ", ".join(str(path) for path in source_reports),
    ]
    for name, value in exports:
        if value is None:
            lines.append(f"unset {name}")
        else:
            lines.append(f"export {name}={shell_quote(value)}")
    return "\n".join(lines)


def write_markdown(
    path: Path,
    recommendations: dict[str, dict],
    exports: list[tuple[str, str | None]],
    status: dict,
    access_failure_count: int = 0,
) -> None:
    lines = [
        "# Model Matrix Runtime Recommendation",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Evidence status: `{status['status']}`",
        "",
        "## Evidence Coverage",
        "",
        f"- Required categories: {len(status['required_categories'])}",
        f"- Covered categories: {len(status['covered_categories'])}",
        f"- Eligible categories: {len(status['eligible_categories'])}",
        f"- Missing categories: {', '.join(status['missing_categories']) if status['missing_categories'] else 'none'}",
        f"- Ineligible categories: {', '.join(status['ineligible_categories']) if status['ineligible_categories'] else 'none'}",
        f"- Access/deployment failure rows excluded from quality scoring: {access_failure_count}",
        "",
        "> Models that returned access/deployment errors were excluded from quality scoring. This does not imply low model quality.",
        "",
        "## Category Decisions",
        "",
        "| Category | Runtime Model | Runtime Prompt | Eligible | Observed Best | Pass Rate | Avg Score | Avg Tokens | Runs | Failure Reasons |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for category, item in sorted(recommendations.items()):
        observed = f"{item['observed_best_model']} / {item['observed_best_prompt_policy']}"
        failures = ", ".join(item.get("eligibility_failures", [])) or "none"
        lines.append(
            f"| {category} | {item['model']} | {item['prompt_policy']} | "
            f"{'yes' if item['eligible'] else 'no'} | {observed} | "
            f"{item['pass_rate']:.1%} | {item['avg_score']:.3f} | {item['avg_tokens']:.1f} | {item['runs']} | {failures} |"
        )
    lines.extend(["", "## Shell Exports", "", "```bash"])
    lines.extend(render_shell(exports, []).splitlines()[2:])
    lines.extend(["```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recommend runtime env vars from model_matrix JSONL evidence.")
    parser.add_argument("reports", nargs="+", type=Path, help="model_matrix_*.jsonl files.")
    parser.add_argument("--out-json", type=Path, default=Path("eval_runs/model_matrix_runtime_recommendation.json"))
    parser.add_argument("--out-md", type=Path, default=Path("eval_runs/model_matrix_runtime_recommendation.md"))
    parser.add_argument("--min-pass-rate", type=float, default=0.80)
    parser.add_argument("--min-avg-score", type=float, default=0.80)
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument("--fallback-model", default=DEFAULT_FALLBACK_MODEL)
    parser.add_argument("--fallback-policy", default=DEFAULT_FALLBACK_POLICY)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--drop-error-rows", action="store_true")
    parser.add_argument("--max-run-error-rate", type=float, default=0.25)
    parser.add_argument(
        "--required-categories",
        default=",".join(DEFAULT_REQUIRED_CATEGORIES),
        help="Comma-separated categories that must be covered and eligible. Use an empty string to disable.",
    )
    args = parser.parse_args(argv)

    rows = []
    for path in args.reports:
        rows.extend(load_jsonl(path))
    rows, dropped = filter_rows(
        rows,
        drop_error_rows=args.drop_error_rows,
        max_run_error_rate=args.max_run_error_rate,
    )
    rows, access_failures = split_access_failures(rows)
    if not rows:
        raise SystemExit("No usable rows found.")

    recommendations = choose_by_category(
        rows=rows,
        min_pass_rate=args.min_pass_rate,
        min_avg_score=args.min_avg_score,
        min_runs=args.min_runs,
        fallback_model=args.fallback_model,
        fallback_policy=args.fallback_policy,
    )
    exports = exports_for_recommendations(
        recommendations,
        fallback_model=args.fallback_model,
        fallback_policy=args.fallback_policy,
        max_tokens=args.max_tokens,
    )
    status = evidence_status(
        recommendations,
        required_categories=parse_required_categories(args.required_categories),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_status": status["status"],
        "evidence": status,
        "source_reports": [str(path) for path in args.reports],
        "rows": len(rows),
        "runs": len({run_id_for(row) for row in rows}),
        "dropped": dropped,
        "access_failure_rows_excluded": len(access_failures),
        "thresholds": {
            "min_pass_rate": args.min_pass_rate,
            "min_avg_score": args.min_avg_score,
            "min_runs": args.min_runs,
        },
        "recommendations": recommendations,
        "exports": {name: value for name, value in exports},
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    write_markdown(args.out_md, recommendations, exports, status, access_failure_count=len(access_failures))

    print(render_shell(exports, args.reports))
    print(f"Evidence status: {status['status']}")
    if access_failures:
        print(f"Access/deployment failure rows excluded: {len(access_failures)}")
    print(f"JSON: {args.out_json}")
    print(f"Markdown: {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
