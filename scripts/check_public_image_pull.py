import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check anonymous/public Docker pull timing and basic image contents."
    )
    parser.add_argument("image", help="Exact public image reference, including tag.")
    parser.add_argument("--platform", default="linux/amd64")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--warn-seconds", type=float, default=300.0)
    parser.add_argument("--expect-file", default="/app/models/local-model.gguf")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--skip-rmi", action="store_true")
    args = parser.parse_args()

    report: dict = {
        "image": args.image,
        "platform": args.platform,
        "timeout_seconds": args.timeout_seconds,
        "warn_seconds": args.warn_seconds,
        "expect_file": args.expect_file,
        "steps": [],
    }

    if not args.skip_rmi:
        run_step(report, ["docker", "logout", registry_from_image(args.image)], allow_failure=True)
        run_step(report, ["docker", "rmi", args.image], allow_failure=True)

    pull_started = time.monotonic()
    pull = run_step(
        report,
        ["docker", "pull", "--platform", args.platform, args.image],
        timeout=args.timeout_seconds,
    )
    pull_seconds = time.monotonic() - pull_started
    report["pull_seconds"] = round(pull_seconds, 3)
    report["pull_status"] = "passed" if pull.returncode == 0 else "failed"

    if pull.returncode != 0:
        report["status"] = "failed_pull"
        write_report(args.out_json, report)
        print_summary(report)
        return pull.returncode or 1

    inspect = run_step(
        report,
        ["docker", "image", "inspect", args.image, "--format", "{{.Architecture}} {{.Size}}"],
    )
    if inspect.returncode == 0:
        parts = inspect.stdout.strip().split()
        if len(parts) >= 2:
            report["architecture"] = parts[0]
            try:
                report["size_bytes"] = int(parts[1])
                report["size_gb"] = round(int(parts[1]) / (1024**3), 4)
            except ValueError:
                pass

    check_file = run_step(
        report,
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            args.platform,
            args.image,
            "sh",
            "-c",
            f"test -f {shell_quote(args.expect_file)} && ls -lh {shell_quote(args.expect_file)}",
        ],
    )
    report["expected_file_present"] = check_file.returncode == 0

    if report.get("architecture") != "amd64":
        report["status"] = "failed_architecture"
        exit_code = 2
    elif not report["expected_file_present"]:
        report["status"] = "failed_expected_file"
        exit_code = 3
    elif pull_seconds > args.warn_seconds:
        report["status"] = "passed_slow_pull"
        exit_code = 0
    else:
        report["status"] = "passed"
        exit_code = 0

    write_report(args.out_json, report)
    print_summary(report)
    return exit_code


def run_step(
    report: dict,
    cmd: list[str],
    *,
    timeout: int | None = None,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        step = {
            "cmd": cmd,
            "returncode": 124,
            "elapsed_seconds": round(elapsed, 3),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or f"Timed out after {timeout} seconds",
        }
        report["steps"].append(step)
        return subprocess.CompletedProcess(cmd, 124, step["stdout"], step["stderr"])

    elapsed = time.monotonic() - started
    report["steps"].append(
        {
            "cmd": cmd,
            "returncode": proc.returncode,
            "elapsed_seconds": round(elapsed, 3),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "allowed_failure": allow_failure,
        }
    )
    return proc


def registry_from_image(image: str) -> str:
    first = image.split("/", 1)[0]
    if "." in first or ":" in first:
        return first
    return "docker.io"


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def write_report(path: str, report: dict) -> None:
    if not path:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def print_summary(report: dict) -> None:
    print(f"status: {report.get('status')}")
    print(f"image: {report.get('image')}")
    print(f"pull_seconds: {report.get('pull_seconds')}")
    print(f"architecture: {report.get('architecture')}")
    print(f"size_gb: {report.get('size_gb')}")
    print(f"expected_file_present: {report.get('expected_file_present')}")
    for step in report.get("steps", []):
        cmd = " ".join(step["cmd"])
        print(f"step: rc={step['returncode']} elapsed={step['elapsed_seconds']}s {cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
