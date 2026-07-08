import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.router_config_sweep import DEFAULT_CONFIGS


EVAL_RUNS = REPO_ROOT / "eval_runs"
RECOMMENDED_CONFIG_RE = re.compile(r"Recommended config:\s*`([^`]+)`")


def config_by_name(name: str) -> dict:
    for config in DEFAULT_CONFIGS:
        if config["name"] == name:
            return config
    raise ValueError(f"unknown router sweep config: {name}")


def latest_router_sweep_report(eval_runs: Path = EVAL_RUNS) -> Path | None:
    reports = sorted(eval_runs.glob("router_sweep_*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def recommended_config_from_report(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = RECOMMENDED_CONFIG_RE.search(text)
    if not match:
        raise ValueError(f"could not find recommended config in {path}")
    return match.group(1)


def prompt_policy_map_value(mapping: dict[str, str] | None) -> str:
    if not mapping:
        return ""
    return ",".join(f"{category}={policy}" for category, policy in sorted(mapping.items()))


def model_preference_value(config: dict) -> str:
    models = [config["fallback_model"]]
    escalation_model = config.get("escalation_model")
    if escalation_model and escalation_model not in models:
        models.append(escalation_model)
    return ",".join(models)


def category_model_preference_value(mapping: dict[str, list[str]] | None) -> str:
    if not mapping:
        return ""
    values = []
    for category, models in sorted(mapping.items()):
        if models:
            values.append(f"{category}={','.join(models)}")
    return ";".join(values)


def exports_for_config(config: dict) -> list[tuple[str, str | None]]:
    prompt_policy = config["prompt_policy"]
    model_preference = model_preference_value(config)
    category_policy = prompt_policy_map_value(config.get("prompt_policy_by_category"))
    category_models = category_model_preference_value(config.get("models_by_category"))

    exports: list[tuple[str, str | None]] = [
        ("ROUTER_MODE", config["router_mode"]),
        ("LOCAL_CONFIDENCE_THRESHOLD", str(config["local_confidence_threshold"] if config["local_enabled"] else 1.01)),
        ("FIREWORKS_MAX_TOKENS", str(config["max_tokens"])),
        ("ROUTER_PROMPT_POLICY_REMOTE_ACCURACY", prompt_policy),
        ("ROUTER_PROMPT_POLICY_REMOTE_CODE", prompt_policy),
        ("ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT", prompt_policy),
        ("ROUTER_PROMPT_POLICY_REMOTE_CONCISE", prompt_policy),
        ("ROUTER_PROMPT_POLICY_BY_CATEGORY", category_policy or None),
        ("ROUTER_MODELS_REMOTE_ACCURACY", model_preference),
        ("ROUTER_MODELS_REMOTE_CODE", model_preference),
        ("ROUTER_MODELS_REMOTE_FORMAT_STRICT", model_preference),
        ("ROUTER_MODELS_REMOTE_CONCISE", model_preference),
        ("ROUTER_MODELS_BY_CATEGORY", category_models or None),
    ]
    return exports


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def render_shell(config_name: str, config: dict, source_report: Path | None = None) -> str:
    lines = [f"# Router sweep config: {config_name}"]
    if source_report:
        lines.append(f"# Source report: {source_report}")
    lines.append("# Paste these exports for runtime testing. Do not set ROUTER_MODE to the sweep config name.")
    for name, value in exports_for_config(config):
        if value is None:
            lines.append(f"unset {name}")
        else:
            lines.append(f"export {name}={shell_quote(value)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print runtime env exports for a router sweep config.")
    parser.add_argument("--config", help="Router config name from eval/router_config_sweep.py.")
    parser.add_argument(
        "--from-latest-sweep",
        action="store_true",
        help="Read the recommended config from the latest eval_runs/router_sweep_*.md report.",
    )
    args = parser.parse_args(argv)

    source_report = None
    config_name = args.config
    if args.from_latest_sweep:
        source_report = latest_router_sweep_report()
        if source_report is None:
            print("ERROR: no router_sweep_*.md report found in eval_runs", file=sys.stderr)
            return 1
        config_name = recommended_config_from_report(source_report)

    if not config_name:
        parser.error("provide --config or --from-latest-sweep")

    try:
        config = config_by_name(config_name)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(render_shell(config_name, config, source_report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
