import argparse
import json
from collections import defaultdict
from pathlib import Path


def load_jsonl(path):
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_number}: invalid JSON: {exc}") from exc
    return rows


def metric(row, *names, default=0):
    for name in names:
        value = row.get(name)
        if isinstance(value, (int, float)):
            return value
    return default


def summarize(rows):
    by_category = defaultdict(lambda: {"count": 0, "passes": 0, "score": 0.0, "tokens": 0})
    total = {"count": 0, "passes": 0, "score": 0.0, "tokens": 0}

    for row in rows:
        category = row.get("category", "unknown")
        score = metric(row, "score")
        passed = bool(row.get("pass", row.get("passed", score >= 1.0)))
        tokens = metric(row, "estimated_total_tokens", "total_tokens", "tokens")

        for bucket in (total, by_category[category]):
            bucket["count"] += 1
            bucket["passes"] += int(passed)
            bucket["score"] += score
            bucket["tokens"] += tokens

    return total, dict(sorted(by_category.items()))


def format_bucket(bucket):
    count = bucket["count"] or 1
    return {
        "rows": bucket["count"],
        "pass_rate": round(bucket["passes"] / count, 4),
        "avg_score": round(bucket["score"] / count, 4),
        "total_tokens": bucket["tokens"],
        "avg_tokens": round(bucket["tokens"] / count, 2),
    }


def compare_to_baseline(baseline, candidate):
    return {
        "pass_rate": round(candidate["pass_rate"] - baseline["pass_rate"], 4),
        "avg_score": round(candidate["avg_score"] - baseline["avg_score"], 4),
        "total_tokens": candidate["total_tokens"] - baseline["total_tokens"],
    }


def rank_candidates(records):
    return sorted(
        records,
        key=lambda item: (
            -item["summary"]["pass_rate"],
            -item["summary"]["avg_score"],
            item["summary"]["total_tokens"],
        ),
    )


def main():
    parser = argparse.ArgumentParser(description="Compare eval JSONL reports.")
    parser.add_argument("baseline", help="Baseline JSONL report path.")
    parser.add_argument("candidates", nargs="+", help="One or more candidate JSONL report paths.")
    args = parser.parse_args()

    baseline_rows = load_jsonl(Path(args.baseline))
    baseline_total, baseline_categories = summarize(baseline_rows)
    baseline = format_bucket(baseline_total)

    print("Baseline:", json.dumps(baseline, sort_keys=True))

    records = []
    for candidate_path_raw in args.candidates:
        candidate_path = Path(candidate_path_raw)
        candidate_rows = load_jsonl(candidate_path)
        candidate_total, candidate_categories = summarize(candidate_rows)
        candidate = format_bucket(candidate_total)
        delta = compare_to_baseline(baseline, candidate)
        records.append({"path": str(candidate_path), "summary": candidate, "delta": delta})

        label = "Candidate:" if len(args.candidates) == 1 else f"Candidate {candidate_path}:"
        print(label, json.dumps(candidate, sort_keys=True))
        print("Delta:", json.dumps(delta, sort_keys=True))

        categories = sorted(set(baseline_categories) | set(candidate_categories))
        for category in categories:
            before = format_bucket(baseline_categories.get(category, {"count": 0, "passes": 0, "score": 0, "tokens": 0}))
            after = format_bucket(candidate_categories.get(category, {"count": 0, "passes": 0, "score": 0, "tokens": 0}))
            print(f"{category}: {json.dumps({'baseline': before, 'candidate': after}, sort_keys=True)}")

    if len(records) > 1:
        print("Ranking:")
        for index, record in enumerate(rank_candidates(records), start=1):
            print(f"{index}. {record['path']}: {json.dumps(record['summary'], sort_keys=True)}")


if __name__ == "__main__":
    main()
