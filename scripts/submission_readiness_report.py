import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_REPORT = ROOT / "eval_runs" / "phase1_acceptance_latest.json"
QUALITY_REPORT = ROOT / "eval_runs" / "local_quality_gate_latest.json"
EVAL_RUNS = ROOT / "eval_runs"


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
    evidence = payload.get("evidence", {})
    exports = payload.get("exports", {})
    return {
        "status": payload.get("evidence_status", "unknown"),
        "path": display_path(path),
        "rows": payload.get("rows"),
        "runs": payload.get("runs"),
        "missing_categories": evidence.get("missing_categories", []),
        "ineligible_categories": evidence.get("ineligible_categories", []),
        "export_count": len(exports) if isinstance(exports, dict) else 0,
    }


def readiness_status(acceptance: dict, quality: dict, docker: dict | None, recommendation: dict | None = None) -> str:
    if acceptance.get("status") != "passed":
        return "blocked_acceptance_not_passed"
    if quality.get("status") != "passed":
        return "blocked_quality_gate_not_passed"
    if recommendation is not None:
        if recommendation.get("status") == "missing":
            return "blocked_recommendation_missing"
        if recommendation.get("status") != "passed":
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
    status = readiness_status(acceptance, quality, docker, recommendation)

    summary = {
        "status": status,
        "acceptance_status": acceptance.get("status"),
        "acceptance_timestamp": acceptance.get("timestamp"),
        "quality_status": quality.get("status"),
        "quality_timestamp": quality.get("timestamp"),
        "latest_router_sweep": router_sweep,
        "latest_model_matrix": model_matrix,
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
