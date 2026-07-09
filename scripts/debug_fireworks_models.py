import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import DEFAULT_ALLOWED_PLANNING_MODELS, parse_allowed_models
from eval.model_matrix import classify_access_error


NORMAL_FIREWORKS_HOST = "api." + "fireworks.ai"
NORMAL_FIREWORKS_BASE_URL = "https://" + NORMAL_FIREWORKS_HOST + "/inference/v1"
MANAGEMENT_API_BASE_URL = "https://" + NORMAL_FIREWORKS_HOST + "/v1"
NOT_READY_STATES = {"creating", "initializing", "starting", "pending", "provisioning"}
READY_STATES = {"ready", "running", "active", "deployed", "available", "started"}


@dataclass
class CallResult:
    status: str
    http_status: int | None = None
    error: str | None = None
    answer: str = ""
    latency_ms: float = 0.0


def official_model_path(alias: str) -> str:
    return f"accounts/fireworks/models/{alias}"


def auth_headers() -> dict[str, str]:
    api_key = os.environ.get("FIREWORKS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("FIREWORKS_API_KEY is missing")
    return {"Authorization": f"Bearer {api_key}"}


def format_http_error(exc: urllib.error.HTTPError) -> tuple[str, str]:
    body = ""
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    status = classify_access_error(f"HTTPError: HTTP Error {exc.code}: {exc.reason} body={body}")
    return status, f"HTTPError: HTTP Error {exc.code}: {exc.reason}" + (f" body={body[:500]}" if body else "")


def deployment_state(value: object) -> str:
    return str(value or "").strip().lower()


def is_not_ready_state(state: str | None, status: str | None = None) -> bool:
    values = {deployment_state(state), deployment_state(status)}
    return bool(values & NOT_READY_STATES)


def is_ready_state(state: str | None, status: str | None = None) -> bool:
    values = {deployment_state(state), deployment_state(status)}
    return bool(values & READY_STATES)


def normalize_deployment(raw: dict) -> dict:
    return {
        "name": raw.get("name"),
        "displayName": raw.get("displayName"),
        "baseModel": raw.get("baseModel"),
        "state": raw.get("state"),
        "status": raw.get("status"),
        "desiredReplicaCount": raw.get("desiredReplicaCount"),
        "directRouteHandle": raw.get("directRouteHandle"),
        "directRouteType": raw.get("directRouteType"),
        "activeModelVersion": raw.get("activeModelVersion"),
    }


def deployment_matches_model(deployment: dict, alias: str) -> bool:
    needle = alias.lower()
    official = official_model_path(alias).lower()
    for key in ("name", "displayName", "baseModel", "directRouteHandle", "activeModelVersion"):
        value = str(deployment.get(key) or "").lower()
        if needle in value or official in value:
            return True
    return False


def related_deployments(deployments: list[dict], alias: str) -> list[dict]:
    return [deployment for deployment in deployments if deployment_matches_model(deployment, alias)]


def load_deployments(account_id: str) -> list[dict]:
    url = f"{MANAGEMENT_API_BASE_URL}/accounts/{account_id}/deployments"
    request = urllib.request.Request(url, headers=auth_headers())
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    items = payload.get("deployments") or payload.get("data") or payload.get("results") or payload
    if not isinstance(items, list):
        return []
    return [normalize_deployment(item) for item in items if isinstance(item, dict)]


def wait_for_deployments(account_id: str, models: list[str], timeout_seconds: int, poll_interval_seconds: int) -> list[dict]:
    deadline = time.time() + timeout_seconds
    latest: list[dict] = []
    while True:
        latest = load_deployments(account_id)
        all_known_ready = True
        for model in models:
            related = related_deployments(latest, model)
            if not related:
                all_known_ready = False
                continue
            if not any(is_ready_state(item.get("state"), item.get("status")) for item in related):
                all_known_ready = False
        if all_known_ready or time.time() >= deadline:
            return latest
        time.sleep(max(1, poll_interval_seconds))


def call_chat_model(model_path: str, deployment_not_ready_hint: bool = False) -> CallResult:
    payload = {
        "model": model_path,
        "messages": [{"role": "user", "content": "Return exactly: OK"}],
        "max_tokens": 16,
        "temperature": 0,
    }
    request = urllib.request.Request(
        NORMAL_FIREWORKS_BASE_URL.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={**auth_headers(), "Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        elapsed_ms = (time.perf_counter() - start) * 1000
        answer = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        return CallResult(status="ok", http_status=200, answer=str(answer).strip(), latency_ms=round(elapsed_ms, 2))
    except urllib.error.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        status, error = format_http_error(exc)
        if status == "not_found_or_no_access" and deployment_not_ready_hint:
            status = "deployment_not_ready"
        return CallResult(status=status, http_status=exc.code, error=error, latency_ms=round(elapsed_ms, 2))
    except TimeoutError as exc:
        return CallResult(status="timeout", error=f"TimeoutError: {exc}")
    except urllib.error.URLError as exc:
        return CallResult(status="network_error", error=f"URLError: {exc}")
    except Exception as exc:
        return CallResult(status="unknown_error", error=f"{type(exc).__name__}: {exc}")


def private_deployment_path(account_id: str, deployment: dict) -> str | None:
    name = deployment.get("name")
    if not name:
        return None
    tail = str(name).rstrip("/").split("/")[-1]
    return f"accounts/{account_id}/deployments/{tail}"


def evaluate_model(alias: str, deployments: list[dict], account_id: str | None, test_private_deployments: bool) -> dict:
    related = related_deployments(deployments, alias)
    not_ready = any(is_not_ready_state(item.get("state"), item.get("status")) for item in related)
    ready = any(is_ready_state(item.get("state"), item.get("status")) for item in related)
    official_path = official_model_path(alias)
    official = call_chat_model(official_path, deployment_not_ready_hint=not_ready)
    candidates = [{
        "kind": "official_model_path",
        "model_path": official_path,
        "status": official.status,
        "http_status": official.http_status,
        "answer": official.answer,
        "latency_ms": official.latency_ms,
        "error": official.error,
    }]
    if test_private_deployments and account_id:
        for deployment in related:
            path = private_deployment_path(account_id, deployment)
            if not path:
                continue
            result = call_chat_model(path, deployment_not_ready_hint=is_not_ready_state(deployment.get("state"), deployment.get("status")))
            candidates.append({
                "kind": "private_deployment_path",
                "model_path": path,
                "status": result.status,
                "http_status": result.http_status,
                "answer": result.answer,
                "latency_ms": result.latency_ms,
                "error": result.error,
            })
    status = official.status
    if status == "not_found_or_no_access" and not_ready:
        status = "deployment_not_ready"
        candidates[0]["status"] = status
    return {
        "alias": alias,
        "status": status,
        "official_model_path": official_path,
        "deployment_summary": {
            "related_count": len(related),
            "any_ready": ready,
            "any_not_ready": not_ready,
        },
        "deployments": related,
        "candidates": candidates,
    }


def render_markdown(payload: dict) -> str:
    lines = [
        "# Fireworks Model Access Diagnostics",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Summary",
        "",
        "| Model Alias | Status | Related Deployments | Ready | Not Ready |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for result in payload["results"]:
        summary = result["deployment_summary"]
        lines.append(
            f"| {result['alias']} | `{result['status']}` | {summary['related_count']} | "
            f"{'yes' if summary['any_ready'] else 'no'} | {'yes' if summary['any_not_ready'] else 'no'} |"
        )
    lines.extend([
        "",
        "## Live Test Commands",
        "",
        "```bash",
        "python3 scripts/debug_fireworks_models.py --models kimi-k2p7-code --out-json eval_runs/access_kimi_k2p7.json --out-md eval_runs/access_kimi_k2p7.md",
        "python3 scripts/debug_fireworks_models.py --models minimax-m3 --out-json eval_runs/access_minimax_m3.json --out-md eval_runs/access_minimax_m3.md",
        "python3 scripts/debug_fireworks_models.py --models gemma-4-26b-a4b-it --account-id antoinemawad-j26hhi0 --check-deployments --wait-for-deployment-ready --wait-timeout-seconds 1800 --poll-interval-seconds 30 --out-json eval_runs/access_gemma_4_26b_a4b_it.json --out-md eval_runs/access_gemma_4_26b_a4b_it.md",
        "```",
        "",
        "## Details",
        "",
    ])
    for result in payload["results"]:
        lines.extend([f"### {result['alias']}", ""])
        for candidate in result["candidates"]:
            lines.append(
                f"- `{candidate['kind']}` `{candidate['model_path']}`: `{candidate['status']}`"
                + (f" HTTP {candidate['http_status']}" if candidate.get("http_status") else "")
            )
            if candidate.get("error"):
                lines.append(f"  - Error: `{candidate['error']}`")
        if result["deployments"]:
            lines.append("")
            lines.append("| name | displayName | baseModel | state | status | desiredReplicaCount | directRouteHandle | directRouteType | activeModelVersion |")
            lines.append("| --- | --- | --- | --- | --- | ---: | --- | --- | --- |")
            for item in result["deployments"]:
                lines.append(
                    f"| {item.get('name') or ''} | {item.get('displayName') or ''} | {item.get('baseModel') or ''} | "
                    f"{item.get('state') or ''} | {item.get('status') or ''} | {item.get('desiredReplicaCount') or ''} | "
                    f"{item.get('directRouteHandle') or ''} | {item.get('directRouteType') or ''} | {item.get('activeModelVersion') or ''} |"
                )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Debug Fireworks model access and Gemma on-demand deployment readiness.")
    parser.add_argument("--account-id", default=None)
    parser.add_argument("--check-deployments", action="store_true")
    parser.add_argument("--wait-for-deployment-ready", action="store_true")
    parser.add_argument("--wait-timeout-seconds", type=int, default=1800)
    parser.add_argument("--poll-interval-seconds", type=int, default=30)
    parser.add_argument("--models", default=",".join(DEFAULT_ALLOWED_PLANNING_MODELS))
    parser.add_argument("--test-private-deployments", action="store_true")
    parser.add_argument("--out-json", type=Path, default=Path("eval_runs/fireworks_model_access.json"))
    parser.add_argument("--out-md", type=Path, default=Path("eval_runs/fireworks_model_access.md"))
    args = parser.parse_args(argv)

    models = parse_allowed_models(args.models)
    allowed = set(DEFAULT_ALLOWED_PLANNING_MODELS)
    unexpected = [model for model in models if model not in allowed]
    if unexpected:
        raise SystemExit("Unexpected model alias(es): " + ", ".join(unexpected))
    if (args.check_deployments or args.wait_for_deployment_ready or args.test_private_deployments) and not args.account_id:
        raise SystemExit("--account-id is required for deployment checks")

    deployments: list[dict] = []
    if args.wait_for_deployment_ready:
        deployments = wait_for_deployments(
            args.account_id,
            models,
            timeout_seconds=args.wait_timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
    elif args.check_deployments:
        deployments = load_deployments(args.account_id)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": models,
        "account_id": args.account_id,
        "checked_deployments": bool(args.check_deployments or args.wait_for_deployment_ready),
        "results": [
            evaluate_model(model, deployments, args.account_id, args.test_private_deployments)
            for model in models
        ],
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    args.out_md.write_text(render_markdown(payload) + "\n", encoding="utf-8")
    print(f"JSON: {args.out_json}")
    print(f"Markdown: {args.out_md}")
    for result in payload["results"]:
        print(f"{result['alias']}: {result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
