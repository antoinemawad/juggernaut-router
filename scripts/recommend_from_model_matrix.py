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


DEFAULT_FALLBACK_MODEL = "minimax-m3"
DEFAULT_FALLBACK_POLICY = "original"
DEFAULT_MAX_TOKENS = 192


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


def write_markdown(path: Path, recommendations: dict[str, dict], exports: list[tuple[str, str | None]]) -> None:
    lines = [
        "# Model Matrix Runtime Recommendation",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Category Decisions",
        "",
        "| Category | Runtime Model | Runtime Prompt | Eligible | Observed Best | Pass Rate | Avg Score | Avg Tokens | Runs |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for category, item in sorted(recommendations.items()):
        observed = f"{item['observed_best_model']} / {item['observed_best_prompt_policy']}"
        lines.append(
            f"| {category} | {item['model']} | {item['prompt_policy']} | "
            f"{'yes' if item['eligible'] else 'no'} | {observed} | "
            f"{item['pass_rate']:.1%} | {item['avg_score']:.3f} | {item['avg_tokens']:.1f} | {item['runs']} |"
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
    parser.add_argument("--min-pass-rate", type=float, default=0.85)
    parser.add_argument("--min-avg-score", type=float, default=0.85)
    parser.add_argument("--min-runs", type=int, default=2)
    parser.add_argument("--fallback-model", default=DEFAULT_FALLBACK_MODEL)
    parser.add_argument("--fallback-policy", default=DEFAULT_FALLBACK_POLICY)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--drop-error-rows", action="store_true")
    parser.add_argument("--max-run-error-rate", type=float, default=0.25)
    args = parser.parse_args(argv)

    rows = []
    for path in args.reports:
        rows.extend(load_jsonl(path))
    rows, dropped = filter_rows(
        rows,
        drop_error_rows=args.drop_error_rows,
        max_run_error_rate=args.max_run_error_rate,
    )
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

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_reports": [str(path) for path in args.reports],
        "rows": len(rows),
        "runs": len({run_id_for(row) for row in rows}),
        "dropped": dropped,
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
    write_markdown(args.out_md, recommendations, exports)

    print(render_shell(exports, args.reports))
    print(f"JSON: {args.out_json}")
    print(f"Markdown: {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
