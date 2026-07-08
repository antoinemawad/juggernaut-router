import argparse
import json
from collections import defaultdict
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            row["_source_file"] = str(path)
            rows.append(row)
    return rows


def run_id_for(row: dict) -> str:
    return row.get("run_id") or row.get("_source_file") or "unknown"


def filter_rows(rows: list[dict], drop_error_rows=False, max_run_error_rate: float | None = None) -> tuple[list[dict], dict]:
    dropped = {
        "error_rows": 0,
        "error_runs": [],
    }
    if max_run_error_rate is not None:
        by_run = defaultdict(lambda: {"rows": 0, "errors": 0})
        for row in rows:
            bucket = by_run[run_id_for(row)]
            bucket["rows"] += 1
            bucket["errors"] += int(bool(row.get("error")))
        dropped_runs = {
            run_id
            for run_id, item in by_run.items()
            if item["rows"] and item["errors"] / item["rows"] > max_run_error_rate
        }
        dropped["error_runs"] = sorted(dropped_runs)
        rows = [row for row in rows if run_id_for(row) not in dropped_runs]

    if drop_error_rows:
        before = len(rows)
        rows = [row for row in rows if not row.get("error")]
        dropped["error_rows"] = before - len(rows)

    return rows, dropped


def bucket() -> dict:
    return {
        "rows": 0,
        "runs": set(),
        "passed": 0,
        "score": 0.0,
        "tokens": 0,
        "latency_ms": 0.0,
        "errors": 0,
    }


def add_row(item: dict, row: dict) -> None:
    item["rows"] += 1
    item["runs"].add(run_id_for(row))
    item["passed"] += int(bool(row.get("passed")))
    item["score"] += float(row.get("score") or 0)
    item["tokens"] += int(row.get("total_tokens") or 0)
    item["latency_ms"] += float(row.get("latency_ms") or 0)
    item["errors"] += int(bool(row.get("error")))


def format_bucket(item: dict) -> dict:
    rows = item["rows"] or 1
    return {
        "rows": item["rows"],
        "runs": len(item["runs"]),
        "pass_rate": round(item["passed"] / rows, 4),
        "avg_score": round(item["score"] / rows, 4),
        "total_tokens": item["tokens"],
        "avg_tokens": round(item["tokens"] / rows, 2),
        "avg_latency_ms": round(item["latency_ms"] / rows, 2),
        "errors": item["errors"],
    }


def summarize(rows: list[dict]) -> tuple[dict, dict, dict]:
    by_model_policy = defaultdict(bucket)
    by_category_model_policy = defaultdict(bucket)
    by_category = defaultdict(bucket)

    for row in rows:
        model = row.get("model", "unknown")
        policy = row.get("prompt_policy", "unknown")
        category = row.get("category", "unknown")
        add_row(by_model_policy[(model, policy)], row)
        add_row(by_category_model_policy[(category, model, policy)], row)
        add_row(by_category[category], row)

    return by_model_policy, by_category_model_policy, by_category


def rank_items(items):
    return sorted(
        items,
        key=lambda item: (
            -item[1]["pass_rate"],
            -item[1]["avg_score"],
            item[1]["avg_tokens"],
            item[0],
        ),
    )


def recommended_by_category(by_category_model_policy: dict) -> dict:
    grouped = defaultdict(list)
    for (category, model, policy), raw in by_category_model_policy.items():
        grouped[category].append(((model, policy), format_bucket(raw)))
    return {
        category: rank_items(items)[0]
        for category, items in sorted(grouped.items())
        if items
    }


def write_markdown(path: Path, rows: list[dict], dropped: dict | None = None) -> None:
    dropped = dropped or {"error_rows": 0, "error_runs": []}
    by_model_policy, by_category_model_policy, by_category = summarize(rows)
    formatted_model_policy = {
        key: format_bucket(value)
        for key, value in by_model_policy.items()
    }
    formatted_category = {
        key: format_bucket(value)
        for key, value in by_category.items()
    }
    recommendations = recommended_by_category(by_category_model_policy)

    lines = [
        "# Model Matrix Multi-Run Summary",
        "",
        f"Rows: {len(rows)}",
        f"Source runs: {len({run_id_for(row) for row in rows})}",
        f"Dropped error rows: {dropped.get('error_rows', 0)}",
        f"Dropped high-error runs: {len(dropped.get('error_runs', []))}",
        "",
        "## Model And Prompt Policy",
        "",
        "| Model | Prompt Policy | Rows | Runs | Pass Rate | Avg Score | Avg Tokens | Total Tokens | Avg Latency ms | Errors |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for (model, policy), data in rank_items(formatted_model_policy.items()):
        lines.append(
            f"| {model} | {policy} | {data['rows']} | {data['runs']} | "
            f"{data['pass_rate']:.1%} | {data['avg_score']:.3f} | {data['avg_tokens']:.1f} | "
            f"{data['total_tokens']} | {data['avg_latency_ms']:.1f} | {data['errors']} |"
        )

    lines.extend([
        "",
        "## Category Coverage",
        "",
        "| Category | Rows | Runs | Pass Rate | Avg Score | Avg Tokens | Errors |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for category, data in sorted(formatted_category.items()):
        lines.append(
            f"| {category} | {data['rows']} | {data['runs']} | {data['pass_rate']:.1%} | "
            f"{data['avg_score']:.3f} | {data['avg_tokens']:.1f} | {data['errors']} |"
        )

    lines.extend([
        "",
        "## Recommended By Category",
        "",
        "| Category | Model | Prompt Policy | Pass Rate | Avg Score | Avg Tokens | Runs |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for category, ((model, policy), data) in recommendations.items():
        lines.append(
            f"| {category} | {model} | {policy} | {data['pass_rate']:.1%} | "
            f"{data['avg_score']:.3f} | {data['avg_tokens']:.1f} | {data['runs']} |"
        )

    if dropped.get("error_runs"):
        lines.extend([
            "",
            "## Dropped High-Error Runs",
            "",
        ])
        for run_id in dropped["error_runs"]:
            lines.append(f"- `{run_id}`")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize one or more model_matrix JSONL runs.")
    parser.add_argument("reports", nargs="+", type=Path, help="model_matrix_*.jsonl files.")
    parser.add_argument("--out", type=Path, default=None, help="Optional markdown output path.")
    parser.add_argument("--drop-error-rows", action="store_true", help="Exclude rows that have a non-empty error field.")
    parser.add_argument(
        "--max-run-error-rate",
        type=float,
        default=None,
        help="Exclude whole runs whose error-row rate is greater than this value, e.g. 0.25.",
    )
    args = parser.parse_args()

    rows = []
    for path in args.reports:
        rows.extend(load_jsonl(path))
    rows, dropped = filter_rows(
        rows,
        drop_error_rows=args.drop_error_rows,
        max_run_error_rate=args.max_run_error_rate,
    )
    if not rows:
        raise SystemExit("No rows found.")

    out = args.out
    if out is None:
        out = Path("eval_runs") / "model_matrix_multi_run_summary.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(out, rows, dropped)
    print(f"Rows: {len(rows)}")
    print(f"Runs: {len({run_id_for(row) for row in rows})}")
    print(f"Dropped error rows: {dropped.get('error_rows', 0)}")
    print(f"Dropped high-error runs: {len(dropped.get('error_runs', []))}")
    print(f"Report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
