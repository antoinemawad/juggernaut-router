import argparse
import json
from pathlib import Path


DEFAULT_EVAL_RUNS = Path("eval_runs")


def safe_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def count_jsonl_rows(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


def first_jsonl_row(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    return json.loads(line)
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def paired_report(path: Path) -> str | None:
    md_path = path.with_suffix(".md")
    return md_path.name if md_path.exists() else None


def report_mode(path: Path) -> str | None:
    md_path = path.with_suffix(".md")
    if not md_path.exists():
        return None
    for line in md_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Mode:"):
            return line.removeprefix("Mode:").strip()
    return None


def summarize_jsonl(path: Path) -> dict:
    first = first_jsonl_row(path)
    evidence_type = "jsonl"
    if path.name.startswith("model_matrix_"):
        evidence_type = "model_matrix"
    elif path.name.startswith("router_sweep_"):
        evidence_type = "router_sweep"

    return {
        "file": path.name,
        "type": evidence_type,
        "rows": count_jsonl_rows(path),
        "report": paired_report(path),
        "run_id": first.get("run_id"),
        "mode": report_mode(path),
        "timestamp": first.get("timestamp"),
    }


def summarize_json(path: Path) -> dict:
    payload = safe_json(path)
    return {
        "file": path.name,
        "type": "json",
        "status": payload.get("status"),
        "timestamp": payload.get("timestamp"),
    }


def build_manifest(eval_runs: Path) -> dict:
    jsonl = [summarize_jsonl(path) for path in sorted(eval_runs.glob("*.jsonl"))]
    json_reports = [summarize_json(path) for path in sorted(eval_runs.glob("*.json"))]
    markdown_reports = sorted(path.name for path in eval_runs.glob("*.md"))
    return {
        "eval_runs": str(eval_runs),
        "jsonl_reports": jsonl,
        "json_reports": json_reports,
        "markdown_reports": markdown_reports,
        "counts": {
            "jsonl": len(jsonl),
            "json": len(json_reports),
            "markdown": len(markdown_reports),
        },
    }


def write_markdown(path: Path, manifest: dict) -> None:
    lines = [
        "# Evidence Manifest",
        "",
        f"Eval runs directory: `{manifest['eval_runs']}`",
        "",
        "## Counts",
        "",
        f"- JSONL reports: {manifest['counts']['jsonl']}",
        f"- JSON reports: {manifest['counts']['json']}",
        f"- Markdown reports: {manifest['counts']['markdown']}",
        "",
        "## JSONL Evidence",
        "",
        "| File | Type | Rows | Mode | Paired Report |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for item in manifest["jsonl_reports"]:
        lines.append(
            f"| {item['file']} | {item['type']} | {item['rows']} | "
            f"{item.get('mode') or ''} | {item.get('report') or ''} |"
        )

    lines.extend([
        "",
        "## JSON Status Reports",
        "",
        "| File | Status | Timestamp |",
        "| --- | --- | --- |",
    ])
    for item in manifest["json_reports"]:
        lines.append(f"| {item['file']} | {item.get('status') or ''} | {item.get('timestamp') or ''} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a manifest of eval evidence files.")
    parser.add_argument("--eval-runs", type=Path, default=DEFAULT_EVAL_RUNS)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_EVAL_RUNS / "evidence_manifest.json")
    parser.add_argument("--out-md", type=Path, default=DEFAULT_EVAL_RUNS / "evidence_manifest.md")
    args = parser.parse_args()

    manifest = build_manifest(args.eval_runs)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    write_markdown(args.out_md, manifest)
    print(f"JSON: {args.out_json}")
    print(f"Markdown: {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
