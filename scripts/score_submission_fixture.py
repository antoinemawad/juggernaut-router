import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.model_matrix import score_answer


def main() -> int:
    parser = argparse.ArgumentParser(description="Score local submission output against an official-like fixture.")
    parser.add_argument("tasks_json")
    parser.add_argument("results_json")
    parser.add_argument("--min-pass-rate", type=float, default=0.0)
    args = parser.parse_args()

    tasks = load_tasks(Path(args.tasks_json))
    results = load_results(Path(args.results_json))
    by_id = {row.get("task_id"): row for row in results if isinstance(row, dict)}

    rows = []
    for task in tasks:
        task_id = str(task.get("task_id") or task.get("id") or "")
        result = by_id.get(task_id, {})
        answer = result.get("answer", "")
        scenario = {
            "prompt": task.get("prompt") or task.get("question") or "",
            "verifier": task.get("verifier"),
            "expected_answer": task.get("expected_answer"),
            "expected_keywords": task.get("expected_keywords", []),
            "constraints": task.get("constraints", []),
            "output_constraints": task.get("output_constraints", []),
        }
        passed, score, notes = score_answer(answer, scenario)
        rows.append(
            {
                "task_id": task_id,
                "category": task.get("category", "unknown"),
                "passed": passed,
                "score": score,
                "notes": notes,
                "answer": answer,
            }
        )

    total = len(rows)
    passed_count = sum(1 for row in rows if row["passed"])
    avg_score = sum(float(row["score"]) for row in rows) / max(1, total)
    pass_rate = passed_count / max(1, total)

    print(f"fixture_tasks: {total}")
    print(f"fixture_passed: {passed_count}")
    print(f"fixture_pass_rate: {pass_rate:.1%}")
    print(f"fixture_avg_score: {avg_score:.3f}")

    by_category = defaultdict(lambda: {"rows": 0, "passed": 0, "score": 0.0})
    for row in rows:
        bucket = by_category[row["category"]]
        bucket["rows"] += 1
        bucket["passed"] += int(row["passed"])
        bucket["score"] += float(row["score"])

    print("fixture_by_category:")
    for category in sorted(by_category):
        bucket = by_category[category]
        count = bucket["rows"]
        print(
            f"- {category}: pass_rate={bucket['passed'] / count:.1%} "
            f"avg_score={bucket['score'] / count:.3f} rows={count}"
        )

    failures = [row for row in rows if not row["passed"]]
    if failures:
        print("fixture_failures:")
        for row in failures[:10]:
            notes = ";".join(row["notes"])
            preview = str(row["answer"]).replace("\n", "\\n")[:180]
            print(f"- {row['task_id']} [{row['category']}]: score={row['score']} notes={notes} answer={preview}")

    missing_results = Counter(
        str(task.get("task_id") or task.get("id") or "")
        for task in tasks
        if str(task.get("task_id") or task.get("id") or "") not in by_id
    )
    if missing_results:
        print("fixture_missing_results: " + ",".join(sorted(missing_results)))
        return 8

    if pass_rate < args.min_pass_rate:
        print(
            f"ERROR: fixture pass rate {pass_rate:.1%} is below required {args.min_pass_rate:.1%}",
            file=sys.stderr,
        )
        return 9
    return 0


def load_tasks(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("tasks", "questions", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return [payload]
    return []


def load_results(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit("results_json must be a JSON array")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
