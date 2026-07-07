import json

from app.agent import answer_task
from app.config import RuntimeConfig
from app.deadline import DeadlineManager
from app.normalization import normalize_answer
from app.telemetry import TelemetryLogger
from app.types import SAFE_FALLBACK_ANSWER


def load_tasks(config: RuntimeConfig) -> tuple[list[dict], str | None]:
    try:
        raw = config.input_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], f"input_read_error:{type(exc).__name__}"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [], "input_invalid_json"

    if not isinstance(data, list):
        return [], "input_not_array"

    tasks = []
    seen_task_ids = set()
    for index, item in enumerate(data):
        task = coerce_task(item, index)
        task["task_id"] = unique_task_id(task["task_id"], index, seen_task_ids)
        tasks.append(task)
    return tasks, None


def coerce_task(item, index: int) -> dict:
    if not isinstance(item, dict):
        return {
            "task_id": f"invalid_{index}",
            "prompt": "",
            "input_error": "task_not_object",
        }

    raw_task_id = item.get("task_id")
    raw_prompt = item.get("prompt")
    task_id = str(raw_task_id).strip() if raw_task_id is not None else f"invalid_{index}"
    prompt = raw_prompt if isinstance(raw_prompt, str) else ""

    error = None
    if not task_id:
        task_id = f"invalid_{index}"
        error = "missing_task_id"
    if not isinstance(raw_prompt, str):
        error = "missing_or_non_string_prompt"

    return {
        "task_id": task_id,
        "prompt": prompt,
        "input_error": error,
    }


def unique_task_id(task_id: str, index: int, seen_task_ids: set[str]) -> str:
    candidate = task_id.strip() or f"invalid_{index}"
    if candidate not in seen_task_ids:
        seen_task_ids.add(candidate)
        return candidate

    suffix = 2
    while f"{candidate}_{suffix}" in seen_task_ids:
        suffix += 1
    unique = f"{candidate}_{suffix}"
    seen_task_ids.add(unique)
    return unique


def main():
    config = RuntimeConfig.from_env()
    deadline = DeadlineManager(
        total_seconds=config.batch_deadline_seconds,
        safety_margin_seconds=config.deadline_safety_margin_seconds,
    )
    telemetry = TelemetryLogger(config.router_log_path)
    tasks, input_error = load_tasks(config)
    results = []

    if input_error is not None:
        telemetry.log({
            "event": "input_error",
            "error": input_error,
            "batch_elapsed_ms": deadline.elapsed_ms(),
        })
        write_results(config, results)
        return

    for task in tasks:
        task_id = task["task_id"]
        prompt = task["prompt"]

        try:
            if task.get("input_error"):
                answer = SAFE_FALLBACK_ANSWER
                telemetry.log({
                    "task_id": task_id,
                    "route": "fallback",
                    "route_reason": task["input_error"],
                    "error": task["input_error"],
                    "batch_elapsed_ms_at_start": deadline.elapsed_ms(),
                    "batch_elapsed_ms_at_finish": deadline.elapsed_ms(),
                    "remaining_budget_ms": deadline.remaining_budget_ms(),
                })
            else:
                agent_result = answer_task(task_id, prompt, config=config, deadline=deadline)
                answer = agent_result.answer
                telemetry.log(agent_result.telemetry_record(task_id))
        except Exception as exc:
            answer = SAFE_FALLBACK_ANSWER
            telemetry.log({
                "task_id": task_id,
                "route": "fallback",
                "route_reason": "unhandled_task_exception",
                "error": type(exc).__name__,
                "batch_elapsed_ms_at_finish": deadline.elapsed_ms(),
                "remaining_budget_ms": deadline.remaining_budget_ms(),
            })

        results.append({
            "task_id": task_id,
            "answer": normalize_answer(answer),
        })

    write_results(config, results)


def write_results(config: RuntimeConfig, results: list[dict]) -> None:
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
