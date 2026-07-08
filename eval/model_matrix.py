import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_live_eval_env import validate_live_eval_env


ALLOWED_TRACK1_MODELS = [
    "minimax-m3",
    "kimi-k2p7-code",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
    "gemma-4-31b-it-nvfp4",
]

DEFAULT_SCENARIOS = Path(__file__).with_name("model_matrix_scenarios.jsonl")
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[1] / "eval_runs"
PROMPT_POLICIES = ("original", "compact", "answer_only")
NORMAL_FIREWORKS_HOST = "api." + "fireworks.ai"


def load_scenarios(path):
    scenarios = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                scenarios.append(json.loads(line))
    return scenarios


def limit_scenarios(scenarios, limit):
    if limit is None:
        return scenarios
    return scenarios[:limit]


def env_models():
    raw = os.environ.get("ALLOWED_MODELS", "")
    models = [model.strip() for model in raw.split(",") if model.strip()]
    return models or ALLOWED_TRACK1_MODELS


def normal_fireworks_dev_enabled(allow_normal_fireworks_dev=False):
    if not allow_normal_fireworks_dev:
        return False
    base_url = os.environ.get("FIREWORKS_BASE_URL", "").strip()
    return urlparse(base_url).netloc == NORMAL_FIREWORKS_HOST


def parse_dev_model_map(raw):
    mapping = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError("FIREWORKS_DEV_MODEL_MAP entries must use alias=provider_model")
        alias, provider_model = item.split("=", 1)
        alias = alias.strip()
        provider_model = provider_model.strip()
        if not alias or not provider_model:
            raise ValueError("FIREWORKS_DEV_MODEL_MAP entries must not be empty")
        mapping[alias] = provider_model
    return mapping


def provider_model_for(alias, allow_normal_fireworks_dev=False):
    if not normal_fireworks_dev_enabled(allow_normal_fireworks_dev):
        return alias
    mapping = parse_dev_model_map(os.environ.get("FIREWORKS_DEV_MODEL_MAP", ""))
    return mapping.get(alias, alias)


def estimate_tokens(text):
    return max(1, (len(text) + 3) // 4)


def prompt_for_policy(scenario, policy):
    prompt = scenario["prompt"]
    if policy == "original":
        return prompt
    if policy == "compact":
        return "Answer the task accurately and concisely. Preserve all constraints.\n\nTask:\n" + prompt
    if policy == "answer_only":
        return "Return only the final answer. Preserve exact requested format.\n\nTask:\n" + prompt
    raise ValueError(f"Unknown prompt policy: {policy}")


def score_answer(answer, scenario):
    verifier = scenario.get("verifier")
    expected_answer = str(scenario.get("expected_answer", "")).strip()
    answer_text = str(answer or "").strip()
    answer_lower = answer_text.lower()

    if verifier == "label_set" and expected_answer:
        expected_label = expected_answer.lower()
        passed = expected_label in answer_lower.split() or answer_lower.startswith(expected_label)
        return passed, 1.0 if passed else 0.0, [] if passed else [f"expected_label={expected_answer}"]

    if verifier == "numeric_exact" and expected_answer:
        expected_numbers = _numbers(expected_answer)
        answer_numbers = _numbers(answer_text)
        passed = bool(expected_numbers) and expected_numbers[0] in answer_numbers
        return passed, 1.0 if passed else 0.0, [] if passed else [f"expected_number={expected_numbers[0] if expected_numbers else expected_answer}"]

    expected_keywords = scenario.get("expected_keywords", [])
    matches = [keyword for keyword in expected_keywords if keyword.lower() in answer_lower]
    score = len(matches) / max(1, len(expected_keywords))
    threshold = 0.66 if verifier == "summary_constraints" else 0.75
    passed = score >= threshold
    notes = []
    matched_lower = {keyword.lower() for keyword in matches}
    missing = [keyword for keyword in expected_keywords if keyword.lower() not in matched_lower]
    if missing:
        notes.append("missing_keywords=" + ",".join(missing))
    return passed, round(score, 3), notes


def _numbers(text):
    values = []
    for raw in re.findall(r"-?\d+(?:\.\d+)?", text):
        value = float(raw)
        values.append(str(int(value)) if value.is_integer() else str(value))
    return values


def mock_answer(model, scenario):
    expected = scenario.get("expected_answer", "")
    category = scenario["category"]
    if model == "kimi-k2p7-code" and category in {"code_debugging", "code_generation"}:
        return expected
    if model.startswith("gemma") and category in {"text_summarisation", "sentiment_classification", "factual_knowledge"}:
        return expected
    if model == "minimax-m3" and category in {"mathematical_reasoning", "named_entity_recognition", "logical_deductive_reasoning"}:
        return expected
    if model == "gemma-4-31b-it-nvfp4":
        return expected if category != "code_generation" else "def solution(...): pass"
    return expected


def call_fireworks(model, scenario, prompt, max_tokens, allow_normal_fireworks_dev=False):
    api_key = os.environ["FIREWORKS_API_KEY"]
    base_url = os.environ["FIREWORKS_BASE_URL"].rstrip("/")
    url = base_url + "/chat/completions"
    provider_model = provider_model_for(model, allow_normal_fireworks_dev)
    payload = {
        "model": provider_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Answer accurately and concisely in English. "
                    "Follow the requested output format exactly."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    answer = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    return answer, {
        "prompt_tokens": usage.get("prompt_tokens", estimate_tokens(prompt)),
        "completion_tokens": usage.get("completion_tokens", estimate_tokens(answer)),
        "total_tokens": usage.get("total_tokens"),
    }, provider_model


def format_http_error(exc):
    body = ""
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    if len(body) > 500:
        body = body[:500] + "..."
    suffix = f" body={body}" if body else ""
    return f"HTTPError: HTTP Error {exc.code}: {exc.reason}{suffix}"


def run_case(model, scenario, live, max_tokens, prompt_policy, allow_normal_fireworks_dev=False):
    start = time.perf_counter()
    error = None
    prompt = prompt_for_policy(scenario, prompt_policy)
    provider_model = provider_model_for(model, allow_normal_fireworks_dev)
    if live:
        try:
            answer, usage, provider_model = call_fireworks(
                model,
                scenario,
                prompt,
                max_tokens,
                allow_normal_fireworks_dev=allow_normal_fireworks_dev,
            )
        except urllib.error.HTTPError as exc:
            answer = ""
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            error = format_http_error(exc)
        except (KeyError, urllib.error.URLError, TimeoutError, ValueError) as exc:
            answer = ""
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            error = f"{type(exc).__name__}: {exc}"
    else:
        answer = mock_answer(model, scenario)
        usage = {
            "prompt_tokens": estimate_tokens(prompt),
            "completion_tokens": estimate_tokens(answer),
            "total_tokens": estimate_tokens(prompt) + estimate_tokens(answer),
        }
    if usage.get("total_tokens") is None:
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    latency_ms = (time.perf_counter() - start) * 1000
    passed, score, notes = score_answer(answer, scenario)
    if error:
        passed = False
        score = 0.0
        notes.append(error)
    return {
        "task_id": scenario["task_id"],
        "category": scenario["category"],
        "difficulty": scenario.get("difficulty"),
        "scenario_class": scenario.get("scenario_class"),
        "intent": scenario.get("intent"),
        "answer_shape": scenario.get("answer_shape"),
        "constraints": scenario.get("constraints", []),
        "risk_components": scenario.get("risk_components", []),
        "output_constraints": scenario.get("output_constraints", []),
        "expected_route": scenario.get("expected_route"),
        "remote_mode_hint": scenario.get("remote_mode_hint"),
        "verifier": scenario.get("verifier"),
        "retry_policy": scenario.get("retry_policy"),
        "failure_taxonomy": scenario.get("failure_taxonomy", []),
        "model": model,
        "provider_model": provider_model,
        "prompt_policy": prompt_policy,
        "prompt_chars": len(prompt),
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "total_tokens": usage["total_tokens"],
        "latency_ms": round(latency_ms, 2),
        "passed": passed,
        "score": score,
        "answer": answer,
        "expected_answer": scenario.get("expected_answer"),
        "notes": notes,
        "error": error,
    }


def summarize(rows):
    by_model = defaultdict(lambda: {"cases": 0, "passed": 0, "score": 0.0, "tokens": 0, "latency": 0.0})
    by_model_category = defaultdict(lambda: {"cases": 0, "passed": 0, "score": 0.0, "tokens": 0})
    by_policy = defaultdict(lambda: {"cases": 0, "passed": 0, "score": 0.0, "tokens": 0})
    for row in rows:
        model_row = by_model[row["model"]]
        model_row["cases"] += 1
        model_row["passed"] += int(row["passed"])
        model_row["score"] += row["score"]
        model_row["tokens"] += row["total_tokens"]
        model_row["latency"] += row["latency_ms"]

        key = (row["model"], row["category"])
        category_row = by_model_category[key]
        category_row["cases"] += 1
        category_row["passed"] += int(row["passed"])
        category_row["score"] += row["score"]
        category_row["tokens"] += row["total_tokens"]

        policy_row = by_policy[row["prompt_policy"]]
        policy_row["cases"] += 1
        policy_row["passed"] += int(row["passed"])
        policy_row["score"] += row["score"]
        policy_row["tokens"] += row["total_tokens"]
    return by_model, by_model_category, by_policy


def write_report(path, rows, live):
    by_model, by_model_category, by_policy = summarize(rows)
    lines = [
        "# Track 1 Model Matrix Report",
        "",
        f"Mode: {'live Fireworks' if live else 'mock'}",
        "",
        "## Summary by Model",
        "",
        "| Model | Cases | Pass Rate | Avg Score | Total Tokens | Avg Tokens | Avg Latency ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for model, data in sorted(by_model.items()):
        cases = data["cases"]
        lines.append(
            f"| {model} | {cases} | {data['passed'] / cases:.1%} | "
            f"{data['score'] / cases:.3f} | {data['tokens']} | "
            f"{data['tokens'] / cases:.1f} | {data['latency'] / cases:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Summary by Model and Category",
            "",
            "| Model | Category | Cases | Pass Rate | Avg Score | Total Tokens |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for (model, category), data in sorted(by_model_category.items()):
        cases = data["cases"]
        lines.append(
            f"| {model} | {category} | {cases} | {data['passed'] / cases:.1%} | "
            f"{data['score'] / cases:.3f} | {data['tokens']} |"
        )
    lines.extend(
        [
            "",
            "## Summary by Prompt Policy",
            "",
            "| Prompt Policy | Cases | Pass Rate | Avg Score | Total Tokens | Avg Tokens |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for policy, data in sorted(by_policy.items()):
        cases = data["cases"]
        lines.append(
            f"| {policy} | {cases} | {data['passed'] / cases:.1%} | "
            f"{data['score'] / cases:.3f} | {data['tokens']} | {data['tokens'] / cases:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Provisional Routing Recommendation",
            "",
        ]
    )
    categories = sorted({row["category"] for row in rows})
    for category in categories:
        candidates = [row for row in rows if row["category"] == category]
        model_scores = defaultdict(lambda: {"score": 0.0, "tokens": 0, "cases": 0})
        for row in candidates:
            item = model_scores[row["model"]]
            item["score"] += row["score"]
            item["tokens"] += row["total_tokens"]
            item["cases"] += 1
        ranked = sorted(
            model_scores.items(),
            key=lambda item: (-(item[1]["score"] / item[1]["cases"]), item[1]["tokens"] / item[1]["cases"]),
        )
        best_model, best_data = ranked[0]
        lines.append(
            f"- {category}: `{best_model}` "
            f"(avg_score={best_data['score'] / best_data['cases']:.3f}, "
            f"avg_tokens={best_data['tokens'] / best_data['cases']:.1f})"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run Track 1 allowed-model matrix experiments.")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--models", default=",".join(ALLOWED_TRACK1_MODELS))
    parser.add_argument(
        "--prompt-policies",
        default="original",
        help="Comma-separated prompt policies: original, compact, answer_only, or all.",
    )
    parser.add_argument("--live", action="store_true", help="Call Fireworks through FIREWORKS_BASE_URL.")
    parser.add_argument(
        "--allow-normal-fireworks-dev",
        action="store_true",
        help="Development only: allow --live against the normal Fireworks API when the judging proxy is unavailable.",
    )
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N scenarios for smoke tests.")
    args = parser.parse_args()

    requested_models = [model.strip() for model in args.models.split(",") if model.strip()]
    allowed = set(env_models())
    models = [model for model in requested_models if model in allowed]
    if not models:
        raise SystemExit("No requested models are present in ALLOWED_MODELS.")
    if args.live:
        env_errors = validate_live_eval_env(
            os.environ,
            allow_normal_fireworks_dev=args.allow_normal_fireworks_dev,
        )
        if env_errors:
            raise SystemExit("--live environment is not ready: " + "; ".join(env_errors))
        if args.allow_normal_fireworks_dev:
            print("WARNING: normal Fireworks dev override is enabled; results are not judging-proxy token data.")
    if args.prompt_policies.strip() == "all":
        prompt_policies = list(PROMPT_POLICIES)
    else:
        prompt_policies = [policy.strip() for policy in args.prompt_policies.split(",") if policy.strip()]
    invalid_policies = [policy for policy in prompt_policies if policy not in PROMPT_POLICIES]
    if invalid_policies:
        raise SystemExit(f"Unknown prompt policies: {', '.join(invalid_policies)}")

    scenarios = limit_scenarios(load_scenarios(args.scenarios), args.limit)
    run_id = datetime.now(timezone.utc).strftime("model_matrix_%Y%m%d_%H%M%S")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.out_dir / f"{run_id}.jsonl"
    report_path = args.out_dir / f"{run_id}.md"

    rows = []
    with log_path.open("x", encoding="utf-8") as handle:
        for model in models:
            for scenario in scenarios:
                for prompt_policy in prompt_policies:
                    row = run_case(
                        model,
                        scenario,
                        args.live,
                        args.max_tokens,
                        prompt_policy,
                        allow_normal_fireworks_dev=args.allow_normal_fireworks_dev,
                    )
                    row["run_id"] = run_id
                    row["timestamp"] = datetime.now(timezone.utc).isoformat()
                    rows.append(row)
                    handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    write_report(report_path, rows, args.live)
    print(f"Mode: {'live' if args.live else 'mock'}")
    print(f"Models: {', '.join(models)}")
    print(f"Prompt policies: {', '.join(prompt_policies)}")
    print(f"Scenarios: {len(scenarios)}")
    print(f"Rows: {len(rows)}")
    print(f"Log: {log_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
