import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.agent import answer_task
from app.config import RuntimeConfig
from app.deadline import DeadlineManager
from app.normalization import normalize_answer
from app.telemetry import TelemetryLogger
from app.types import SAFE_FALLBACK_ANSWER


def load_tasks(config: RuntimeConfig) -> tuple[list[dict], str | None, dict]:
    input_path, discovered_files = resolve_input_path(config.input_path)
    diagnostics = {
        "configured_input_path": str(config.input_path),
        "input_path_used": str(input_path),
        "input_directory": str(input_path.parent),
        "input_files": discovered_files,
    }
    try:
        raw = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        diagnostics["input_read_exception"] = type(exc).__name__
        return [], f"input_read_error:{type(exc).__name__}", diagnostics

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [], "input_invalid_json", diagnostics

    data, shape_error = extract_task_items(data)
    if shape_error is not None:
        return [], shape_error, diagnostics

    tasks = []
    seen_task_ids = set()
    for index, item in enumerate(data):
        task = coerce_task(item, index)
        task["task_id"] = unique_task_id(task["task_id"], index, seen_task_ids)
        tasks.append(task)
    diagnostics["tasks_parsed"] = len(tasks)
    return tasks, None, diagnostics


def resolve_input_path(configured_path: Path) -> tuple[Path, list[str]]:
    input_dir = configured_path.parent
    discovered = discover_input_files(input_dir)
    if configured_path.exists():
        return configured_path, discovered

    json_candidates = [
        input_dir / name
        for name in discovered
        if name.endswith(".json") and not name.startswith(".")
    ]
    if len(json_candidates) == 1:
        return json_candidates[0], discovered
    for preferred_name in ("tasks.json", "input.json", "questions.json", "data.json"):
        candidate = input_dir / preferred_name
        if candidate.exists():
            return candidate, discovered
    return configured_path, discovered


def discover_input_files(input_dir: Path) -> list[str]:
    try:
        return sorted(path.name for path in input_dir.iterdir())
    except OSError:
        return []


def extract_task_items(data) -> tuple[list, str | None]:
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        for key in ("tasks", "questions", "items", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value, None
        if any(key in data for key in ("prompt", "question", "input", "text")):
            return [data], None
        return [], "input_object_without_task_array"
    return [], "input_not_array_or_object"


def coerce_task(item, index: int) -> dict:
    if not isinstance(item, dict):
        return {
            "task_id": f"invalid_{index}",
            "prompt": "",
            "input_error": "task_not_object",
        }

    raw_task_id = first_present(item, ("task_id", "id", "uid", "name"))
    raw_prompt = first_present(item, ("prompt", "question", "input", "text", "query"))
    task_id = str(raw_task_id).strip() if raw_task_id is not None else f"invalid_{index}"
    prompt = prompt_to_text(raw_prompt)

    error = None
    if not task_id:
        task_id = f"invalid_{index}"
        error = "missing_task_id"
    if prompt == "":
        error = "missing_or_non_string_prompt"

    return {
        "task_id": task_id,
        "prompt": prompt,
        "input_error": error,
    }


def first_present(item: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in item:
            return item[key]
    return None


def prompt_to_text(value) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, list):
        return "\n".join(prompt_to_text(item) for item in value if prompt_to_text(item))
    return str(value)


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
    tasks, input_error, input_diagnostics = load_tasks(config)
    results = []
    log_runtime_event("startup", startup_diagnostics(config, input_diagnostics, len(tasks), input_error))

    if input_error is not None:
        record = {
            "event": "input_error",
            "error": input_error,
            "tasks_parsed": len(tasks),
            **input_diagnostics,
            "batch_elapsed_ms": deadline.elapsed_ms(),
        }
        log_runtime_event("input_error", record)
        telemetry.log(record)
        write_results(config, results)
        return

    results = run_tasks(tasks, config, deadline, telemetry)

    write_results(config, results)
    summary = summarize_results(tasks, results, deadline, telemetry)
    log_runtime_event("finish", summary)


def startup_diagnostics(
    config: RuntimeConfig,
    input_diagnostics: dict,
    tasks_parsed: int,
    input_error: str | None,
) -> dict:
    return {
        "cwd": os.getcwd(),
        "output_path": str(config.output_path),
        "router_mode": config.router_mode,
        "allowed_models": list(config.allowed_models),
        "fireworks_base_url_present": bool(config.fireworks_base_url),
        "fireworks_api_key_present": bool(config.fireworks_api_key),
        "local_model_enabled": config.local_model_enabled,
        "tasks_parsed": tasks_parsed,
        "input_error": input_error,
        **input_diagnostics,
    }


def summarize_results(
    tasks: list[dict],
    results: list[dict],
    deadline: DeadlineManager,
    telemetry: TelemetryLogger,
) -> dict:
    return {
        "tasks_read": len(tasks),
        "answers_written": len(results),
        "output_answer_count_matches_tasks": len(tasks) == len(results),
        "output_empty": len(results) == 0,
        "batch_elapsed_ms": deadline.elapsed_ms(),
        "telemetry_enabled": telemetry.enabled,
    }


def log_runtime_event(event: str, payload: dict) -> None:
    safe = {"event": event, **payload}
    print("[juggernaut-router] " + json.dumps(safe, ensure_ascii=True, sort_keys=True), file=sys.stderr, flush=True)


def run_tasks(
    tasks: list[dict],
    config: RuntimeConfig,
    deadline: DeadlineManager,
    telemetry: TelemetryLogger,
) -> list[dict]:
    if not tasks:
        log_runtime_event("no_tasks", {
            "message": "zero tasks parsed; output will be an empty valid results array",
        })
        return []

    results: list[dict | None] = [None] * len(tasks)
    max_workers = max(1, min(config.remote_worker_count, len(tasks)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_task, index, task, config, deadline): (index, task)
            for index, task in enumerate(tasks)
        }
        for future in as_completed(futures):
            index, task = futures[future]
            try:
                output_row, telemetry_record = future.result()
            except Exception as exc:
                task_id = task.get("task_id", f"invalid_{index}")
                output_row = {
                    "task_id": task_id,
                    "answer": SAFE_FALLBACK_ANSWER,
                }
                telemetry_record = {
                    "task_id": task_id,
                    "route": "fallback",
                    "route_reason": "unhandled_worker_exception",
                    "error": type(exc).__name__,
                    "batch_elapsed_ms_at_finish": deadline.elapsed_ms(),
                    "remaining_budget_ms": deadline.remaining_budget_ms(),
                }
            results[index] = output_row
            telemetry.log(telemetry_record)

    return [row for row in results if row is not None]


def process_task(
    index: int,
    task: dict,
    config: RuntimeConfig,
    deadline: DeadlineManager,
) -> tuple[dict, dict]:
    task_id = task["task_id"]
    prompt = task["prompt"]
    started_ms = deadline.elapsed_ms()

    try:
        if task.get("input_error"):
            answer = SAFE_FALLBACK_ANSWER
            telemetry_record = {
                "task_id": task_id,
                "route": "fallback",
                "route_reason": task["input_error"],
                "error": task["input_error"],
                "batch_elapsed_ms_at_start": started_ms,
                "batch_elapsed_ms_at_finish": deadline.elapsed_ms(),
                "remaining_budget_ms": deadline.remaining_budget_ms(),
            }
        else:
            agent_result = answer_task(task_id, prompt, config=config, deadline=deadline)
            answer = agent_result.answer
            telemetry_record = agent_result.telemetry_record(task_id)
    except Exception as exc:
        answer = SAFE_FALLBACK_ANSWER
        telemetry_record = {
            "task_id": task_id,
            "route": "fallback",
            "route_reason": "unhandled_task_exception",
            "error": type(exc).__name__,
            "batch_elapsed_ms_at_start": started_ms,
            "batch_elapsed_ms_at_finish": deadline.elapsed_ms(),
            "remaining_budget_ms": deadline.remaining_budget_ms(),
        }

    return {
        "task_id": task_id,
        "answer": normalize_answer(answer),
    }, telemetry_record


def write_results(config: RuntimeConfig, results: list[dict]) -> None:
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
