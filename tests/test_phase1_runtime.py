import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import RuntimeConfig, parse_allowed_models
from app.deadline import DeadlineManager
from app.fireworks_client import ask_fireworks_structured
from app.main import main
from app.normalization import normalize_answer
from app.telemetry import TelemetryLogger
from app.types import SAFE_FALLBACK_ANSWER


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class Phase1RuntimeTests(unittest.TestCase):
    def test_parse_allowed_models_deduplicates_and_strips(self):
        self.assertEqual(parse_allowed_models(" a, b ,,a "), ["a", "b"])

    def test_config_clamps_fireworks_timeout_below_response_ceiling(self):
        with patch.dict(os.environ, {"FIREWORKS_TIMEOUT_SECONDS": "99"}, clear=True):
            config = RuntimeConfig.from_env()
        self.assertEqual(config.fireworks_timeout_seconds, 29)

    def test_deadline_suppresses_retry_when_budget_is_low(self):
        clock = FakeClock()
        deadline = DeadlineManager(total_seconds=10, safety_margin_seconds=3, clock=clock)
        clock.value = 8
        self.assertFalse(deadline.should_retry(timeout_seconds=2))
        self.assertEqual(deadline.deadline_decision(2), "deadline_suppressed_remote_or_retry")

    def test_normalize_answer_returns_safe_fallback_for_empty(self):
        self.assertEqual(normalize_answer("   "), SAFE_FALLBACK_ANSWER)

    def test_normalize_answer_strips_code_fence_for_code_only(self):
        answer = normalize_answer("```python\nprint('ok')\n```", code_only=True)
        self.assertEqual(answer, "print('ok')")

    def test_telemetry_redacts_secret_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "router.jsonl"
            logger = TelemetryLogger(path)
            logger.log({"task_id": "x", "api_key": "secret", "nested": {"authorization": "bearer"}})
            row = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(row["api_key"], "[redacted]")
        self.assertEqual(row["nested"]["authorization"], "[redacted]")

    def test_fireworks_missing_env_fails_soft(self):
        with patch.dict(os.environ, {}, clear=True):
            result = ask_fireworks_structured("hello")
        self.assertEqual(result.answer, SAFE_FALLBACK_ANSWER)
        self.assertEqual(result.error, "missing_fireworks_environment")

    def test_main_handles_malformed_task_and_keeps_official_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "tasks.json"
            output_path = Path(tmpdir) / "results.json"
            log_path = Path(tmpdir) / "router.jsonl"
            input_path.write_text(
                json.dumps([
                    {"task_id": "ok", "prompt": "2+2"},
                    {"task_id": "bad"},
                    "not-an-object",
                ]),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "INPUT_PATH": str(input_path),
                    "OUTPUT_PATH": str(output_path),
                    "ROUTER_LOG_PATH": str(log_path),
                },
                clear=True,
            ):
                main()
            rows = json.loads(output_path.read_text(encoding="utf-8"))
            telemetry_rows = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(set(row), {"task_id", "answer"})
            self.assertIsInstance(row["answer"], str)
            self.assertTrue(row["answer"].strip())
        self.assertTrue(any(row.get("task_elapsed_ms") is not None for row in telemetry_rows))

    def test_main_writes_empty_results_for_invalid_input_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "tasks.json"
            output_path = Path(tmpdir) / "results.json"
            input_path.write_text("{bad json", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"INPUT_PATH": str(input_path), "OUTPUT_PATH": str(output_path)},
                clear=True,
            ):
                main()
            rows = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
