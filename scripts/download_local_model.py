import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _safe_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def main() -> int:
    url = os.environ.get("LOCAL_MODEL_URL", "").strip()
    target_raw = os.environ.get("LOCAL_MODEL_TARGET", "").strip()
    if not url:
        print("LOCAL_MODEL_URL is empty", file=sys.stderr)
        return 2
    if not target_raw:
        print("LOCAL_MODEL_TARGET is empty", file=sys.stderr)
        return 2

    target = Path(target_raw)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    if partial.exists():
        partial.unlink()

    print(f"Downloading local model from: {_safe_url(url)}")
    print(f"Target local model path: {target}")
    request = urllib.request.Request(url, headers={"User-Agent": "juggernaut-router-build/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            status = getattr(response, "status", None) or 200
            if status < 200 or status >= 300:
                print(f"Local model download failed with HTTP {status}", file=sys.stderr)
                return 3
            with partial.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        if partial.exists():
            partial.unlink()
        print(f"Local model download failed: {type(exc).__name__}", file=sys.stderr)
        return 4

    size = partial.stat().st_size if partial.exists() else 0
    if size <= 0:
        if partial.exists():
            partial.unlink()
        print("Local model download produced an empty file", file=sys.stderr)
        return 5

    partial.replace(target)
    print(f"Downloaded local model: {target} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
