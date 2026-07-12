import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.model_matrix import score_answer


REMOTE_ENV_NAMES = ("FIREWORKS_API_KEY", "FIREWORKS_BASE_URL", "ALLOWED_MODELS")
OPTIONAL_ENV_NAMES = (
    "FIREWORKS_DISABLE_MAX_TOKENS",
    "FIREWORKS_MAX_TOKENS",
    "FIREWORKS_MAX_TOKENS_BY_CATEGORY",
    "FIREWORKS_TIMEOUT_SECONDS",
    "FIREWORKS_MAX_RETRIES",
    "FIREWORKS_DEV_MODEL_MAP",
    "REMOTE_VALIDATION_ESCALATION_ENABLED",
    "ROUTER_MODELS_BY_CATEGORY",
    "ROUTER_MODELS_REMOTE_ACCURACY",
    "ROUTER_MODELS_REMOTE_CODE",
    "ROUTER_MODELS_REMOTE_CONCISE",
    "ROUTER_MODELS_REMOTE_ESCALATION",
    "ROUTER_MODELS_REMOTE_FORMAT_STRICT",
    "ROUTER_PROMPT_POLICY_BY_CATEGORY",
    "ROUTER_PROMPT_POLICY_REMOTE_ACCURACY",
    "ROUTER_PROMPT_POLICY_REMOTE_CODE",
    "ROUTER_PROMPT_POLICY_REMOTE_CONCISE",
    "ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT",
)

LOCAL_CATEGORIES_ALL = ",".join(
    (
        "factual_knowledge",
        "text_summarisation",
        "sentiment_classification",
        "named_entity_recognition",
        "mathematical_reasoning",
        "logical_deductive_reasoning",
        "code_generation",
        "code_debugging",
    )
)

LOCAL_CATEGORIES_TARGETED = ",".join(
    (
        "sentiment_classification",
        "text_summarisation",
        "code_debugging",
    )
)

MODE_CONFIGS = {
    "local_targeted_only": {
        "requires_remote": False,
        "env": {
            "LOCAL_MODEL_ENABLED": "true",
            "LOCAL_MODEL_BATCH_LIMIT": "1000",
            "LOCAL_MODEL_CATEGORIES": LOCAL_CATEGORIES_TARGETED,
            "ROUTER_PROFILE": "accuracy_gate",
            "ROUTER_MODE": "local_only",
        },
    },
    "local_only": {
        "requires_remote": False,
        "env": {
            "LOCAL_MODEL_ENABLED": "true",
            "LOCAL_MODEL_BATCH_LIMIT": "1000",
            "LOCAL_MODEL_CATEGORIES": LOCAL_CATEGORIES_ALL,
            "ROUTER_PROFILE": "accuracy_gate",
            "ROUTER_MODE": "local_only",
        },
    },
    "remote_only": {
        "requires_remote": True,
        "env": {
            "LOCAL_MODEL_ENABLED": "false",
            "LOCAL_MODEL_BATCH_LIMIT": "0",
            "ROUTER_PROFILE": "accuracy_gate",
            "ROUTER_MODE": "accuracy_first",
        },
    },
    "mixed_fast": {
        "requires_remote": True,
        "env": {
            "LOCAL_MODEL_ENABLED": "true",
            "LOCAL_MODEL_BATCH_LIMIT": "6",
            "LOCAL_MODEL_CATEGORIES": "sentiment_classification,text_summarisation",
            "ROUTER_PROFILE": "accuracy_gate",
            "ROUTER_MODE": "balanced",
        },
    },
    "mixed_targeted": {
        "requires_remote": True,
        "env": {
            "LOCAL_MODEL_ENABLED": "true",
            "LOCAL_MODEL_BATCH_LIMIT": "1000",
            "LOCAL_MODEL_CATEGORIES": LOCAL_CATEGORIES_TARGETED,
            "ROUTER_PROFILE": "accuracy_gate",
            "ROUTER_MODE": "balanced",
        },
    },
    "mixed_broad": {
        "requires_remote": True,
        "env": {
            "LOCAL_MODEL_ENABLED": "true",
            "LOCAL_MODEL_BATCH_LIMIT": "12",
            "LOCAL_MODEL_CATEGORIES": LOCAL_CATEGORIES_ALL,
            "ROUTER_PROFILE": "accuracy_gate",
            "ROUTER_MODE": "balanced",
        },
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare local, remote, and mixed Docker routing modes.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--input-dir", default="local_test/accuracy_gate_input")
    parser.add_argument("--tasks-file", help="Optional JSON/JSONL task file to convert into a mounted /input/tasks.json.")
    parser.add_argument("--out-dir", default="eval_runs/local_remote_compare")
    parser.add_argument("--platform", default="linux/amd64")
    parser.add_argument("--memory", default="4g")
    parser.add_argument("--cpus", default="2")
    parser.add_argument("--modes", default="local_targeted_only,local_only,mixed_targeted,remote_only,mixed_broad")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--min-pass-rate", type=float, default=0.0)
    parser.add_argument("--fail-under-min", action="store_true")
    parser.add_argument("--require-remote", action="store_true")
    parser.add_argument("--keep-outputs", action="store_true")
    args = parser.parse_args()

    out_dir = (ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.tasks_file:
        tasks_source = (ROOT / args.tasks_file).resolve()
        if not tasks_source.exists():
            print(f"ERROR: missing task file {tasks_source}", file=sys.stderr)
            return 2
        tasks = load_tasks(tasks_source)
        input_dir = out_dir / "_input"
        input_dir.mkdir(parents=True, exist_ok=True)
        tasks_path = input_dir / "tasks.json"
        tasks_path.write_text(json.dumps({"tasks": tasks}, indent=2), encoding="utf-8")
    else:
        input_dir = (ROOT / args.input_dir).resolve()
        tasks_path = input_dir / "tasks.json"
        tasks = load_tasks(tasks_path) if tasks_path.exists() else []
    if not tasks_path.exists():
        print(f"ERROR: missing fixture {tasks_path}", file=sys.stderr)
        return 2

    selected_modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    unknown = [mode for mode in selected_modes if mode not in MODE_CONFIGS]
    if unknown:
        print(f"ERROR: unknown modes: {', '.join(unknown)}", file=sys.stderr)
        return 2
    if args.runs < 1:
        print("ERROR: --runs must be >= 1", file=sys.stderr)
        return 2

    remote_ready = all(os.environ.get(name, "").strip() for name in REMOTE_ENV_NAMES)
    if args.require_remote and not remote_ready:
        print("ERROR: FIREWORKS_API_KEY, FIREWORKS_BASE_URL, and ALLOWED_MODELS are required", file=sys.stderr)
        return 3

    raw_runs = []
    for mode in selected_modes:
        mode_config = MODE_CONFIGS[mode]
        if mode_config["requires_remote"] and not remote_ready:
            raw_runs.append({"mode": mode, "run": None, "status": "skipped_missing_remote_env"})
            print(f"{mode}: skipped_missing_remote_env")
            continue
        for run_index in range(1, args.runs + 1):
            raw_runs.append(
                run_mode(
                    mode=mode,
                    run_index=run_index,
                    run_count=args.runs,
                    mode_env=mode_config["env"],
                    image=args.image,
                    input_dir=input_dir,
                    out_dir=out_dir,
                    tasks=tasks,
                    platform=args.platform,
                    memory=args.memory,
                    cpus=args.cpus,
                )
            )
    summaries = aggregate_mode_runs(raw_runs)

    summary_path = out_dir / "summary.json"
    md_path = out_dir / "summary.md"
    summary_payload = {
        "image": args.image,
        "input_dir": str(input_dir),
        "task_count": len(tasks),
        "runs_per_mode": args.runs,
        "min_pass_rate": args.min_pass_rate,
        "remote_env_present": remote_ready,
        "modes": summaries,
        "category_winners": category_winners(summaries),
        "raw_runs": raw_runs,
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(summary_payload), encoding="utf-8")

    print(f"JSON: {summary_path}")
    print(f"Markdown: {md_path}")
    if not args.keep_outputs:
        print("Mode outputs kept in:", out_dir)
    if args.fail_under_min:
        below = [
            row
            for row in summaries
            if row.get("status") == "passed" and float(row.get("pass_rate", 0.0)) < args.min_pass_rate
        ]
        if below:
            for row in below:
                print(
                    f"ERROR: {row['mode']} pass rate {row['pass_rate']:.1%} is below {args.min_pass_rate:.1%}",
                    file=sys.stderr,
                )
            return 9
    return 0


def run_mode(
    *,
    mode: str,
    run_index: int,
    run_count: int,
    mode_env: dict[str, str],
    image: str,
    input_dir: Path,
    out_dir: Path,
    tasks: list[dict],
    platform: str,
    memory: str,
    cpus: str,
) -> dict:
    mode_out = out_dir / mode
    if run_count > 1:
        mode_out = mode_out / f"run_{run_index:02d}"
    mode_out.mkdir(parents=True, exist_ok=True)
    for name in ("results.json", "router_log.jsonl", "stdout.txt", "stderr.txt"):
        path = mode_out / name
        if path.exists():
            path.unlink()

    env_args = {
        "ROUTER_LOG_PATH": "/output/router_log.jsonl",
        "LOCAL_MODEL_PATH": "/app/models/local-model.gguf",
        **mode_env,
    }
    if MODE_CONFIGS[mode]["requires_remote"]:
        for name in REMOTE_ENV_NAMES:
            value = os.environ.get(name, "")
            if value:
                env_args[name] = value
        for name in OPTIONAL_ENV_NAMES:
            value = os.environ.get(name, "")
            if value:
                env_args[name] = value

    cmd = [
        "docker",
        "run",
        "--rm",
        "--platform",
        platform,
        "--memory",
        memory,
        "--cpus",
        cpus,
    ]
    for name, value in env_args.items():
        cmd.extend(["-e", f"{name}={value}"])
    cmd.extend(
        [
            "-v",
            f"{input_dir}:/input:ro",
            "-v",
            f"{mode_out}:/output",
            image,
        ]
    )

    started = time.monotonic()
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    elapsed_seconds = time.monotonic() - started
    (mode_out / "stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (mode_out / "stderr.txt").write_text(proc.stderr, encoding="utf-8")

    results_path = mode_out / "results.json"
    log_path = mode_out / "router_log.jsonl"
    telemetry = load_jsonl(log_path)
    results = load_results_if_present(results_path)
    scored = score_results(tasks, results)
    route_counts = route_counter(telemetry)
    error_counts = value_counter(telemetry, ("fireworks_error", "error"))
    model_counts = value_counter(telemetry, ("selected_model",))
    reason_counts = value_counter(telemetry, ("route_reason",))
    startup = next((row for row in telemetry if row.get("event") == "startup"), {})
    finish = next((row for row in reversed(telemetry) if row.get("event") == "finish"), {})
    summary = {
        "mode": mode,
        "run": run_index,
        "status": "passed" if proc.returncode == 0 and results else "failed",
        "returncode": proc.returncode,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "app_batch_elapsed_seconds": round((finish.get("batch_elapsed_ms") or 0) / 1000, 3),
        "tasks_read": finish.get("tasks_read") or len(tasks),
        "answers_written": len(results),
        "pass_rate": scored["pass_rate"],
        "avg_score": scored["avg_score"],
        "route_counts": route_counts,
        "fireworks_count": finish.get("fireworks_count", route_counts.get("fireworks", 0)),
        "local_llm_count": finish.get("local_llm_count", route_counts.get("local_model", 0)),
        "fallbacks_count": finish.get("fallbacks_count", route_counts.get("fallback", 0)),
        "deterministic_count": finish.get("deterministic_count", route_counts.get("local", 0)),
        "error_counts": error_counts,
        "model_counts": model_counts,
        "route_reason_counts": reason_counts,
        "remote_env_seen": {
            "fireworks_api_key_present": bool(startup.get("fireworks_api_key_present")),
            "fireworks_base_url_present": bool(startup.get("fireworks_base_url_present")),
            "allowed_models_count": len(startup.get("allowed_models") or []),
        },
        "by_category": scored["by_category"],
        "by_difficulty": scored["by_difficulty"],
        "by_scenario_class": scored["by_scenario_class"],
        "failures": scored["failures"][:10],
        "task_scores": scored["rows"],
        "output_dir": str(mode_out),
    }
    print(
        f"{mode} run {run_index}/{run_count}: status={summary['status']} pass_rate={summary['pass_rate']:.1%} "
        f"elapsed={summary['elapsed_seconds']:.1f}s routes={summary['route_counts']}"
    )
    return summary


def aggregate_mode_runs(raw_runs: list[dict]) -> list[dict]:
    by_mode: dict[str, list[dict]] = defaultdict(list)
    skipped: dict[str, dict] = {}
    for row in raw_runs:
        if str(row.get("status", "")).startswith("skipped"):
            skipped[row["mode"]] = row
        else:
            by_mode[row["mode"]].append(row)

    summaries: list[dict] = []
    for mode in sorted(set(by_mode) | set(skipped)):
        runs = by_mode.get(mode, [])
        if not runs:
            summaries.append(skipped[mode])
            continue
        completed = [row for row in runs if row.get("status") == "passed"]
        source = completed or runs
        aggregate = {
            "mode": mode,
            "status": "passed" if completed and len(completed) == len(runs) else "failed",
            "runs": len(runs),
            "completed_runs": len(completed),
            "pass_rate": average(row.get("pass_rate", 0.0) for row in source),
            "avg_score": average(row.get("avg_score", 0.0) for row in source),
            "elapsed_seconds": average(row.get("elapsed_seconds", 0.0) for row in source),
            "max_elapsed_seconds": max(float(row.get("elapsed_seconds", 0.0)) for row in source),
            "answers_written": min(int(row.get("answers_written", 0)) for row in source),
            "fireworks_count": average(row.get("fireworks_count", 0.0) for row in source),
            "local_llm_count": average(row.get("local_llm_count", 0.0) for row in source),
            "fallbacks_count": average(row.get("fallbacks_count", 0.0) for row in source),
            "deterministic_count": average(row.get("deterministic_count", 0.0) for row in source),
            "route_counts": merge_average_counts(row.get("route_counts", {}) for row in source),
            "error_counts": merge_sum_counts(row.get("error_counts", {}) for row in source),
            "model_counts": merge_sum_counts(row.get("model_counts", {}) for row in source),
            "route_reason_counts": merge_sum_counts(row.get("route_reason_counts", {}) for row in source),
            "remote_env_seen": source[-1].get("remote_env_seen", {}),
            "by_category": aggregate_categories(source),
            "by_difficulty": aggregate_named_buckets(source, "by_difficulty"),
            "by_scenario_class": aggregate_named_buckets(source, "by_scenario_class"),
            "unstable_tasks": unstable_tasks(source),
            "failures": source[-1].get("failures", []),
            "output_dir": str(Path(source[-1].get("output_dir", "")).parent if len(source) > 1 else source[-1].get("output_dir", "")),
        }
        summaries.append(aggregate)
    return summaries


def average(values) -> float:
    numbers = [float(value) for value in values]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def merge_sum_counts(counts_list) -> dict[str, int]:
    merged = Counter()
    for counts in counts_list:
        merged.update({str(key): int(value) for key, value in dict(counts).items()})
    return {key: value for key, value in merged.most_common()}


def merge_average_counts(counts_list) -> dict[str, float]:
    rows = [dict(counts) for counts in counts_list]
    if not rows:
        return {}
    keys = sorted({str(key) for row in rows for key in row})
    return {
        key: round(sum(float(row.get(key, 0.0)) for row in rows) / len(rows), 3)
        for key in keys
    }


def aggregate_categories(runs: list[dict]) -> dict:
    return aggregate_named_buckets(runs, "by_category")


def category_winners(summaries: list[dict]) -> list[dict]:
    by_category: dict[str, list[dict]] = defaultdict(list)
    for summary in summaries:
        if summary.get("status") != "passed":
            continue
        for category, bucket in (summary.get("by_category") or {}).items():
            by_category[category].append(
                {
                    "category": category,
                    "mode": summary["mode"],
                    "pass_rate": float(bucket.get("pass_rate", 0.0)),
                    "avg_score": float(bucket.get("avg_score", 0.0)),
                    "avg_seconds": float(summary.get("elapsed_seconds", 0.0)),
                    "fireworks_count": float(summary.get("fireworks_count", 0.0)),
                    "local_llm_count": float(summary.get("local_llm_count", 0.0)),
                    "fallbacks_count": float(summary.get("fallbacks_count", 0.0)),
                }
            )

    winners = []
    for category, rows in sorted(by_category.items()):
        rows.sort(
            key=lambda row: (
                -row["pass_rate"],
                -row["avg_score"],
                row["fireworks_count"],
                row["avg_seconds"],
                row["fallbacks_count"],
                row["mode"],
            )
        )
        winner = rows[0]
        winner["alternatives"] = rows[1:4]
        winners.append(winner)
    return winners


def aggregate_named_buckets(runs: list[dict], key: str) -> dict:
    buckets = defaultdict(lambda: {"runs": 0, "rows": 0, "pass_rate": 0.0, "avg_score": 0.0})
    for run in runs:
        for name, bucket in (run.get(key) or {}).items():
            target = buckets[name]
            target["runs"] += 1
            target["rows"] = max(target["rows"], int(bucket.get("rows", 0)))
            target["pass_rate"] += float(bucket.get("pass_rate", 0.0))
            target["avg_score"] += float(bucket.get("avg_score", 0.0))
    return {
        name: {
            "rows": bucket["rows"],
            "runs": bucket["runs"],
            "pass_rate": bucket["pass_rate"] / max(1, bucket["runs"]),
            "avg_score": bucket["avg_score"] / max(1, bucket["runs"]),
        }
        for name, bucket in sorted(buckets.items())
    }


def unstable_tasks(runs: list[dict]) -> list[dict]:
    by_task = defaultdict(list)
    for run in runs:
        for row in run.get("task_scores") or []:
            by_task[row["task_id"]].append(row)

    unstable = []
    for task_id, rows in sorted(by_task.items()):
        if len(rows) <= 1:
            continue
        pass_values = [bool(row["passed"]) for row in rows]
        scores = [float(row["score"]) for row in rows]
        if len(set(pass_values)) > 1 or max(scores) - min(scores) >= 0.25:
            unstable.append(
                {
                    "task_id": task_id,
                    "category": rows[-1].get("category", "unknown"),
                    "difficulty": rows[-1].get("difficulty", "unknown"),
                    "scenario_class": rows[-1].get("scenario_class", "unknown"),
                    "pass_rate": sum(pass_values) / len(pass_values),
                    "min_score": min(scores),
                    "max_score": max(scores),
                    "latest_notes": rows[-1].get("notes", []),
                    "latest_answer_preview": str(rows[-1].get("answer", "")).replace("\n", "\\n")[:180],
                }
            )
    unstable.sort(key=lambda row: (row["pass_rate"], row["min_score"], row["task_id"]))
    return unstable


def score_results(tasks: list[dict], results: list[dict]) -> dict:
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
                "difficulty": task.get("difficulty", "unknown"),
                "scenario_class": task.get("scenario_class", "unknown"),
                "passed": bool(passed),
                "score": float(score),
                "notes": list(notes),
                "answer": answer,
            }
        )

    total = len(rows)
    pass_rate = sum(1 for row in rows if row["passed"]) / max(1, total)
    avg_score = sum(row["score"] for row in rows) / max(1, total)
    by_category = bucket_scores(rows, "category")
    by_difficulty = bucket_scores(rows, "difficulty")
    by_scenario_class = bucket_scores(rows, "scenario_class")
    failures = [
        {
            "task_id": row["task_id"],
            "category": row["category"],
            "difficulty": row["difficulty"],
            "scenario_class": row["scenario_class"],
            "score": row["score"],
            "notes": row["notes"],
            "answer_preview": str(row["answer"]).replace("\n", "\\n")[:220],
        }
        for row in rows
        if not row["passed"]
    ]
    return {
        "pass_rate": pass_rate,
        "avg_score": avg_score,
        "by_category": by_category,
        "by_difficulty": by_difficulty,
        "by_scenario_class": by_scenario_class,
        "failures": failures,
        "rows": rows,
    }


def bucket_scores(rows: list[dict], key: str) -> dict:
    buckets = defaultdict(lambda: {"rows": 0, "passed": 0, "score": 0.0})
    for row in rows:
        bucket = buckets[row.get(key) or "unknown"]
        bucket["rows"] += 1
        bucket["passed"] += int(row["passed"])
        bucket["score"] += row["score"]
    output = {}
    for name, bucket in sorted(buckets.items()):
        output[name] = {
            "rows": bucket["rows"],
            "pass_rate": bucket["passed"] / max(1, bucket["rows"]),
            "avg_score": bucket["score"] / max(1, bucket["rows"]),
        }
    return output


def route_counter(telemetry: list[dict]) -> dict[str, int]:
    counts = Counter(row.get("route") for row in telemetry if row.get("task_id"))
    return {str(key): value for key, value in sorted(counts.items()) if key}


def value_counter(telemetry: list[dict], keys: tuple[str, ...]) -> dict[str, int]:
    counts = Counter()
    for row in telemetry:
        if not row.get("task_id"):
            continue
        for key in keys:
            value = row.get(key)
            if value:
                counts[str(value)] += 1
                break
    return {key: value for key, value in counts.most_common()}


def load_tasks(path: Path) -> list[dict]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
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


def load_results_if_present(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def render_markdown(payload: dict) -> str:
    lines = [
        "# Local vs Remote Routing Comparison",
        "",
        f"Image: `{payload['image']}`",
        f"Tasks: {payload['task_count']}",
        f"Runs per mode: {payload.get('runs_per_mode', 1)}",
        f"Minimum pass rate target: {float(payload.get('min_pass_rate', 0.0)):.1%}",
        f"Remote env present: `{payload['remote_env_present']}`",
        "",
        "## Summary",
        "",
        "| Mode | Status | Runs | Pass Rate | Avg Score | Avg Seconds | Max Seconds | Fireworks | Local LLM | Fallbacks | Deterministic | Answers |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["modes"]:
        if row.get("status", "").startswith("skipped"):
            lines.append(f"| {row['mode']} | {row['status']} |  |  |  |  |  |  |  |  |  |  |")
            continue
        lines.append(
            "| {mode} | {status} | {completed_runs}/{runs} | {pass_rate:.1%} | {avg_score:.3f} | {elapsed_seconds:.1f} | "
            "{max_elapsed_seconds:.1f} | {fireworks_count:.1f} | {local_llm_count:.1f} | {fallbacks_count:.1f} | "
            "{deterministic_count:.1f} | {answers_written} |".format(
                **row
            )
        )
    lines.extend(["", "## Category Scores", ""])
    for row in payload["modes"]:
        if "by_category" not in row:
            continue
        lines.extend([f"### {row['mode']}", "", "| Category | Pass Rate | Avg Score | Rows | Runs |", "| --- | ---: | ---: | ---: | ---: |"])
        for category, bucket in row["by_category"].items():
            lines.append(
                f"| {category} | {bucket['pass_rate']:.1%} | {bucket['avg_score']:.3f} | {bucket['rows']} | {bucket.get('runs', 1)} |"
            )
        lines.append("")
    winners = payload.get("category_winners") or []
    if winners:
        lines.extend(["## Category Winners", ""])
        lines.append("| Category | Best Mode | Pass Rate | Avg Score | Avg Seconds | Fireworks | Local LLM | Fallbacks |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for winner in winners:
            lines.append(
                "| {category} | {mode} | {pass_rate:.1%} | {avg_score:.3f} | {avg_seconds:.1f} | "
                "{fireworks_count:.1f} | {local_llm_count:.1f} | {fallbacks_count:.1f} |".format(**winner)
            )
        lines.append("")
    lines.extend(["## Difficulty Scores", ""])
    for row in payload["modes"]:
        if "by_difficulty" not in row:
            continue
        lines.extend([f"### {row['mode']}", "", "| Difficulty | Pass Rate | Avg Score | Rows | Runs |", "| --- | ---: | ---: | ---: | ---: |"])
        for difficulty, bucket in row["by_difficulty"].items():
            lines.append(
                f"| {difficulty} | {bucket['pass_rate']:.1%} | {bucket['avg_score']:.3f} | {bucket['rows']} | {bucket.get('runs', 1)} |"
            )
        lines.append("")
    lines.extend(["## Scenario Class Scores", ""])
    for row in payload["modes"]:
        if "by_scenario_class" not in row:
            continue
        lines.extend([f"### {row['mode']}", "", "| Scenario Class | Pass Rate | Avg Score | Rows | Runs |", "| --- | ---: | ---: | ---: | ---: |"])
        for scenario_class, bucket in row["by_scenario_class"].items():
            lines.append(
                f"| {scenario_class} | {bucket['pass_rate']:.1%} | {bucket['avg_score']:.3f} | {bucket['rows']} | {bucket.get('runs', 1)} |"
            )
        lines.append("")
    lines.extend(["## Models And Errors", ""])
    for row in payload["modes"]:
        if row.get("status", "").startswith("skipped"):
            continue
        lines.append(f"### {row['mode']}")
        model_counts = row.get("model_counts") or {}
        error_counts = row.get("error_counts") or {}
        if model_counts:
            lines.append("Models: " + ", ".join(f"`{key}`={value}" for key, value in list(model_counts.items())[:8]))
        else:
            lines.append("Models: none")
        if error_counts:
            lines.append("Errors: " + ", ".join(f"`{key}`={value}" for key, value in list(error_counts.items())[:8]))
        else:
            lines.append("Errors: none")
        lines.append("")
    lines.extend(["## Unstable Tasks", ""])
    for row in payload["modes"]:
        unstable = row.get("unstable_tasks") or []
        if not unstable:
            continue
        lines.append(f"### {row['mode']}")
        for task in unstable[:12]:
            notes = ";".join(task.get("latest_notes") or [])
            lines.append(
                f"- `{task['task_id']}` ({task['category']}, {task.get('difficulty', 'unknown')}, {task.get('scenario_class', 'unknown')}): "
                f"pass_rate={task['pass_rate']:.1%}; "
                f"score_range={task['min_score']:.3f}-{task['max_score']:.3f}; notes={notes}; "
                f"answer={task['latest_answer_preview']}"
            )
        lines.append("")
    lines.extend(["## First Failures", ""])
    for row in payload["modes"]:
        failures = row.get("failures") or []
        if not failures:
            continue
        lines.append(f"### {row['mode']}")
        for failure in failures[:10]:
            notes = ";".join(failure["notes"])
            lines.append(
                f"- `{failure['task_id']}` ({failure['category']}, {failure.get('difficulty', 'unknown')}, "
                f"{failure.get('scenario_class', 'unknown')}): score={failure['score']:.3f}; "
                f"notes={notes}; answer={failure['answer_preview']}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
