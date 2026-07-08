import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_REPORT = ROOT / "eval_runs" / "phase1_acceptance_latest.json"
QUALITY_REPORT = ROOT / "eval_runs" / "local_quality_gate_latest.json"


def read_json(path: Path) -> dict:
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


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


def readiness_status(acceptance: dict, quality: dict, docker: dict | None) -> str:
    if acceptance.get("status") != "passed":
        return "blocked_acceptance_not_passed"
    if quality.get("status") != "passed":
        return "blocked_quality_gate_not_passed"
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    acceptance = read_json(ACCEPTANCE_REPORT)
    quality = read_json(QUALITY_REPORT)
    docker = docker_summary(args.image) if args.include_docker else None
    status = readiness_status(acceptance, quality, docker)

    summary = {
        "status": status,
        "acceptance_status": acceptance.get("status"),
        "acceptance_timestamp": acceptance.get("timestamp"),
        "quality_status": quality.get("status"),
        "quality_timestamp": quality.get("timestamp"),
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
