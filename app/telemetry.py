import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_FIELD_MARKERS = ("api_key", "authorization", "secret", "password", "bearer")


class TelemetryLogger:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def log(self, record: dict[str, Any]) -> None:
        if self.path is None:
            return
        safe_record = sanitize_record(record)
        safe_record["logged_at"] = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe_record, ensure_ascii=True, sort_keys=True) + "\n")


def sanitize_record(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in SECRET_FIELD_MARKERS):
                sanitized[key] = "[redacted]"
            else:
                sanitized[key] = sanitize_record(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_record(item) for item in value]
    return value
