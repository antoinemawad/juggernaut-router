import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import DEFAULT_ALLOWED_PLANNING_MODELS, parse_allowed_models


NORMAL_FIREWORKS_HOST = "api." + "fireworks.ai"


def _normal_fireworks_dev_allowed(env: dict[str, str], explicit: bool = False) -> bool:
    return explicit or env.get("JUGGERNAUT_ALLOW_NORMAL_FIREWORKS_DEV", "").strip() == "1"


def validate_live_eval_env(env: dict[str, str], allow_normal_fireworks_dev: bool = False) -> list[str]:
    errors: list[str] = []
    api_key = env.get("FIREWORKS_API_KEY", "").strip()
    base_url = env.get("FIREWORKS_BASE_URL", "").strip()
    allowed_models = parse_allowed_models(env.get("ALLOWED_MODELS"))
    dev_override = _normal_fireworks_dev_allowed(env, allow_normal_fireworks_dev)

    if not api_key:
        errors.append("FIREWORKS_API_KEY is missing")
    if not base_url:
        errors.append("FIREWORKS_BASE_URL is missing")
    else:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append("FIREWORKS_BASE_URL must be an absolute http(s) URL")
        if parsed.netloc == NORMAL_FIREWORKS_HOST and not dev_override:
            errors.append("FIREWORKS_BASE_URL must be the judging proxy, not the normal Fireworks API host")

    if not allowed_models:
        errors.append("ALLOWED_MODELS is missing or empty")
    else:
        allowed_set = set(DEFAULT_ALLOWED_PLANNING_MODELS)
        unsupported = [model for model in allowed_models if model not in allowed_set]
        if unsupported:
            errors.append("ALLOWED_MODELS contains unexpected model(s): " + ", ".join(unsupported))

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate env vars before live AMD/Fireworks eval runs.")
    parser.add_argument(
        "--print-models",
        action="store_true",
        help="Print parsed ALLOWED_MODELS when validation passes.",
    )
    parser.add_argument(
        "--allow-normal-fireworks-dev",
        action="store_true",
        help="Development only: allow the normal Fireworks API host when the judging proxy is unavailable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = validate_live_eval_env(os.environ, allow_normal_fireworks_dev=args.allow_normal_fireworks_dev)
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1

    print("OK: live eval environment is ready")
    if _normal_fireworks_dev_allowed(os.environ, args.allow_normal_fireworks_dev):
        print("WARNING: normal Fireworks dev override is enabled; do not use this for official Track 1 judging.")
    if args.print_models:
        print("Allowed models: " + ", ".join(parse_allowed_models(os.environ.get("ALLOWED_MODELS"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
