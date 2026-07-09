import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.recommend_from_model_matrix import DEFAULT_REQUIRED_CATEGORIES, evidence_status

ACCEPTANCE_REPORT = ROOT / "eval_runs" / "phase1_acceptance_latest.json"
QUALITY_REPORT = ROOT / "eval_runs" / "local_quality_gate_latest.json"
EVAL_RUNS = ROOT / "eval_runs"
AGENT_EVIDENCE_THRESHOLD = 0.80


def read_json(path: Path) -> dict:
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def latest_file(pattern: str) -> Path | None:
    files = sorted(EVAL_RUNS.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def report_line(path: Path, prefix: str) -> str | None:
    report_path = path.with_suffix(".md")
    if not report_path.exists():
        return None
    for line in report_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return None


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def latest_router_sweep_summary() -> dict:
    path = latest_file("router_sweep_*.jsonl")
    if path is None:
        return {"status": "missing"}

    rows = read_jsonl(path)
    configs = sorted({row.get("config") for row in rows if row.get("config")})
    passed = sum(1 for row in rows if row.get("passed"))
    tokens = sum(int(row.get("total_tokens") or 0) for row in rows)
    recommended = report_line(path, "Recommended config:")
    if recommended:
        recommended = recommended.strip("`")
    return {
        "status": "present",
        "path": display_path(path),
        "rows": len(rows),
        "configs": configs,
        "recommended_config": recommended,
        "pass_rate": round(passed / len(rows), 4) if rows else 0,
        "total_tokens": tokens,
    }


def latest_model_matrix_summary() -> dict:
    path = latest_file("model_matrix_*.jsonl")
    if path is None:
        return {"status": "missing"}

    rows = read_jsonl(path)
    models = sorted({row.get("model") for row in rows if row.get("model")})
    policies = sorted({row.get("prompt_policy") for row in rows if row.get("prompt_policy")})
    passed = sum(1 for row in rows if row.get("passed"))
    errors = sum(1 for row in rows if row.get("error"))
    tokens = sum(int(row.get("total_tokens") or 0) for row in rows)
    return {
        "status": "present",
        "path": display_path(path),
        "mode": report_line(path, "Mode:") or "unknown",
        "rows": len(rows),
        "models": models,
        "prompt_policies": policies,
        "pass_rate": round(passed / len(rows), 4) if rows else 0,
        "errors": errors,
        "total_tokens": tokens,
    }


def latest_agent_matrix_summary() -> dict:
    path = latest_file("agent_matrix_*.jsonl")
    if path is None:
        return {"status": "missing"}

    rows = read_jsonl(path)
    passed = sum(1 for row in rows if row.get("passed"))
    errors = sum(1 for row in rows if row.get("error"))
    tokens = sum(int(row.get("total_tokens") or 0) for row in rows)
    by_category = {}
    for row in rows:
        category = row.get("category")
        if not category:
            continue
        item = by_category.setdefault(category, {"rows": 0, "passed": 0, "score": 0.0, "errors": 0, "tokens": 0})
        item["rows"] += 1
        item["passed"] += int(bool(row.get("passed")))
        item["score"] += float(row.get("score") or 0.0)
        item["errors"] += int(bool(row.get("error")))
        item["tokens"] += int(row.get("total_tokens") or 0)

    category_summary = {}
    for category, item in sorted(by_category.items()):
        rows_count = item["rows"]
        category_summary[category] = {
            "rows": rows_count,
            "pass_rate": round(item["passed"] / rows_count, 4) if rows_count else 0,
            "avg_score": round(item["score"] / rows_count, 4) if rows_count else 0,
            "errors": item["errors"],
            "total_tokens": item["tokens"],
        }

    return {
        "status": "present",
        "path": display_path(path),
        "mode": report_line(path, "Mode:") or "unknown",
        "rows": len(rows),
        "pass_rate": round(passed / len(rows), 4) if rows else 0,
        "errors": errors,
        "total_tokens": tokens,
        "categories": category_summary,
    }


def docker_value(image: str, template: str) -> str | None:
    completed = subprocess.run(
        ["docker", "image", "inspect", image, "--format", template],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def docker_summary(image: str) -> dict:
    arch = docker_value(image, "{{.Architecture}}")
    size_raw = docker_value(image, "{{.Size}}")
    if arch is None or size_raw is None:
        return {"available": False, "image": image}

    size_bytes = int(size_raw)
    return {
        "available": True,
        "image": image,
        "architecture": arch,
        "size_bytes": size_bytes,
        "size_gb": round(size_bytes / (1024**3), 4),
        "under_10gb": size_bytes <= 10 * 1024**3,
        "under_8gb_guard": size_bytes <= 8 * 1024**3,
    }


def recommendation_summary(path: Path | None) -> dict | None:
    if path is None:
        return None
    if not path.exists():
        return {
            "status": "missing",
            "path": display_path(path),
        }
    payload = read_json(path)
    inferred_legacy_evidence = False
    status = payload.get("evidence_status")
    evidence = payload.get("evidence")
    recommendations = payload.get("recommendations", {})
    if status is None and isinstance(recommendations, dict):
        evidence = evidence_status(recommendations, DEFAULT_REQUIRED_CATEGORIES)
        status = evidence["status"]
        inferred_legacy_evidence = True
    if not isinstance(evidence, dict):
        evidence = {}
    exports = payload.get("exports", {})
    return {
        "status": status or "unknown",
        "path": display_path(path),
        "rows": payload.get("rows"),
        "runs": payload.get("runs"),
        "inferred_legacy_evidence": inferred_legacy_evidence,
        "missing_categories": evidence.get("missing_categories", []),
        "ineligible_categories": evidence.get("ineligible_categories", []),
        "export_count": len(exports) if isinstance(exports, dict) else 0,
    }


def agent_matrix_covers_ineligible_categories(recommendation: dict | None, agent_matrix: dict | None) -> bool:
    if recommendation is None or agent_matrix is None:
        return False
    if recommendation.get("status") == "passed":
        return True
    if recommendation.get("status") in {None, "missing"}:
        return False
    if recommendation.get("missing_categories"):
        return False
    ineligible = recommendation.get("ineligible_categories", [])
    if not ineligible:
        return False
    categories = agent_matrix.get("categories", {}) if isinstance(agent_matrix, dict) else {}
    for category in ineligible:
        item = categories.get(category)
        if not item:
            return False
        if item.get("errors", 0) != 0:
            return False
        if item.get("pass_rate", 0) < AGENT_EVIDENCE_THRESHOLD:
            return False
        if item.get("avg_score", 0) < AGENT_EVIDENCE_THRESHOLD:
            return False
    return True


def readiness_status(
    acceptance: dict,
    quality: dict,
    docker: dict | None,
    recommendation: dict | None = None,
    agent_matrix: dict | None = None,
) -> str:
    if acceptance.get("status") != "passed":
        return "blocked_acceptance_not_passed"
    if quality.get("status") != "passed":
        return "blocked_quality_gate_not_passed"
    if recommendation is not None:
        if recommendation.get("status") == "missing":
            return "blocked_recommendation_missing"
        if recommendation.get("status") != "passed" and not agent_matrix_covers_ineligible_categories(
            recommendation,
            agent_matrix,
        ):
            return "blocked_recommendation_evidence_not_passed"
    if docker is not None:
        if not docker.get("available"):
            return "blocked_docker_image_missing"
        if docker.get("architecture") != "amd64":
            return "blocked_docker_not_amd64"
        if not docker.get("under_10gb"):
            return "blocked_docker_too_large"
    return "ready_for_live_eval_or_final_submission_prep"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print latest Track 1 submission readiness summary.")
    parser.add_argument("--image", default="juggernaut-router:local", help="Docker image to inspect.")
    parser.add_argument("--include-docker", action="store_true", help="Inspect local Docker image metadata.")
    parser.add_argument(
        "--recommendation",
        type=Path,
        default=None,
        help="Optional runtime recommendation JSON that must have evidence_status=passed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    acceptance = read_json(ACCEPTANCE_REPORT)
    quality = read_json(QUALITY_REPORT)
    docker = docker_summary(args.image) if args.include_docker else None
    recommendation = recommendation_summary(args.recommendation)
    router_sweep = latest_router_sweep_summary()
    model_matrix = latest_model_matrix_summary()
    agent_matrix = latest_agent_matrix_summary()
    status = readiness_status(acceptance, quality, docker, recommendation, agent_matrix)

    summary = {
        "status": status,
        "acceptance_status": acceptance.get("status"),
        "acceptance_timestamp": acceptance.get("timestamp"),
        "quality_status": quality.get("status"),
        "quality_timestamp": quality.get("timestamp"),
        "latest_router_sweep": router_sweep,
        "latest_model_matrix": model_matrix,
        "latest_agent_matrix": agent_matrix,
        "runtime_recommendation": recommendation,
        "docker": docker,
        "next_required_step": (
            "Run live model matrix in AMD notebook through FIREWORKS_BASE_URL"
            if status == "ready_for_live_eval_or_final_submission_prep"
            else "Fix blocking readiness status"
        ),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if status == "ready_for_live_eval_or_final_submission_prep" else 1


if __name__ == "__main__":
    raise SystemExit(main())
