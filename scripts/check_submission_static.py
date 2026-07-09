import fnmatch
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_FIREWORKS_URL = "https://api." + "fireworks.ai"
RUNTIME_SCAN_GLOBS = (
    "app/**/*.py",
    "scripts/**/*.py",
    "eval/**/*.py",
    "tests/**/*.py",
    "Dockerfile",
)
FORBIDDEN_TRACKED_PATTERNS = (
    ".env",
    ".env.*",
    "*.key",
    "*.pem",
    "models/*",
    "checkpoints/*",
    "*.safetensors",
    "*.bin",
    "*.pt",
    "*.pth",
)
ALLOWED_TRACKED_ARTIFACTS = {
    "models/.gitkeep",
}


def git_tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def collect_runtime_files() -> list[Path]:
    files: list[Path] = []
    for pattern in RUNTIME_SCAN_GLOBS:
        if "**" in pattern or "*" in pattern:
            files.extend(path for path in ROOT.glob(pattern) if path.is_file())
        else:
            path = ROOT / pattern
            if path.is_file():
                files.append(path)
    return sorted(set(files))


def check_no_forbidden_runtime_url() -> list[str]:
    errors = []
    for path in collect_runtime_files():
        if FORBIDDEN_FIREWORKS_URL in read_text(path):
            errors.append(f"{path.relative_to(ROOT)} hardcodes {FORBIDDEN_FIREWORKS_URL}")
    return errors


def check_no_forbidden_tracked_files() -> list[str]:
    errors = []
    for tracked in git_tracked_files():
        if tracked in ALLOWED_TRACKED_ARTIFACTS:
            continue
        for pattern in FORBIDDEN_TRACKED_PATTERNS:
            if fnmatch.fnmatch(tracked, pattern):
                errors.append(f"forbidden tracked artifact: {tracked}")
                break
    return errors


def check_ignore_files() -> list[str]:
    errors = []
    gitignore = read_text(ROOT / ".gitignore")
    dockerignore = read_text(ROOT / ".dockerignore")
    for required in (".env", ".env*", "*.key", "*.pem"):
        if required not in gitignore:
            errors.append(f".gitignore missing {required}")
        if required not in dockerignore:
            errors.append(f".dockerignore missing {required}")
    for required in ("models/", "checkpoints/", "*.safetensors", "*.bin", "*.pt", "*.pth"):
        if required not in dockerignore:
            errors.append(f".dockerignore missing model artifact guard {required}")
    for required in (
        ".git",
        "__pycache__/",
        "**/__pycache__/",
        "*.pyc",
        "*.pyo",
        "Guides/",
        "docs/",
        "eval_runs/",
        "local_test/",
    ):
        if required not in dockerignore:
            errors.append(f".dockerignore missing runtime artifact guard {required}")
    return errors


def check_dockerfile_is_submission_scoped() -> list[str]:
    dockerfile = read_text(ROOT / "Dockerfile")
    errors = []
    if "COPY . " in dockerfile or "COPY ./" in dockerfile:
        errors.append("Dockerfile should not copy the entire repository into the image")
    if "COPY app ./app" not in dockerfile:
        errors.append("Dockerfile should copy app/ into the runtime image")
    if 'CMD ["python", "-m", "app.main"]' not in dockerfile:
        errors.append("Dockerfile should run app.main as the submission entrypoint")
    return errors


def main() -> int:
    errors = []
    errors.extend(check_no_forbidden_runtime_url())
    errors.extend(check_no_forbidden_tracked_files())
    errors.extend(check_ignore_files())
    errors.extend(check_dockerfile_is_submission_scoped())

    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1

    print("OK: static submission guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
