import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = "juggernaut-router:local"
DEFAULT_PLATFORM = "linux/amd64"
DEFAULT_MAX_SIZE_GB = 8.0


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    print("$ " + " ".join(cmd))
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(completed.stdout)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return completed


def image_size_bytes(image: str) -> int:
    completed = run(["docker", "image", "inspect", image, "--format", "{{.Size}}"])
    return int(completed.stdout.strip())


def image_architecture(image: str) -> str:
    completed = run(["docker", "image", "inspect", image, "--format", "{{.Architecture}}"])
    return completed.stdout.strip()


def bytes_to_gb(size: int) -> float:
    return size / (1024**3)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and smoke-test the Docker runtime.")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="Local Docker image tag.")
    parser.add_argument("--platform", default=DEFAULT_PLATFORM, help="Build platform.")
    parser.add_argument("--max-size-gb", type=float, default=DEFAULT_MAX_SIZE_GB, help="Conservative local image size ceiling.")
    parser.add_argument("--input-dir", default="local_test/input", help="Directory mounted to /input:ro.")
    parser.add_argument("--output-dir", default="local_test/output", help="Directory mounted to /output.")
    parser.add_argument("--skip-build", action="store_true", help="Use an existing image.")
    parser.add_argument("--skip-run", action="store_true", help="Skip mounted IO container run.")
    parser.add_argument("--skip-size", action="store_true", help="Skip image size check.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = (ROOT / args.input_dir).resolve()
    output_dir = (ROOT / args.output_dir).resolve()
    output_file = output_dir / "results.json"

    if not args.skip_build:
        run(["docker", "build", "--platform", args.platform, "-t", args.image, "."])

    arch = image_architecture(args.image)
    expected_arch = args.platform.split("/")[-1]
    if arch != expected_arch:
        print(f"FAIL: image architecture is {arch}, expected {expected_arch}")
        return 1
    print(f"OK: image architecture is {arch}")

    if not args.skip_size:
        size = image_size_bytes(args.image)
        size_gb = bytes_to_gb(size)
        print(f"Image size: {size_gb:.3f} GB ({size} bytes)")
        if size_gb > args.max_size_gb:
            print(f"FAIL: image size exceeds conservative ceiling of {args.max_size_gb:.3f} GB")
            return 1
        print(f"OK: image size is below {args.max_size_gb:.3f} GB conservative ceiling")

    if not args.skip_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        if output_file.exists():
            output_file.unlink()
        run(
            [
                "docker",
                "run",
                "--rm",
                "--platform",
                args.platform,
                "-v",
                f"{input_dir}:/input:ro",
                "-v",
                f"{output_dir}:/output",
                args.image,
            ]
        )
        run([sys.executable, "scripts/validate_submission_io.py", str(output_file)])

    print("OK: Docker runtime guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
