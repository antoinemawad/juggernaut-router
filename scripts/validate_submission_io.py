import json
import sys
from pathlib import Path


def fail(message):
    print(f"FAIL: {message}")
    return 1


def main():
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("local_test/output/results.json")
    if not output_path.exists():
        return fail(f"missing output file: {output_path}")

    try:
        data = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return fail(f"invalid JSON: {exc}")

    if not isinstance(data, list):
        return fail("output must be a JSON array")

    seen_ids = set()
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            return fail(f"item {index} must be an object")
        if set(item.keys()) != {"task_id", "answer"}:
            return fail(f"item {index} must contain exactly task_id and answer")
        if not isinstance(item["task_id"], str) or not item["task_id"].strip():
            return fail(f"item {index} has invalid task_id")
        if item["task_id"] in seen_ids:
            return fail(f"duplicate task_id: {item['task_id']}")
        seen_ids.add(item["task_id"])
        if not isinstance(item["answer"], str):
            return fail(f"item {index} answer must be a string")
        if not item["answer"].strip():
            return fail(f"item {index} answer must not be empty")

    print(f"OK: {len(data)} results in {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
