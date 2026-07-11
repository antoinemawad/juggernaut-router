import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from app.agent import _local_model_skip_reason
from app.classifier import classify_prompt
from app.config import DEFAULT_ALLOWED_PLANNING_MODELS, RuntimeConfig, parse_allowed_models
from app.deadline import DeadlineManager
from app.fireworks_client import allowed_model_candidates, ask_fireworks_structured, provider_model_for_dev, select_allowed_model
from app.local_model_client import _bounded_local_max_tokens
from app.local_llm import _extract_text, _format_messages
from app.main import load_tasks, main
from app.normalization import normalize_answer
from app.telemetry import TelemetryLogger
from app.types import SAFE_FALLBACK_ANSWER, AgentResult
from eval.model_matrix import classify_access_error, parse_dev_model_map, provider_model_for
from scripts.check_live_eval_env import validate_live_eval_env
from scripts.debug_fireworks_models import (
    evaluate_model,
    is_ready_state,
    is_not_ready_state,
    official_model_path,
)
from scripts.final_submission_commands import validate_image_ref
from scripts.validate_runtime_recommendation import isolated_env, validate_recommendation
from scripts import check_submission_static
from scripts import build_evidence_manifest
from scripts import compare_local_remote_routes
from scripts import compare_eval_reports
from scripts import recommend_runtime_env
from scripts import summarize_model_matrix_runs
from scripts import submission_readiness_report


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
    def test_official_track1_aliases_remain_in_config(self):
        self.assertEqual(
            DEFAULT_ALLOWED_PLANNING_MODELS,
            (
                "minimax-m3",
                "kimi-k2p7-code",
                "gemma-4-31b-it",
                "gemma-4-26b-a4b-it",
                "gemma-4-31b-it-nvfp4",
            ),
        )

    def test_model_access_classifier_categorizes_plain_404_as_no_access(self):
        self.assertEqual(
            classify_access_error("HTTPError: HTTP Error 404: Not Found body={\"code\":\"NOT_FOUND\"}"),
            "not_found_or_no_access",
        )

    def test_deployment_state_helpers(self):
        self.assertTrue(is_not_ready_state("CREATING"))
        self.assertTrue(is_not_ready_state("INITIALIZING"))
        self.assertTrue(is_not_ready_state("STARTING"))
        self.assertTrue(is_ready_state("READY"))
        self.assertTrue(is_ready_state("RUNNING"))

    def test_404_while_deployment_creating_is_deployment_not_ready(self):
        deployment = {
            "name": "accounts/antoinemawad-j26hhi0/deployments/demo",
            "displayName": "gemma-4-26b-a4b-it",
            "baseModel": official_model_path("gemma-4-26b-a4b-it"),
            "state": "CREATING",
            "status": None,
            "desiredReplicaCount": 1,
            "directRouteHandle": None,
            "directRouteType": None,
            "activeModelVersion": None,
        }
        with patch(
            "scripts.debug_fireworks_models.call_chat_model",
            return_value=type("Result", (), {
                "status": "not_found_or_no_access",
                "http_status": 404,
                "answer": "",
                "latency_ms": 1.0,
                "error": "HTTPError: HTTP Error 404: Not Found",
            })(),
        ):
            result = evaluate_model("gemma-4-26b-a4b-it", [deployment], "antoinemawad-j26hhi0", False)

        self.assertEqual(result["status"], "deployment_not_ready")
        self.assertTrue(result["deployment_summary"]["any_not_ready"])

    def test_ready_deployment_is_recorded_as_callable_candidate(self):
        deployment = {
            "name": "accounts/antoinemawad-j26hhi0/deployments/demo",
            "displayName": "gemma-4-26b-a4b-it",
            "baseModel": official_model_path("gemma-4-26b-a4b-it"),
            "state": "READY",
            "status": None,
            "desiredReplicaCount": 1,
            "directRouteHandle": None,
            "directRouteType": None,
            "activeModelVersion": None,
        }
        with patch(
            "scripts.debug_fireworks_models.call_chat_model",
            return_value=type("Result", (), {
                "status": "ok",
                "http_status": 200,
                "answer": "OK",
                "latency_ms": 1.0,
                "error": None,
            })(),
        ):
            result = evaluate_model("gemma-4-26b-a4b-it", [deployment], "antoinemawad-j26hhi0", False)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["deployment_summary"]["any_ready"])

    def test_static_submission_guard_core_checks_pass(self):
        self.assertEqual(check_submission_static.check_no_forbidden_runtime_url(), [])
        self.assertEqual(check_submission_static.check_no_forbidden_tracked_files(), [])
        self.assertEqual(check_submission_static.check_ignore_files(), [])
        self.assertEqual(check_submission_static.check_dockerfile_is_submission_scoped(), [])

    def test_dockerfile_restores_qwen25_local_model_build_defaults(self):
        dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ARG ENABLE_LOCAL_MODEL=false", dockerfile)
        self.assertIn(
            "ARG LOCAL_MODEL_URL=https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
            dockerfile,
        )
        self.assertIn("ARG LOCAL_MODEL_FILENAME=local-model.gguf", dockerfile)
        self.assertIn("LOCAL_MODEL_ENABLED=${ENABLE_LOCAL_MODEL}", dockerfile)
        self.assertIn("LOCAL_MODEL_PATH=/app/models/${LOCAL_MODEL_FILENAME}", dockerfile)
        self.assertIn("LOCAL_MODEL_BATCH_LIMIT=6", dockerfile)
        self.assertIn("LOCAL_MODEL_CATEGORIES=sentiment_classification,text_summarisation", dockerfile)
        self.assertIn("LOCAL_MODEL_MAX_TOKENS=128", dockerfile)
        self.assertIn("LOCAL_MODEL_CONTEXT=1024", dockerfile)
        self.assertIn("LOCAL_MODEL_THREADS=2", dockerfile)
        self.assertIn("LOCAL_MODEL_TEMPERATURE=0", dockerfile)
        self.assertIn("LOCAL_MODEL_TIMEOUT_SECONDS=10", dockerfile)
        self.assertIn("LOCAL_MODEL_MAX_CHARS=4096", dockerfile)

    def test_dockerfile_local_model_selection_is_deterministic_and_hardened(self):
        dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY models ./models", dockerfile)
        self.assertIn('target="/app/models/${LOCAL_MODEL_FILENAME}"', dockerfile)
        self.assertIn("Using exact bundled model:", dockerfile)
        self.assertIn("Downloading local model from configured LOCAL_MODEL_URL", dockerfile)
        self.assertIn("find /app/models -maxdepth 1 -type f -name '*.gguf' | sort | head -n 1", dockerfile)
        self.assertIn("No local GGUF model was found.", dockerfile)
        self.assertIn("test -s", dockerfile)

    def test_dockerfile_preserves_current_fireworks_routing_values(self):
        dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
        expected_values = {
            "ROUTER_PROMPT_POLICY_REMOTE_ACCURACY": "answer_only",
            "ROUTER_PROMPT_POLICY_REMOTE_CODE": "answer_only",
            "ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT": "answer_only",
            "ROUTER_PROMPT_POLICY_REMOTE_CONCISE": "answer_only",
            "ROUTER_PROMPT_POLICY_BY_CATEGORY": (
                "sentiment_classification=answer_only;named_entity_recognition=answer_only;"
                "mathematical_reasoning=final_only;logical_deductive_reasoning=final_only;"
                "code_generation=answer_only;code_debugging=answer_only;factual_knowledge=answer_only;"
                "text_summarisation=answer_only"
            ),
            "ROUTER_MODELS_REMOTE_ACCURACY": "gemma-4-31b-it,kimi-k2p7-code,gemma-4-26b-a4b-it,minimax-m3",
            "ROUTER_MODELS_REMOTE_CODE": "kimi-k2p7-code,gemma-4-31b-it,gemma-4-26b-a4b-it,minimax-m3",
            "ROUTER_MODELS_REMOTE_FORMAT_STRICT": "gemma-4-31b-it,kimi-k2p7-code,gemma-4-26b-a4b-it,minimax-m3",
            "ROUTER_MODELS_REMOTE_CONCISE": "gemma-4-26b-a4b-it,gemma-4-31b-it,kimi-k2p7-code,minimax-m3",
            "ROUTER_MODELS_REMOTE_ESCALATION": "gemma-4-31b-it,kimi-k2p7-code,gemma-4-26b-a4b-it,minimax-m3",
            "ROUTER_MODELS_BY_CATEGORY": (
                "code_debugging=kimi-k2p7-code,gemma-4-31b-it,gemma-4-26b-a4b-it,minimax-m3;"
                "code_generation=kimi-k2p7-code,gemma-4-31b-it,gemma-4-26b-a4b-it,minimax-m3;"
                "factual_knowledge=gemma-4-31b-it,kimi-k2p7-code,gemma-4-26b-a4b-it,minimax-m3;"
                "logical_deductive_reasoning=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3;"
                "mathematical_reasoning=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3;"
                "named_entity_recognition=gemma-4-31b-it,gemma-4-26b-a4b-it,kimi-k2p7-code,minimax-m3;"
                "sentiment_classification=gemma-4-26b-a4b-it,gemma-4-31b-it,kimi-k2p7-code,minimax-m3;"
                "text_summarisation=gemma-4-26b-a4b-it,gemma-4-31b-it,kimi-k2p7-code,minimax-m3"
            ),
        }
        for name, value in expected_values.items():
            self.assertIn(f"{name}={value}", dockerfile)
        self.assertIn(
            "FIREWORKS_MAX_TOKENS_BY_CATEGORY="
            "sentiment_classification=12,named_entity_recognition=96,"
            "mathematical_reasoning=160,logical_deductive_reasoning=160,"
            "factual_knowledge=224,text_summarisation=224,"
            "code_generation=512,code_debugging=448",
            dockerfile,
        )

    def test_dockerfile_exposes_supported_runtime_variables_without_secret_defaults(self):
        dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text(encoding="utf-8")
        for name in (
            "INPUT_PATH",
            "OUTPUT_PATH",
            "FIREWORKS_TIMEOUT_SECONDS",
            "FIREWORKS_MAX_RETRIES",
            "FIREWORKS_DISABLE_MAX_TOKENS",
            "FIREWORKS_MAX_TOKENS",
            "FIREWORKS_MAX_TOKENS_BY_CATEGORY",
            "ROUTER_PROFILE",
            "ROUTER_MODE",
            "LOCAL_CONFIDENCE_THRESHOLD",
            "LOCAL_PROOF_BUDGET_MS",
            "LOCAL_CROSS_CHECK_ENABLED",
            "LOCAL_MODEL_ENABLED",
            "LOCAL_MODEL_COMMAND",
            "LOCAL_MODEL_PATH",
            "LOCAL_MODEL_MAX_TOKENS",
            "LOCAL_MODEL_CONTEXT",
            "LOCAL_MODEL_THREADS",
            "LOCAL_MODEL_TEMPERATURE",
            "LOCAL_MODEL_TIMEOUT_SECONDS",
            "LOCAL_MODEL_MAX_CHARS",
            "LOCAL_MODEL_BATCH_LIMIT",
            "BATCH_DEADLINE_SECONDS",
            "DEADLINE_SAFETY_MARGIN_SECONDS",
            "REMOTE_WORKER_COUNT",
            "REMOTE_VALIDATION_ESCALATION_ENABLED",
            "ROUTER_PROMPT_POLICY_REMOTE_ACCURACY",
            "ROUTER_PROMPT_POLICY_REMOTE_CODE",
            "ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT",
            "ROUTER_PROMPT_POLICY_REMOTE_CONCISE",
            "ROUTER_PROMPT_POLICY_BY_CATEGORY",
            "ROUTER_MODELS_REMOTE_ACCURACY",
            "ROUTER_MODELS_REMOTE_CODE",
            "ROUTER_MODELS_REMOTE_FORMAT_STRICT",
            "ROUTER_MODELS_REMOTE_CONCISE",
            "ROUTER_MODELS_REMOTE_ESCALATION",
            "ROUTER_MODELS_BY_CATEGORY",
        ):
            self.assertIn(name, dockerfile)
        self.assertIn("# FIREWORKS_API_KEY", dockerfile)
        self.assertIn("# FIREWORKS_BASE_URL", dockerfile)
        self.assertIn("# ALLOWED_MODELS", dockerfile)
        self.assertNotIn("FIREWORKS_API_KEY=", dockerfile)
        self.assertNotIn("FIREWORKS_BASE_URL=", dockerfile)

    def test_runtime_local_model_enabled_override_still_wins(self):
        with patch.dict(os.environ, {"LOCAL_MODEL_ENABLED": "false"}, clear=True):
            self.assertFalse(RuntimeConfig.from_env().local_model_enabled)
        with patch.dict(os.environ, {"LOCAL_MODEL_ENABLED": "true"}, clear=True):
            self.assertTrue(RuntimeConfig.from_env().local_model_enabled)

    def test_download_local_model_rejects_empty_file_url(self):
        from scripts.download_local_model import main as download_main

        with tempfile.TemporaryDirectory() as tmp:
            empty_source = Path(tmp) / "empty.gguf"
            empty_source.write_bytes(b"")
            target = Path(tmp) / "target.gguf"
            with patch.dict(
                os.environ,
                {
                    "LOCAL_MODEL_URL": empty_source.as_uri(),
                    "LOCAL_MODEL_TARGET": str(target),
                },
                clear=True,
            ):
                self.assertNotEqual(download_main(), 0)
            self.assertFalse(target.exists())

    def test_download_local_model_accepts_non_empty_file_url(self):
        from scripts.download_local_model import main as download_main

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.gguf"
            source.write_bytes(b"not-a-real-model-but-non-empty")
            target = Path(tmp) / "target.gguf"
            with patch.dict(
                os.environ,
                {
                    "LOCAL_MODEL_URL": source.as_uri(),
                    "LOCAL_MODEL_TARGET": str(target),
                },
                clear=True,
            ):
                self.assertEqual(download_main(), 0)
            self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_live_eval_env_validator_accepts_judging_proxy_env(self):
        errors = validate_live_eval_env({
            "FIREWORKS_API_KEY": "secret",
            "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
            "ALLOWED_MODELS": "minimax-m3,kimi-k2p7-code",
        })
        self.assertEqual(errors, [])

    def test_live_eval_env_validator_rejects_normal_fireworks_host(self):
        errors = validate_live_eval_env({
            "FIREWORKS_API_KEY": "secret",
            "FIREWORKS_BASE_URL": "https://api." + "fireworks.ai/inference/v1",
            "ALLOWED_MODELS": "minimax-m3",
        })
        self.assertTrue(any("judging proxy" in error for error in errors))

    def test_live_eval_env_validator_allows_normal_fireworks_for_explicit_dev_runs(self):
        errors = validate_live_eval_env(
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://api." + "fireworks.ai/inference/v1",
                "ALLOWED_MODELS": "minimax-m3",
            },
            allow_normal_fireworks_dev=True,
        )
        self.assertEqual(errors, [])

    def test_dev_model_map_parses_alias_to_provider_model(self):
        self.assertEqual(
            parse_dev_model_map("minimax-m3=accounts/fireworks/models/dev-model,kimi-k2p7-code=kimi-provider"),
            {
                "minimax-m3": "accounts/fireworks/models/dev-model",
                "kimi-k2p7-code": "kimi-provider",
            },
        )

    def test_provider_model_mapping_only_applies_to_normal_fireworks_dev(self):
        env = {
            "FIREWORKS_BASE_URL": "https://api." + "fireworks.ai/inference/v1",
            "FIREWORKS_DEV_MODEL_MAP": "minimax-m3=accounts/fireworks/models/dev-model",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                provider_model_for("minimax-m3", allow_normal_fireworks_dev=True),
                "accounts/fireworks/models/dev-model",
            )
            self.assertEqual(provider_model_for("minimax-m3", allow_normal_fireworks_dev=False), "minimax-m3")

    def test_live_eval_env_validator_rejects_unexpected_model(self):
        errors = validate_live_eval_env({
            "FIREWORKS_API_KEY": "secret",
            "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
            "ALLOWED_MODELS": "not-a-track1-model",
        })
        self.assertTrue(any("unexpected model" in error for error in errors))

    def test_final_submission_image_ref_validator(self):
        self.assertEqual(validate_image_ref("docker.io/team/juggernaut-router:act2"), [])
        self.assertTrue(validate_image_ref("juggernaut-router:local"))
        self.assertTrue(validate_image_ref("docker.io/team/juggernaut-router"))

    def test_parse_allowed_models_deduplicates_and_strips(self):
        self.assertEqual(parse_allowed_models(" a, b ,,a "), ["a", "b"])

    def test_config_clamps_fireworks_timeout_below_response_ceiling(self):
        with patch.dict(os.environ, {"FIREWORKS_TIMEOUT_SECONDS": "99"}, clear=True):
            config = RuntimeConfig.from_env()
        self.assertEqual(config.fireworks_timeout_seconds, 29)

    def test_config_accepts_accuracy_first_mode(self):
        with patch.dict(os.environ, {"ROUTER_MODE": "accuracy_first"}, clear=True):
            config = RuntimeConfig.from_env()
        self.assertEqual(config.router_mode, "accuracy_first")

    def test_config_maps_accuracy_gate_profile_to_accuracy_first(self):
        with patch.dict(os.environ, {"ROUTER_PROFILE": "accuracy_gate"}, clear=True):
            config = RuntimeConfig.from_env()
        self.assertEqual(config.router_profile, "accuracy_gate")
        self.assertEqual(config.router_mode, "accuracy_first")

    def test_config_parses_local_llm_knobs(self):
        with patch.dict(
            os.environ,
            {
                "LOCAL_MODEL_ENABLED": "true",
                "LOCAL_MODEL_PATH": "/app/models/qwen.gguf",
                "LOCAL_MODEL_MAX_TOKENS": "96",
                "LOCAL_MODEL_BATCH_LIMIT": "7",
                "LOCAL_MODEL_CATEGORIES": "sentiment_classification,text_summarisation",
                "LOCAL_MODEL_CONTEXT": "2048",
                "LOCAL_MODEL_THREADS": "2",
                "LOCAL_MODEL_TEMPERATURE": "0",
            },
            clear=True,
        ):
            config = RuntimeConfig.from_env()

        self.assertTrue(config.local_model_enabled)
        self.assertEqual(str(config.local_model_path), "/app/models/qwen.gguf")
        self.assertEqual(config.local_model_max_tokens, 96)
        self.assertEqual(config.local_model_batch_limit, 7)
        self.assertEqual(config.local_model_categories, ("sentiment_classification", "text_summarisation"))
        self.assertEqual(config.local_model_context, 2048)
        self.assertEqual(config.local_model_threads, 2)
        self.assertEqual(config.local_model_temperature, 0)

    def test_local_model_token_budget_is_bounded_by_prompt_type(self):
        self.assertEqual(
            _bounded_local_max_tokens("Explain why FIREWORKS_BASE_URL matters.", 128),
            48,
        )
        self.assertEqual(
            _bounded_local_max_tokens("Write a Python function clamp(x, low, high). Return only code.", 128),
            72,
        )
        self.assertEqual(
            _bounded_local_max_tokens("Classify sentiment as positive, negative, or neutral.", 128),
            24,
        )
        self.assertEqual(
            _bounded_local_max_tokens("Extract named entities and label them.", 128),
            64,
        )

    def test_local_llm_extracts_chat_completion_message(self):
        output = {"choices": [{"message": {"content": "neutral"}}]}
        self.assertEqual(_extract_text(output), "neutral")

    def test_local_llm_chat_messages_preserve_system_and_user_roles(self):
        messages = _format_messages("task-1", "Return only 42.", "System instruction")

        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "System instruction")
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("task-1", messages[1]["content"])

    def test_accuracy_gate_skips_local_model_for_ambiguous_long_task(self):
        config = RuntimeConfig(
            input_path=Path("/input/tasks.json"),
            output_path=Path("/output/results.json"),
            router_mode="accuracy_first",
            local_confidence_threshold=0.95,
            fireworks_timeout_seconds=25,
            fireworks_max_retries=0,
            batch_deadline_seconds=600,
            deadline_safety_margin_seconds=60,
            remote_worker_count=2,
            local_proof_budget_ms=100,
            local_cross_check_enabled=True,
            router_log_path=None,
            fireworks_api_key=None,
            fireworks_base_url=None,
            allowed_models=(),
            fireworks_max_tokens=192,
            router_profile="accuracy_gate",
            local_model_enabled=True,
            local_model_path=Path("/app/models/qwen.gguf"),
        )
        prompt = "Maybe answer this ambiguous task: " + ("details " * 300)
        reason = _local_model_skip_reason(config, None, classify_prompt(prompt), prompt)

        self.assertIn(reason, {"ambiguous_task", "prompt_too_long_for_local_model"})

    def test_accuracy_gate_allows_short_verifiable_local_model_task(self):
        config = RuntimeConfig(
            input_path=Path("/input/tasks.json"),
            output_path=Path("/output/results.json"),
            router_mode="accuracy_first",
            local_confidence_threshold=0.95,
            fireworks_timeout_seconds=25,
            fireworks_max_retries=0,
            batch_deadline_seconds=600,
            deadline_safety_margin_seconds=60,
            remote_worker_count=2,
            local_proof_budget_ms=100,
            local_cross_check_enabled=True,
            router_log_path=None,
            fireworks_api_key=None,
            fireworks_base_url=None,
            allowed_models=(),
            fireworks_max_tokens=192,
            router_profile="accuracy_gate",
            local_model_enabled=True,
            local_model_path=Path("/app/models/qwen.gguf"),
        )
        prompt = "Classify sentiment as positive, negative, or neutral: The setup was easy."
        reason = _local_model_skip_reason(config, None, classify_prompt(prompt), prompt)

        self.assertIsNone(reason)

    def test_local_model_category_allowlist_overrides_profile_defaults(self):
        config = RuntimeConfig(
            input_path=Path("/input/tasks.json"),
            output_path=Path("/output/results.json"),
            router_mode="balanced",
            local_confidence_threshold=0.95,
            fireworks_timeout_seconds=25,
            fireworks_max_retries=0,
            batch_deadline_seconds=600,
            deadline_safety_margin_seconds=60,
            remote_worker_count=2,
            local_proof_budget_ms=100,
            local_cross_check_enabled=True,
            router_log_path=None,
            fireworks_api_key=None,
            fireworks_base_url=None,
            allowed_models=(),
            fireworks_max_tokens=192,
            router_profile="token_competitive",
            local_model_enabled=True,
            local_model_path=Path("/app/models/qwen.gguf"),
            local_model_categories=("sentiment_classification",),
        )

        sentiment_prompt = "Classify sentiment as positive, negative, or neutral: The setup was easy."
        factual_prompt = "In one sentence, explain what ROCm is."

        self.assertIsNone(_local_model_skip_reason(config, None, classify_prompt(sentiment_prompt), sentiment_prompt))
        self.assertEqual(
            _local_model_skip_reason(config, None, classify_prompt(factual_prompt), factual_prompt),
            "category_not_local_model_safe",
        )

    def test_local_model_batch_limit_skip_reason(self):
        config = RuntimeConfig(
            input_path=Path("/input/tasks.json"),
            output_path=Path("/output/results.json"),
            router_mode="accuracy_first",
            local_confidence_threshold=0.95,
            fireworks_timeout_seconds=25,
            fireworks_max_retries=0,
            batch_deadline_seconds=600,
            deadline_safety_margin_seconds=60,
            remote_worker_count=2,
            local_proof_budget_ms=100,
            local_cross_check_enabled=True,
            router_log_path=None,
            fireworks_api_key=None,
            fireworks_base_url=None,
            allowed_models=(),
            fireworks_max_tokens=192,
            router_profile="accuracy_gate",
            local_model_enabled=True,
            local_model_path=Path("/app/models/qwen.gguf"),
        )
        prompt = "Explain in one sentence why a GPU is useful for parallel workloads."
        reason = _local_model_skip_reason(config, None, classify_prompt(prompt), prompt, local_model_allowed=False)

        self.assertEqual(reason, "local_model_batch_limit")

    def test_load_tasks_accepts_wrapped_official_shape_and_field_aliases(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "tasks.json"
            input_path.write_text(
                json.dumps({
                    "tasks": [
                        {"id": "q1", "question": "What is ROCm?"},
                        {"uid": "q2", "input": {"text": "Summarize AMD GPUs."}},
                    ]
                }),
                encoding="utf-8",
            )
            config = RuntimeConfig(input_path=input_path, output_path=Path(tmpdir) / "out.json", router_mode="conservative", local_confidence_threshold=0.95, fireworks_timeout_seconds=25, fireworks_max_retries=0, batch_deadline_seconds=600, deadline_safety_margin_seconds=60, remote_worker_count=2, local_proof_budget_ms=100, local_cross_check_enabled=True, router_log_path=None, fireworks_api_key=None, fireworks_base_url=None, allowed_models=(), fireworks_max_tokens=192)

            tasks, error, diagnostics = load_tasks(config)

        self.assertIsNone(error)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["task_id"], "q1")
        self.assertEqual(tasks[0]["prompt"], "What is ROCm?")
        self.assertEqual(tasks[1]["task_id"], "q2")
        self.assertIn("Summarize AMD GPUs", tasks[1]["prompt"])
        self.assertEqual(diagnostics["tasks_parsed"], 2)

    def test_load_tasks_discovers_single_json_file_when_default_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir)
            (input_dir / "input.json").write_text(
                json.dumps([{"id": "q1", "text": "Classify sentiment: good."}]),
                encoding="utf-8",
            )
            config = RuntimeConfig(input_path=input_dir / "tasks.json", output_path=input_dir / "out.json", router_mode="conservative", local_confidence_threshold=0.95, fireworks_timeout_seconds=25, fireworks_max_retries=0, batch_deadline_seconds=600, deadline_safety_margin_seconds=60, remote_worker_count=2, local_proof_budget_ms=100, local_cross_check_enabled=True, router_log_path=None, fireworks_api_key=None, fireworks_base_url=None, allowed_models=(), fireworks_max_tokens=192)

            tasks, error, diagnostics = load_tasks(config)

        self.assertIsNone(error)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], "q1")
        self.assertEqual(diagnostics["input_path_used"], str(input_dir / "input.json"))

    def test_config_parses_local_proof_and_cross_check_knobs(self):
        with patch.dict(
            os.environ,
            {
                "LOCAL_PROOF_BUDGET_MS": "250",
                "LOCAL_CROSS_CHECK_ENABLED": "false",
                "LOCAL_MODEL_ENABLED": "true",
                "LOCAL_MODEL_COMMAND": "local-model-wrapper",
                "LOCAL_MODEL_TIMEOUT_SECONDS": "17",
                "LOCAL_MODEL_MAX_CHARS": "2048",
            },
            clear=True,
        ):
            config = RuntimeConfig.from_env()
        self.assertEqual(config.local_proof_budget_ms, 250)
        self.assertFalse(config.local_cross_check_enabled)
        self.assertTrue(config.local_model_enabled)
        self.assertEqual(config.local_model_command, "local-model-wrapper")
        self.assertEqual(config.local_model_timeout_seconds, 17)
        self.assertEqual(config.local_model_max_chars, 2048)

    def test_config_parses_remote_prompt_policy_knobs(self):
        with patch.dict(
            os.environ,
            {
                "ROUTER_PROMPT_POLICY_REMOTE_ACCURACY": "original",
                "ROUTER_PROMPT_POLICY_REMOTE_CODE": "final_only",
                "ROUTER_PROMPT_POLICY_REMOTE_FORMAT_STRICT": "compact",
                "ROUTER_PROMPT_POLICY_REMOTE_CONCISE": "invalid-policy",
                "ROUTER_PROMPT_POLICY_BY_CATEGORY": "code_generation=compact,mathematical_reasoning=answer_only,bad=invalid",
            },
            clear=True,
        ):
            config = RuntimeConfig.from_env()
        self.assertEqual(config.prompt_policy_remote_accuracy, "original")
        self.assertEqual(config.prompt_policy_remote_code, "final_only")
        self.assertEqual(config.prompt_policy_remote_format_strict, "compact")
        self.assertEqual(config.prompt_policy_remote_concise, "compact")
        self.assertEqual(config.prompt_policy_by_category, {
            "code_generation": "compact",
            "mathematical_reasoning": "answer_only",
        })

    def test_config_parses_remote_model_preference_knobs(self):
        with patch.dict(
            os.environ,
            {
                "ROUTER_MODELS_REMOTE_ACCURACY": "gemma-4-31b-it,minimax-m3,gemma-4-31b-it",
                "ROUTER_MODELS_REMOTE_CODE": "kimi-k2p7-code",
                "ROUTER_MODELS_REMOTE_FORMAT_STRICT": "gemma-4-26b-a4b-it,kimi-k2p7-code",
                "ROUTER_MODELS_REMOTE_CONCISE": "",
            },
            clear=True,
        ):
            config = RuntimeConfig.from_env()
        self.assertEqual(config.models_remote_accuracy, ("gemma-4-31b-it", "minimax-m3"))
        self.assertEqual(config.models_remote_code, ("kimi-k2p7-code",))
        self.assertEqual(config.models_remote_format_strict, ("gemma-4-26b-a4b-it", "kimi-k2p7-code"))
        self.assertEqual(config.models_remote_concise, ("minimax-m3", "gemma-4-26b-a4b-it", "gemma-4-31b-it"))

    def test_config_parses_category_token_budgets(self):
        with patch.dict(
            os.environ,
            {
                "FIREWORKS_MAX_TOKENS": "192",
                "FIREWORKS_MAX_TOKENS_BY_CATEGORY": (
                    "sentiment_classification=64,code_generation=512,bad=not-int,text_summarisation=99999"
                ),
            },
            clear=True,
        ):
            config = RuntimeConfig.from_env()

        self.assertEqual(config.fireworks_max_tokens, 192)
        self.assertEqual(config.fireworks_max_tokens_by_category["sentiment_classification"], 64)
        self.assertEqual(config.fireworks_max_tokens_by_category["code_generation"], 512)
        self.assertEqual(config.fireworks_max_tokens_by_category["text_summarisation"], 4096)
        self.assertNotIn("bad", config.fireworks_max_tokens_by_category)

    def test_config_can_disable_fireworks_max_tokens(self):
        with patch.dict(
            os.environ,
            {
                "FIREWORKS_DISABLE_MAX_TOKENS": "true",
                "FIREWORKS_MAX_TOKENS": "4096",
                "FIREWORKS_MAX_TOKENS_BY_CATEGORY": "code_generation=512",
            },
            clear=True,
        ):
            config = RuntimeConfig.from_env()

        self.assertTrue(config.fireworks_disable_max_tokens)
        self.assertEqual(config.fireworks_max_tokens, 4096)
        self.assertEqual(config.fireworks_max_tokens_by_category["code_generation"], 512)

    def test_config_loads_runtime_recommendation_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recommendation = Path(tmpdir) / "recommendation.json"
            recommendation.write_text(
                json.dumps({
                    "exports": {
                        "ROUTER_MODE": "balanced",
                        "LOCAL_CONFIDENCE_THRESHOLD": "0.91",
                        "FIREWORKS_MAX_TOKENS": "192",
                        "ROUTER_PROMPT_POLICY_BY_CATEGORY": "mathematical_reasoning=answer_only",
                        "ROUTER_MODELS_BY_CATEGORY": "mathematical_reasoning=kimi-k2p7-code,minimax-m3",
                        "FIREWORKS_API_KEY": "must-not-load",
                    }
                }) + "\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"ROUTER_RECOMMENDATION_PATH": str(recommendation)}, clear=True):
                config = RuntimeConfig.from_env()

        self.assertEqual(config.router_mode, "balanced")
        self.assertEqual(config.local_confidence_threshold, 0.91)
        self.assertEqual(config.fireworks_max_tokens, 192)
        self.assertEqual(config.prompt_policy_by_category, {"mathematical_reasoning": "answer_only"})
        self.assertEqual(config.models_by_category, {
            "mathematical_reasoning": ("kimi-k2p7-code", "minimax-m3"),
        })
        self.assertIsNone(config.fireworks_api_key)

    def test_explicit_env_overrides_runtime_recommendation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recommendation = Path(tmpdir) / "recommendation.json"
            recommendation.write_text(
                json.dumps({
                    "exports": {
                        "ROUTER_MODE": "balanced",
                        "FIREWORKS_MAX_TOKENS": "192",
                    }
                }) + "\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "ROUTER_RECOMMENDATION_PATH": str(recommendation),
                    "ROUTER_MODE": "aggressive",
                    "FIREWORKS_MAX_TOKENS": "128",
                },
                clear=True,
            ):
                config = RuntimeConfig.from_env()

        self.assertEqual(config.router_mode, "aggressive")
        self.assertEqual(config.fireworks_max_tokens, 128)

    def test_readiness_report_summarizes_latest_eval_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            eval_runs = Path(tmpdir)
            router_path = eval_runs / "router_sweep_20260708_010101.jsonl"
            router_path.write_text(
                json.dumps({
                    "config": "strict_hybrid",
                    "passed": True,
                    "total_tokens": 10,
                }) + "\n",
                encoding="utf-8",
            )
            router_path.with_suffix(".md").write_text("Recommended config: `strict_hybrid`\n", encoding="utf-8")

            matrix_path = eval_runs / "model_matrix_20260708_010101.jsonl"
            matrix_path.write_text(
                json.dumps({
                    "model": "minimax-m3",
                    "prompt_policy": "compact",
                    "passed": False,
                    "total_tokens": 12,
                    "error": "x",
                }) + "\n",
                encoding="utf-8",
            )
            matrix_path.with_suffix(".md").write_text("Mode: mock\n", encoding="utf-8")

            agent_path = eval_runs / "agent_matrix_20260708_010101.jsonl"
            agent_path.write_text(
                json.dumps({
                    "category": "code_generation",
                    "passed": True,
                    "score": 1.0,
                    "total_tokens": 0,
                }) + "\n",
                encoding="utf-8",
            )
            agent_path.with_suffix(".md").write_text("Mode: local/runtime\n", encoding="utf-8")

            with patch.object(submission_readiness_report, "EVAL_RUNS", eval_runs):
                router = submission_readiness_report.latest_router_sweep_summary()
                matrix = submission_readiness_report.latest_model_matrix_summary()
                agent = submission_readiness_report.latest_agent_matrix_summary()

        self.assertEqual(router["recommended_config"], "strict_hybrid")
        self.assertEqual(router["rows"], 1)
        self.assertEqual(router["total_tokens"], 10)
        self.assertEqual(matrix["mode"], "mock")
        self.assertEqual(matrix["errors"], 1)
        self.assertEqual(matrix["models"], ["minimax-m3"])
        self.assertEqual(agent["mode"], "local/runtime")
        self.assertEqual(agent["categories"]["code_generation"]["pass_rate"], 1.0)

    def test_readiness_report_blocks_bad_recommendation_evidence(self):
        acceptance = {"status": "passed"}
        quality = {"status": "passed"}
        recommendation = {"status": "needs_more_evidence"}

        status = submission_readiness_report.readiness_status(
            acceptance,
            quality,
            docker=None,
            recommendation=recommendation,
        )

        self.assertEqual(status, "blocked_recommendation_evidence_not_passed")

    def test_readiness_report_accepts_agent_matrix_for_ineligible_categories(self):
        acceptance = {"status": "passed"}
        quality = {"status": "passed"}
        recommendation = {
            "status": "needs_more_evidence",
            "missing_categories": [],
            "ineligible_categories": ["code_generation", "text_summarisation"],
        }
        agent_matrix = {
            "status": "present",
            "categories": {
                "code_generation": {"pass_rate": 1.0, "avg_score": 1.0, "errors": 0},
                "text_summarisation": {"pass_rate": 0.80, "avg_score": 0.80, "errors": 0},
            },
        }

        status = submission_readiness_report.readiness_status(
            acceptance,
            quality,
            docker=None,
            recommendation=recommendation,
            agent_matrix=agent_matrix,
        )

        self.assertEqual(status, "ready_for_live_eval_or_final_submission_prep")

    def test_readiness_report_summarizes_recommendation_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recommendation_path = Path(tmpdir) / "recommendation.json"
            recommendation_path.write_text(
                json.dumps({
                    "evidence_status": "needs_more_evidence",
                    "rows": 72,
                    "runs": 1,
                    "evidence": {
                        "missing_categories": ["code_generation"],
                        "ineligible_categories": ["sentiment_classification"],
                    },
                    "exports": {
                        "ROUTER_MODE": "conservative",
                    },
                }) + "\n",
                encoding="utf-8",
            )

            summary = submission_readiness_report.recommendation_summary(recommendation_path)

        self.assertEqual(summary["status"], "needs_more_evidence")
        self.assertEqual(summary["rows"], 72)
        self.assertEqual(summary["missing_categories"], ["code_generation"])
        self.assertEqual(summary["ineligible_categories"], ["sentiment_classification"])
        self.assertEqual(summary["export_count"], 1)

    def test_readiness_report_infers_legacy_recommendation_evidence(self):
        categories = (
            "code_debugging",
            "code_generation",
            "factual_knowledge",
            "logical_deductive_reasoning",
            "mathematical_reasoning",
            "named_entity_recognition",
            "sentiment_classification",
            "text_summarisation",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            recommendation_path = Path(tmpdir) / "legacy_recommendation.json"
            recommendation_path.write_text(
                json.dumps({
                    "rows": 240,
                    "runs": 3,
                    "recommendations": {
                        category: {
                            "model": "kimi-k2p7-code",
                            "prompt_policy": "original",
                            "eligible": True,
                        }
                        for category in categories
                    },
                    "exports": {
                        "ROUTER_MODE": "conservative",
                    },
                }) + "\n",
                encoding="utf-8",
            )

            summary = submission_readiness_report.recommendation_summary(recommendation_path)

        self.assertEqual(summary["status"], "passed")
        self.assertTrue(summary["inferred_legacy_evidence"])
        self.assertEqual(summary["missing_categories"], [])
        self.assertEqual(summary["ineligible_categories"], [])

    def test_compare_eval_reports_ranks_multiple_candidates(self):
        records = [
            {
                "path": "candidate_low_tokens.jsonl",
                "summary": {"pass_rate": 1.0, "avg_score": 1.0, "total_tokens": 50},
            },
            {
                "path": "candidate_high_tokens.jsonl",
                "summary": {"pass_rate": 1.0, "avg_score": 1.0, "total_tokens": 100},
            },
            {
                "path": "candidate_lower_accuracy.jsonl",
                "summary": {"pass_rate": 0.9, "avg_score": 0.95, "total_tokens": 10},
            },
        ]

        ranked = compare_eval_reports.rank_candidates(records)

        self.assertEqual([item["path"] for item in ranked], [
            "candidate_low_tokens.jsonl",
            "candidate_high_tokens.jsonl",
            "candidate_lower_accuracy.jsonl",
        ])

    def test_model_matrix_multi_run_summary_recommends_by_category(self):
        rows = [
            {
                "run_id": "r1",
                "category": "code_generation",
                "model": "kimi-k2p7-code",
                "prompt_policy": "compact",
                "passed": True,
                "score": 1.0,
                "total_tokens": 100,
                "latency_ms": 50,
            },
            {
                "run_id": "r2",
                "category": "code_generation",
                "model": "kimi-k2p7-code",
                "prompt_policy": "compact",
                "passed": True,
                "score": 1.0,
                "total_tokens": 90,
                "latency_ms": 45,
            },
            {
                "run_id": "r1",
                "category": "code_generation",
                "model": "gemma-4-31b-it",
                "prompt_policy": "answer_only",
                "passed": True,
                "score": 1.0,
                "total_tokens": 120,
                "latency_ms": 40,
            },
        ]
        _by_model_policy, by_category_model_policy, _by_category = summarize_model_matrix_runs.summarize(rows)

        recommendations = summarize_model_matrix_runs.recommended_by_category(by_category_model_policy)

        self.assertEqual(recommendations["code_generation"][0], ("kimi-k2p7-code", "compact"))
        self.assertEqual(recommendations["code_generation"][1]["runs"], 2)

    def test_model_matrix_summary_can_drop_high_error_runs(self):
        rows = [
            {
                "run_id": "good",
                "category": "factual_knowledge",
                "model": "kimi-k2p7-code",
                "prompt_policy": "original",
                "passed": True,
                "score": 1.0,
                "total_tokens": 100,
                "latency_ms": 20,
                "error": None,
            },
            {
                "run_id": "bad",
                "category": "factual_knowledge",
                "model": "kimi-k2p7-code",
                "prompt_policy": "final_only",
                "passed": False,
                "score": 0.0,
                "total_tokens": 0,
                "latency_ms": 20,
                "error": "HTTPError",
            },
        ]

        filtered, dropped = summarize_model_matrix_runs.filter_rows(rows, max_run_error_rate=0.25)

        self.assertEqual([row["run_id"] for row in filtered], ["good"])
        self.assertEqual(dropped["error_runs"], ["bad"])

    def test_evidence_manifest_summarizes_eval_run_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            jsonl_path = root / "model_matrix_20260708_111058.jsonl"
            jsonl_path.write_text(
                json.dumps({
                    "run_id": "model_matrix_20260708_111058",
                    "timestamp": "2026-07-08T11:10:58+00:00",
                    "passed": True,
                }) + "\n",
                encoding="utf-8",
            )
            jsonl_path.with_suffix(".md").write_text("Mode: live Fireworks\n", encoding="utf-8")
            (root / "local_quality_gate_latest.json").write_text(
                json.dumps({"status": "passed", "timestamp": "2026-07-08T11:00:00+00:00"}) + "\n",
                encoding="utf-8",
            )

            manifest = build_evidence_manifest.build_manifest(root)

        self.assertEqual(manifest["counts"]["jsonl"], 1)
        self.assertEqual(manifest["counts"]["json"], 1)
        self.assertEqual(manifest["counts"]["markdown"], 1)
        self.assertEqual(manifest["jsonl_reports"][0]["type"], "model_matrix")
        self.assertEqual(manifest["jsonl_reports"][0]["rows"], 1)
        self.assertEqual(manifest["jsonl_reports"][0]["mode"], "live Fireworks")

    def test_runtime_env_exports_map_sweep_config_to_runtime_knobs(self):
        config = recommend_runtime_env.config_by_name("strict_hybrid")

        rendered = recommend_runtime_env.render_shell("strict_hybrid", config)

        self.assertIn("Router sweep config: strict_hybrid", rendered)
        self.assertIn("export ROUTER_MODE='conservative'", rendered)
        self.assertIn("export LOCAL_CONFIDENCE_THRESHOLD='0.95'", rendered)
        self.assertIn("export FIREWORKS_MAX_TOKENS='192'", rendered)
        self.assertIn("unset ROUTER_PROMPT_POLICY_BY_CATEGORY", rendered)
        self.assertIn("export ROUTER_MODELS_REMOTE_ACCURACY='minimax-m3'", rendered)
        self.assertNotIn("export ROUTER_MODE='strict_hybrid'", rendered)

    def test_runtime_env_exports_category_prompt_policy_experiment(self):
        config = recommend_runtime_env.config_by_name("strict_hybrid_kimi_prompt_evidence")

        rendered = recommend_runtime_env.render_shell("strict_hybrid_kimi_prompt_evidence", config)

        self.assertIn("export ROUTER_MODE='conservative'", rendered)
        self.assertIn(
            "export ROUTER_PROMPT_POLICY_BY_CATEGORY='code_generation=compact,mathematical_reasoning=answer_only'",
            rendered,
        )
        self.assertIn("export ROUTER_MODELS_REMOTE_CODE='kimi-k2p7-code'", rendered)

    def test_runtime_recommendation_env_is_isolated(self):
        env = isolated_env(
            {
                "ROUTER_MODE": "stale",
                "ROUTER_PROMPT_POLICY_BY_CATEGORY": "old=value",
                "LOCAL_CONFIDENCE_THRESHOLD": "0.1",
                "FIREWORKS_MAX_TOKENS": "999",
                "KEEP_ME": "yes",
            },
            Path("eval_runs/live_runtime_recommendation.json"),
        )

        self.assertEqual(env["KEEP_ME"], "yes")
        self.assertEqual(env["ROUTER_RECOMMENDATION_PATH"], "eval_runs/live_runtime_recommendation.json")
        self.assertNotIn("ROUTER_MODE", env)
        self.assertNotIn("FIREWORKS_MAX_TOKENS", env)
        self.assertNotIn("ROUTER_PROMPT_POLICY_BY_CATEGORY", env)
        self.assertNotIn("LOCAL_CONFIDENCE_THRESHOLD", env)

    def test_runtime_recommendation_validation_writes_pass_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            recommendation = tmp / "recommendation.json"
            recommendation.write_text(
                json.dumps({
                    "exports": {
                        "ROUTER_MODE": "conservative",
                        "FIREWORKS_MAX_TOKENS": "192",
                    }
                }) + "\n",
                encoding="utf-8",
            )
            out_json = tmp / "validation.json"
            out_md = tmp / "validation.md"
            seen_envs = []

            def fake_runner(cmd, env):
                seen_envs.append(env)
                return {
                    "cmd": cmd,
                    "returncode": 0,
                    "started_at": "start",
                    "finished_at": "finish",
                    "output_tail": "",
                }

            report = validate_recommendation(recommendation, out_json, out_md, runner=fake_runner)

            self.assertEqual(report["status"], "passed")
            self.assertTrue(out_json.exists())
            self.assertTrue(out_md.exists())
        self.assertEqual(seen_envs[0]["ROUTER_RECOMMENDATION_PATH"], str(recommendation))
        self.assertNotIn("ROUTER_MODE", seen_envs[0])

    def test_runtime_recommendation_validation_stops_on_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            recommendation = tmp / "recommendation.json"
            recommendation.write_text(json.dumps({"exports": {"ROUTER_MODE": "conservative"}}) + "\n", encoding="utf-8")
            calls = []

            def fake_runner(cmd, env):
                calls.append(cmd)
                return {
                    "cmd": cmd,
                    "returncode": 1,
                    "started_at": "start",
                    "finished_at": "finish",
                    "output_tail": "failed",
                }

            report = validate_recommendation(
                recommendation,
                tmp / "validation.json",
                tmp / "validation.md",
                runner=fake_runner,
            )

        self.assertEqual(report["status"], "failed")
        self.assertEqual(len(calls), 1)

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

    def test_normalize_answer_extracts_embedded_code_block_for_code_only(self):
        answer = normalize_answer("Here is the code:\n\n```python\ndef f():\n    return 1\n```\nDone.", code_only=True)
        self.assertEqual(answer, "def f():\n    return 1")

    def test_normalize_answer_trims_prose_after_python_for_code_only(self):
        answer = normalize_answer("Sure:\ndef f():\n    return 1\n\nThis returns one.", code_only=True)
        self.assertEqual(answer, "def f():\n    return 1")

    def test_normalize_answer_extracts_exact_numeric_when_requested(self):
        answer = normalize_answer("The final price is $66.00 after tax.", exact_numeric=True)
        self.assertEqual(answer, "$66.00")

    def test_normalize_answer_extracts_allowed_label_when_requested(self):
        answer = normalize_answer("The sentiment is negative because the service failed.", allowed_labels=("positive", "negative", "neutral"))
        self.assertEqual(answer, "negative")

    def test_normalize_answer_cleans_entity_label_lines_when_requested(self):
        answer = normalize_answer(
            "Entities:\n- PERSON: Lisa Chen\n- ORG: AMD\n- LOCATION: Austin\n- DATE: July 6, 2026",
            entity_labels=True,
        )
        self.assertEqual(answer, "PERSON: Lisa Chen\nORG: AMD\nLOCATION: Austin\nDATE: July 6, 2026")

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

    def test_fireworks_uses_first_allowed_preferred_model(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(json.dumps({
                "choices": [{"message": {"content": "Code answer"}}],
                "usage": {"completion_tokens": 3, "total_tokens": 9},
            }))

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3,kimi-k2p7-code",
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = ask_fireworks_structured(
                "write code",
                preferred_models=("kimi-k2p7-code", "gemma-4-31b-it"),
            )

        self.assertEqual(result.model, "kimi-k2p7-code")
        self.assertEqual(captured["payload"]["model"], "kimi-k2p7-code")

    def test_fireworks_dev_model_map_only_changes_public_fireworks_payload(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(json.dumps({
                "choices": [{"message": {"content": "Mapped answer"}}],
                "usage": {"completion_tokens": 3, "total_tokens": 9},
            }))

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://api." + "fireworks.ai/inference/v1",
                "ALLOWED_MODELS": "gemma-4-31b-it",
                "FIREWORKS_DEV_MODEL_MAP": (
                    "gemma-4-31b-it=accounts/example/deployments/dev-gemma"
                ),
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = ask_fireworks_structured("hello", preferred_models=("gemma-4-31b-it",))

        self.assertEqual(result.model, "gemma-4-31b-it")
        self.assertEqual(captured["payload"]["model"], "accounts/example/deployments/dev-gemma")

    def test_fireworks_dev_model_map_is_ignored_for_judging_proxy(self):
        self.assertEqual(
            provider_model_for_dev("gemma-4-31b-it", "https://judge-proxy.example/v1"),
            "gemma-4-31b-it",
        )

    def test_fireworks_accepts_mode_specific_system_prompt(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(json.dumps({"choices": [{"message": {"content": "Strict answer"}}]}))

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3",
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = ask_fireworks_structured("hello", system_prompt="Follow format exactly.")

        self.assertEqual(result.answer, "Strict answer")
        self.assertEqual(captured["payload"]["messages"][0]["content"], "Follow format exactly.")

    def test_model_selection_never_uses_disallowed_preferred_model(self):
        config = RuntimeConfig(
            input_path=Path("/input/tasks.json"),
            output_path=Path("/output/results.json"),
            router_mode="conservative",
            local_confidence_threshold=0.95,
            fireworks_timeout_seconds=25,
            fireworks_max_retries=0,
            batch_deadline_seconds=600,
            deadline_safety_margin_seconds=60,
            remote_worker_count=1,
            local_proof_budget_ms=100,
            local_cross_check_enabled=True,
            router_log_path=None,
            fireworks_api_key="secret",
            fireworks_base_url="https://judge-proxy.example",
            allowed_models=("minimax-m3",),
            fireworks_max_tokens=256,
        )
        self.assertEqual(select_allowed_model(config, ("kimi-k2p7-code",)), "minimax-m3")
        self.assertEqual(allowed_model_candidates(config, ("kimi-k2p7-code",)), ["minimax-m3"])

    def test_fireworks_falls_through_to_next_model_after_empty_response(self):
        payload_models = []

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data.decode("utf-8"))
            payload_models.append(payload["model"])
            if payload["model"] == "gemma-4-31b-it":
                return FakeResponse(json.dumps({"choices": [{"message": {"content": None}}]}))
            return FakeResponse(json.dumps({
                "choices": [{"message": {"content": "Fallback model answer"}}],
                "usage": {"completion_tokens": 4, "total_tokens": 12},
            }))

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "gemma-4-31b-it,kimi-k2p7-code",
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = ask_fireworks_structured(
                "hello",
                preferred_models=("gemma-4-31b-it", "kimi-k2p7-code"),
            )

        self.assertEqual(result.answer, "Fallback model answer")
        self.assertEqual(result.model, "kimi-k2p7-code")
        self.assertEqual(result.retry_count, 1)
        self.assertEqual(payload_models, ["gemma-4-31b-it", "kimi-k2p7-code"])

    def test_fireworks_dev_mapping_falls_through_across_provider_models(self):
        payload_models = []

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data.decode("utf-8"))
            payload_models.append(payload["model"])
            if payload["model"] == "accounts/example/deployments/gemma":
                return FakeResponse(json.dumps({"choices": [{"message": {"content": ""}}]}))
            return FakeResponse(json.dumps({"choices": [{"message": {"content": "Kimi worked"}}]}))

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://api." + "fireworks.ai/inference/v1",
                "ALLOWED_MODELS": "gemma-4-31b-it,kimi-k2p7-code",
                "FIREWORKS_DEV_MODEL_MAP": (
                    "gemma-4-31b-it=accounts/example/deployments/gemma;"
                    "kimi-k2p7-code=accounts/fireworks/models/kimi-k2p6"
                ),
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = ask_fireworks_structured(
                "hello",
                preferred_models=("gemma-4-31b-it", "kimi-k2p7-code"),
            )

        self.assertEqual(result.answer, "Kimi worked")
        self.assertEqual(result.model, "kimi-k2p7-code")
        self.assertEqual(
            payload_models,
            ["accounts/example/deployments/gemma", "accounts/fireworks/models/kimi-k2p6"],
        )

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

    def test_parallel_main_preserves_output_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "tasks.json"
            output_path = Path(tmpdir) / "results.json"
            input_path.write_text(
                json.dumps([
                    {"task_id": "slow", "prompt": "slow"},
                    {"task_id": "fast", "prompt": "fast"},
                ]),
                encoding="utf-8",
            )

            def fake_answer_task(task_id, prompt, config=None, deadline=None, local_model_allowed=True):
                if task_id == "slow":
                    time.sleep(0.02)
                return AgentResult(
                    answer=f"{task_id} answer",
                    route="local",
                    route_reason="test",
                )

            with patch.dict(
                os.environ,
                {
                    "INPUT_PATH": str(input_path),
                    "OUTPUT_PATH": str(output_path),
                    "REMOTE_WORKER_COUNT": "2",
                },
                clear=True,
            ), patch("app.main.answer_task", side_effect=fake_answer_task):
                main()

            rows = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(
            rows,
            [
                {"task_id": "slow", "answer": "slow answer"},
                {"task_id": "fast", "answer": "fast answer"},
            ],
        )

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
            "prompt_char_count",
            "prompt_token_estimate",
            "remote_prompt_token_estimate",
            "answer_char_count",
            "answer_token_estimate",
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

    def test_local_remote_compare_aggregates_repeated_runs(self):
        raw_runs = [
            {
                "mode": "remote_only",
                "status": "passed",
                "pass_rate": 0.5,
                "avg_score": 0.6,
                "elapsed_seconds": 10,
                "answers_written": 2,
                "fireworks_count": 2,
                "local_llm_count": 0,
                "fallbacks_count": 0,
                "deterministic_count": 0,
                "route_counts": {"fireworks": 2},
                "error_counts": {},
                "model_counts": {"gemma-4-31b-it": 2},
                "route_reason_counts": {"no_local_solver": 2},
                "by_category": {"factual_knowledge": {"rows": 2, "pass_rate": 0.5, "avg_score": 0.6}},
                "task_scores": [
                    {"task_id": "a", "category": "factual_knowledge", "passed": True, "score": 1.0, "notes": [], "answer": "ok"},
                    {"task_id": "b", "category": "factual_knowledge", "passed": False, "score": 0.2, "notes": ["x"], "answer": "bad"},
                ],
                "failures": [],
                "output_dir": "eval_runs/demo/remote_only/run_01",
            },
            {
                "mode": "remote_only",
                "status": "passed",
                "pass_rate": 1.0,
                "avg_score": 1.0,
                "elapsed_seconds": 14,
                "answers_written": 2,
                "fireworks_count": 2,
                "local_llm_count": 0,
                "fallbacks_count": 0,
                "deterministic_count": 0,
                "route_counts": {"fireworks": 2},
                "error_counts": {},
                "model_counts": {"gemma-4-31b-it": 2},
                "route_reason_counts": {"no_local_solver": 2},
                "by_category": {"factual_knowledge": {"rows": 2, "pass_rate": 1.0, "avg_score": 1.0}},
                "task_scores": [
                    {"task_id": "a", "category": "factual_knowledge", "passed": True, "score": 1.0, "notes": [], "answer": "ok"},
                    {"task_id": "b", "category": "factual_knowledge", "passed": True, "score": 1.0, "notes": [], "answer": "good"},
                ],
                "failures": [],
                "output_dir": "eval_runs/demo/remote_only/run_02",
            },
        ]

        [summary] = compare_local_remote_routes.aggregate_mode_runs(raw_runs)

        self.assertEqual(summary["mode"], "remote_only")
        self.assertEqual(summary["completed_runs"], 2)
        self.assertAlmostEqual(summary["pass_rate"], 0.75)
        self.assertAlmostEqual(summary["elapsed_seconds"], 12.0)
        self.assertEqual(summary["model_counts"], {"gemma-4-31b-it": 4})
        self.assertEqual(summary["unstable_tasks"][0]["task_id"], "b")


if __name__ == "__main__":
    unittest.main()
