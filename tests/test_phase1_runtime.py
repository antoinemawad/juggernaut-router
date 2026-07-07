import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

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


class FakeResponse:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.payload.encode("utf-8")


class Phase1RuntimeTests(unittest.TestCase):
    def test_parse_allowed_models_deduplicates_and_strips(self):
        self.assertEqual(parse_allowed_models(" a, b ,,a "), ["a", "b"])

    def test_config_clamps_fireworks_timeout_below_response_ceiling(self):
        with patch.dict(os.environ, {"FIREWORKS_TIMEOUT_SECONDS": "99"}, clear=True):
            config = RuntimeConfig.from_env()
        self.assertEqual(config.fireworks_timeout_seconds, 29)

    def test_config_parses_local_proof_and_cross_check_knobs(self):
        with patch.dict(
            os.environ,
            {
                "LOCAL_PROOF_BUDGET_MS": "250",
                "LOCAL_CROSS_CHECK_ENABLED": "false",
            },
            clear=True,
        ):
            config = RuntimeConfig.from_env()
        self.assertEqual(config.local_proof_budget_ms, 250)
        self.assertFalse(config.local_cross_check_enabled)

    def test_deadline_suppresses_retry_when_budget_is_low(self):
        clock = FakeClock()
        deadline = DeadlineManager(total_seconds=10, safety_margin_seconds=3, clock=clock)
        clock.value = 8
        self.assertFalse(deadline.should_retry(timeout_seconds=2))
        self.assertEqual(deadline.deadline_decision(2), "deadline_suppressed_remote_or_retry")

    def test_deadline_accounts_from_construction_time(self):
        clock = FakeClock()
        deadline = DeadlineManager(total_seconds=600, safety_margin_seconds=60, clock=clock)
        clock.value = 12.5
        self.assertEqual(deadline.elapsed_ms(), 12500)
        self.assertEqual(deadline.remaining_budget_ms(), 527500)

    def test_normalize_answer_returns_safe_fallback_for_empty(self):
        self.assertEqual(normalize_answer("   "), SAFE_FALLBACK_ANSWER)

    def test_normalize_answer_strips_code_fence_for_code_only(self):
        answer = normalize_answer("```python\nprint('ok')\n```", code_only=True)
        self.assertEqual(answer, "print('ok')")

    def test_telemetry_redacts_secret_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "router.jsonl"
            logger = TelemetryLogger(path)
            logger.log({
                "task_id": "x",
                "api_key": "secret",
                "total_tokens": 12,
                "nested": {"authorization": "bearer"},
            })
            row = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(row["api_key"], "[redacted]")
        self.assertEqual(row["total_tokens"], 12)
        self.assertEqual(row["nested"]["authorization"], "[redacted]")

    def test_fireworks_missing_env_fails_soft(self):
        with patch.dict(os.environ, {}, clear=True):
            result = ask_fireworks_structured("hello")
        self.assertEqual(result.answer, SAFE_FALLBACK_ANSWER)
        self.assertEqual(result.error, "missing_fireworks_environment")

    def test_fireworks_success_uses_injected_base_url_and_usage(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return FakeResponse(json.dumps({
                "choices": [{"message": {"content": "Remote answer"}}],
                "usage": {"completion_tokens": 3, "total_tokens": 9},
            }))

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3,kimi-k2p7-code",
                "FIREWORKS_TIMEOUT_SECONDS": "7",
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = ask_fireworks_structured("hello")

        self.assertEqual(result.answer, "Remote answer")
        self.assertEqual(result.model, "minimax-m3")
        self.assertEqual(result.completion_tokens, 3)
        self.assertEqual(result.total_tokens, 9)
        self.assertEqual(captured["url"], "https://judge-proxy.example/v1/chat/completions")
        self.assertEqual(captured["timeout"], 7)

    def test_fireworks_invalid_json_fails_soft(self):
        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example",
                "ALLOWED_MODELS": "minimax-m3",
            },
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse("{bad json")):
            result = ask_fireworks_structured("hello")

        self.assertEqual(result.answer, SAFE_FALLBACK_ANSWER)
        self.assertTrue(result.error.startswith("fireworks_response_error"))

    def test_fireworks_missing_choices_fails_soft(self):
        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example",
                "ALLOWED_MODELS": "minimax-m3",
            },
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(json.dumps({"usage": {}}))):
            result = ask_fireworks_structured("hello")

        self.assertEqual(result.answer, SAFE_FALLBACK_ANSWER)
        self.assertTrue(result.error.startswith("fireworks_response_error"))

    def test_fireworks_missing_usage_still_returns_answer(self):
        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example",
                "ALLOWED_MODELS": "minimax-m3",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse(json.dumps({"choices": [{"message": {"content": "No usage answer"}}]})),
        ):
            result = ask_fireworks_structured("hello")

        self.assertEqual(result.answer, "No usage answer")
        self.assertIsNone(result.completion_tokens)
        self.assertIsNone(result.total_tokens)
        self.assertIsNone(result.error)

    def test_fireworks_network_error_retries_then_fails_soft(self):
        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example",
                "ALLOWED_MODELS": "minimax-m3",
                "FIREWORKS_MAX_RETRIES": "1",
            },
            clear=True,
        ), patch("urllib.request.urlopen", side_effect=URLError("boom")) as mocked:
            result = ask_fireworks_structured("hello")

        self.assertEqual(result.answer, SAFE_FALLBACK_ANSWER)
        self.assertEqual(result.retry_count, 1)
        self.assertEqual(mocked.call_count, 2)
        self.assertTrue(result.error.startswith("fireworks_network_error"))

    def test_fireworks_deadline_suppresses_remote_before_network_call(self):
        clock = FakeClock()
        deadline = DeadlineManager(total_seconds=10, safety_margin_seconds=3, clock=clock)
        clock.value = 8
        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example",
                "ALLOWED_MODELS": "minimax-m3",
                "FIREWORKS_TIMEOUT_SECONDS": "5",
            },
            clear=True,
        ), patch("urllib.request.urlopen") as mocked:
            result = ask_fireworks_structured("hello", deadline=deadline)

        self.assertEqual(result.answer, SAFE_FALLBACK_ANSWER)
        self.assertEqual(result.error, "deadline_suppressed_remote")
        mocked.assert_not_called()

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

    def test_main_remote_path_telemetry_includes_remote_timing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "tasks.json"
            output_path = Path(tmpdir) / "results.json"
            log_path = Path(tmpdir) / "router.jsonl"
            input_path.write_text(
                json.dumps([{"task_id": "remote", "prompt": "Explain a difficult thing."}]),
                encoding="utf-8",
            )

            def fake_urlopen(request, timeout):
                return FakeResponse(json.dumps({
                    "choices": [{"message": {"content": "Remote answer"}}],
                    "usage": {"completion_tokens": 2, "total_tokens": 11},
                }))

            with patch.dict(
                os.environ,
                {
                    "INPUT_PATH": str(input_path),
                    "OUTPUT_PATH": str(output_path),
                    "ROUTER_LOG_PATH": str(log_path),
                    "FIREWORKS_API_KEY": "secret",
                    "FIREWORKS_BASE_URL": "https://judge-proxy.example",
                    "ALLOWED_MODELS": "minimax-m3",
                },
                clear=True,
            ), patch("urllib.request.urlopen", fake_urlopen):
                main()

            output_rows = json.loads(output_path.read_text(encoding="utf-8"))
            telemetry_rows = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(output_rows, [{"task_id": "remote", "answer": "Remote answer"}])
        self.assertEqual(telemetry_rows[0]["route"], "fireworks")
        self.assertEqual(telemetry_rows[0]["selected_model"], "minimax-m3")
        self.assertEqual(telemetry_rows[0]["total_tokens"], 11)
        self.assertIn("remote_elapsed_ms", telemetry_rows[0])
        self.assertEqual(set(output_rows[0]), {"task_id", "answer"})

    def test_main_unhandled_agent_exception_falls_back_and_logs_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "tasks.json"
            output_path = Path(tmpdir) / "results.json"
            log_path = Path(tmpdir) / "router.jsonl"
            input_path.write_text(json.dumps([{"task_id": "boom", "prompt": "2+2"}]), encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "INPUT_PATH": str(input_path),
                    "OUTPUT_PATH": str(output_path),
                    "ROUTER_LOG_PATH": str(log_path),
                },
                clear=True,
            ), patch("app.main.answer_task", side_effect=RuntimeError("boom")):
                main()

            output_rows = json.loads(output_path.read_text(encoding="utf-8"))
            telemetry_rows = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(output_rows, [{"task_id": "boom", "answer": SAFE_FALLBACK_ANSWER}])
        self.assertEqual(telemetry_rows[0]["route"], "fallback")
        self.assertEqual(telemetry_rows[0]["route_reason"], "unhandled_task_exception")
        self.assertEqual(telemetry_rows[0]["error"], "RuntimeError")

    def test_main_makes_duplicate_task_ids_unique_for_valid_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "tasks.json"
            output_path = Path(tmpdir) / "results.json"
            input_path.write_text(
                json.dumps([
                    {"task_id": "dup", "prompt": "2+2"},
                    {"task_id": "dup", "prompt": "2+2"},
                    {"task_id": "", "prompt": "2+2"},
                    {"prompt": "2+2"},
                ]),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"INPUT_PATH": str(input_path), "OUTPUT_PATH": str(output_path)},
                clear=True,
            ):
                main()
            rows = json.loads(output_path.read_text(encoding="utf-8"))

        task_ids = [row["task_id"] for row in rows]
        self.assertEqual(len(task_ids), len(set(task_ids)))
        self.assertEqual(task_ids[:2], ["dup", "dup_2"])

    def test_main_writes_empty_results_for_non_array_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "tasks.json"
            output_path = Path(tmpdir) / "results.json"
            input_path.write_text(json.dumps({"task_id": "x"}), encoding="utf-8")
            with patch.dict(
                os.environ,
                {"INPUT_PATH": str(input_path), "OUTPUT_PATH": str(output_path)},
                clear=True,
            ):
                main()
            rows = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(rows, [])

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

    def test_main_writes_empty_results_for_missing_input_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "missing.json"
            output_path = Path(tmpdir) / "results.json"
            with patch.dict(
                os.environ,
                {"INPUT_PATH": str(input_path), "OUTPUT_PATH": str(output_path)},
                clear=True,
            ):
                main()
            rows = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(rows, [])

    def test_task_telemetry_includes_timing_contract_fields(self):
        required_fields = {
            "task_id",
            "route",
            "route_reason",
            "router_mode",
            "prompt_token_estimate",
            "task_elapsed_ms",
            "classification_elapsed_ms",
            "constraint_extraction_elapsed_ms",
            "local_solver_elapsed_ms",
            "validation_elapsed_ms",
            "local_proof_elapsed_ms",
            "trap_guard_elapsed_ms",
            "cross_check_elapsed_ms",
            "remote_elapsed_ms",
            "normalization_elapsed_ms",
            "batch_elapsed_ms_at_start",
            "batch_elapsed_ms_at_finish",
            "remaining_budget_ms",
            "local_proof_layers_passed",
            "local_proof_layers_failed",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "tasks.json"
            output_path = Path(tmpdir) / "results.json"
            log_path = Path(tmpdir) / "router.jsonl"
            input_path.write_text(json.dumps([{"task_id": "ok", "prompt": "2+2"}]), encoding="utf-8")
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
            records = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

        self.assertEqual(len(records), 1)
        self.assertTrue(required_fields.issubset(records[0]))


if __name__ == "__main__":
    unittest.main()
