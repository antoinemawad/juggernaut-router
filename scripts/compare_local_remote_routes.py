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

MODE_CONFIGS = {
    "local_only": {
        "requires_remote": False,
        "env": {
            "LOCAL_MODEL_ENABLED": "true",
            "LOCAL_MODEL_BATCH_LIMIT": "1000",
            "LOCAL_MODEL_CATEGORIES": LOCAL_CATEGORIES_ALL,
            "ROUTER_PROFILE": "accuracy_gate",
            "ROUTER_MODE": "accuracy_first",
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
    parser.add_argument("--out-dir", default="eval_runs/local_remote_compare")
    parser.add_argument("--platform", default="linux/amd64")
    parser.add_argument("--memory", default="4g")
    parser.add_argument("--cpus", default="2")
    parser.add_argument("--modes", default="local_only,remote_only,mixed_fast,mixed_broad")
    parser.add_argument("--require-remote", action="store_true")
    parser.add_argument("--keep-outputs", action="store_true")
    args = parser.parse_args()

    input_dir = (ROOT / args.input_dir).resolve()
    tasks_path = input_dir / "tasks.json"
    if not tasks_path.exists():
        print(f"ERROR: missing fixture {tasks_path}", file=sys.stderr)
        return 2

    selected_modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    unknown = [mode for mode in selected_modes if mode not in MODE_CONFIGS]
    if unknown:
        print(f"ERROR: unknown modes: {', '.join(unknown)}", file=sys.stderr)
        return 2

    out_dir = (ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    tasks = load_tasks(tasks_path)
    remote_ready = all(os.environ.get(name, "").strip() for name in REMOTE_ENV_NAMES)
    if args.require_remote and not remote_ready:
        print("ERROR: FIREWORKS_API_KEY, FIREWORKS_BASE_URL, and ALLOWED_MODELS are required", file=sys.stderr)
        return 3

    summaries = []
    for mode in selected_modes:
        mode_config = MODE_CONFIGS[mode]
        if mode_config["requires_remote"] and not remote_ready:
            summaries.append({"mode": mode, "status": "skipped_missing_remote_env"})
            print(f"{mode}: skipped_missing_remote_env")
            continue
        summaries.append(
            run_mode(
                mode=mode,
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

    summary_path = out_dir / "summary.json"
    md_path = out_dir / "summary.md"
    summary_payload = {
        "image": args.image,
        "input_dir": str(input_dir),
        "task_count": len(tasks),
        "remote_env_present": remote_ready,
        "modes": summaries,
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(summary_payload), encoding="utf-8")

    print(f"JSON: {summary_path}")
    print(f"Markdown: {md_path}")
    if not args.keep_outputs:
        print("Mode outputs kept in:", out_dir)
    return 0


def run_mode(
    *,
    mode: str,
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
    if mode != "local_only":
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
    startup = next((row for row in telemetry if row.get("event") == "startup"), {})
    finish = next((row for row in reversed(telemetry) if row.get("event") == "finish"), {})
    summary = {
        "mode": mode,
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
        "remote_env_seen": {
            "fireworks_api_key_present": bool(startup.get("fireworks_api_key_present")),
            "fireworks_base_url_present": bool(startup.get("fireworks_base_url_present")),
            "allowed_models_count": len(startup.get("allowed_models") or []),
        },
        "by_category": scored["by_category"],
        "failures": scored["failures"][:10],
        "output_dir": str(mode_out),
    }
    print(
        f"{mode}: status={summary['status']} pass_rate={summary['pass_rate']:.1%} "
        f"elapsed={summary['elapsed_seconds']:.1f}s routes={summary['route_counts']}"
    )
    return summary


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
                "passed": bool(passed),
                "score": float(score),
                "notes": list(notes),
                "answer": answer,
            }
        )

    total = len(rows)
    pass_rate = sum(1 for row in rows if row["passed"]) / max(1, total)
    avg_score = sum(row["score"] for row in rows) / max(1, total)
    buckets = defaultdict(lambda: {"rows": 0, "passed": 0, "score": 0.0})
    for row in rows:
        bucket = buckets[row["category"]]
        bucket["rows"] += 1
        bucket["passed"] += int(row["passed"])
        bucket["score"] += row["score"]
    by_category = {}
    for category, bucket in sorted(buckets.items()):
        by_category[category] = {
            "rows": bucket["rows"],
            "pass_rate": bucket["passed"] / max(1, bucket["rows"]),
            "avg_score": bucket["score"] / max(1, bucket["rows"]),
        }
    failures = [
        {
            "task_id": row["task_id"],
            "category": row["category"],
            "score": row["score"],
            "notes": row["notes"],
            "answer_preview": str(row["answer"]).replace("\n", "\\n")[:220],
        }
        for row in rows
        if not row["passed"]
    ]
    return {"pass_rate": pass_rate, "avg_score": avg_score, "by_category": by_category, "failures": failures}


def route_counter(telemetry: list[dict]) -> dict[str, int]:
    counts = Counter(row.get("route") for row in telemetry if row.get("task_id"))
    return {str(key): value for key, value in sorted(counts.items()) if key}


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
        f"Remote env present: `{payload['remote_env_present']}`",
        "",
        "## Summary",
        "",
        "| Mode | Status | Pass Rate | Avg Score | Seconds | Fireworks | Local LLM | Fallbacks | Deterministic | Answers |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["modes"]:
        if row.get("status", "").startswith("skipped"):
            lines.append(f"| {row['mode']} | {row['status']} |  |  |  |  |  |  |  |  |")
            continue
        lines.append(
            "| {mode} | {status} | {pass_rate:.1%} | {avg_score:.3f} | {elapsed_seconds:.1f} | "
            "{fireworks_count} | {local_llm_count} | {fallbacks_count} | {deterministic_count} | {answers_written} |".format(
                **row
            )
        )
    lines.extend(["", "## Category Scores", ""])
    for row in payload["modes"]:
        if "by_category" not in row:
            continue
        lines.extend([f"### {row['mode']}", "", "| Category | Pass Rate | Avg Score | Rows |", "| --- | ---: | ---: | ---: |"])
        for category, bucket in row["by_category"].items():
            lines.append(
                f"| {category} | {bucket['pass_rate']:.1%} | {bucket['avg_score']:.3f} | {bucket['rows']} |"
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
                f"- `{failure['task_id']}` ({failure['category']}): score={failure['score']:.3f}; "
                f"notes={notes}; answer={failure['answer_preview']}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
