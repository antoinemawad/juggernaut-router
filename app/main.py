import json
import os
from pathlib import Path

from app.agent import answer_prompt


INPUT_PATH = Path(os.environ.get("INPUT_PATH", "/input/tasks.json"))
OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH", "/output/results.json"))


def main():
    tasks = json.loads(INPUT_PATH.read_text(encoding="utf-8"))

    results = []
    for task in tasks:
        task_id = task.get("task_id")
        prompt = task.get("prompt", "")

        try:
            answer = answer_prompt(prompt)
        except Exception as exc:
            answer = f"Unable to answer safely: {type(exc).__name__}"

        results.append({
            "task_id": task_id,
            "answer": answer
        })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
