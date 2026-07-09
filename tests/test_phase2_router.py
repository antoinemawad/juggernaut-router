import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO

from app.agent import answer_task
from app.classifier import classify_prompt
from app.config import RuntimeConfig
from app.deadline import DeadlineManager
from app.solvers.basic import LocalSolverResult
from app.validators import validate_local_answer
from eval.model_matrix import (
    DEFAULT_SCENARIOS,
    estimate_tokens,
    filter_scenarios_by_categories,
    limit_scenarios,
    load_scenarios,
    parse_categories,
    prompt_for_policy,
    run_case,
    score_answer,
)
from eval import agent_matrix
from eval.router_config_sweep import DEFAULT_CONFIGS, route_matches_expected, run_scenario, summarize
from scripts.check_expected_routes import check_routes, config_by_name
from scripts.recommend_from_model_matrix import (
    choose_by_category,
    evidence_status,
    exports_for_recommendations,
    main as recommend_from_model_matrix_main,
    split_access_failures,
)
from scripts.validate_runtime_recommendation import load_recommendation
from scripts.recommend_runtime_env import exports_for_config


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class FakeResponse:
    def __init__(self, content: str = "Remote answer") -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps({
            "choices": [{"message": {"content": self.content}}],
            "usage": {"completion_tokens": 2, "total_tokens": 10},
        }).encode("utf-8")


class Phase2RouterTests(unittest.TestCase):
    def test_classifier_covers_core_categories(self):
        cases = {
            "A product costs $80 and is discounted by 25%. What is the final price?": "mathematical_reasoning",
            "Classify the sentiment as positive, negative, or neutral: The service was slow.": "sentiment_classification",
            "Summarise the following text in one sentence: AMD builds useful tooling.": "text_summarisation",
            "Extract named entities and label them: Lisa Chen joined AMD in Austin on July 6, 2026.": "named_entity_recognition",
            "Debug this Python code:\n\ndef add_numbers(a, b):\n    return a - b": "code_debugging",
            "Alice is taller than Bob. Bob is taller than Carol. Who is the shortest?": "logical_deductive_reasoning",
            "Write a Python function named is_even that returns True if a number is even. Return only code.": "code_generation",
            "Explain in two sentences how a GPU differs from a CPU.": "factual_knowledge",
        }
        for prompt, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(classify_prompt(prompt).category, expected)

    def test_recommendation_excludes_access_failures_from_quality_scoring(self):
        rows = [
            {
                "run_id": "good",
                "category": "factual_knowledge",
                "model": "kimi-k2p7-code",
                "prompt_policy": "original",
                "passed": True,
                "score": 1.0,
                "total_tokens": 100,
                "error": None,
                "access_status": "ok",
            },
            {
                "run_id": "access",
                "category": "factual_knowledge",
                "model": "gemma-4-26b-a4b-it",
                "prompt_policy": "original",
                "passed": False,
                "score": 0.0,
                "total_tokens": 0,
                "error": "HTTPError: HTTP Error 404: Not Found body={\"code\":\"NOT_FOUND\"}",
                "access_status": "not_found_or_no_access",
            },
        ]
        quality_rows, access_failures = split_access_failures(rows)
        recommendations = choose_by_category(
            rows=quality_rows,
            min_pass_rate=0.80,
            min_avg_score=0.80,
            min_runs=1,
            fallback_model="minimax-m3",
            fallback_policy="original",
        )

        self.assertEqual(len(access_failures), 1)
        self.assertEqual(recommendations["factual_knowledge"]["model"], "kimi-k2p7-code")
        self.assertTrue(recommendations["factual_knowledge"]["eligible"])

    def test_model_matrix_records_null_fireworks_content_as_error(self):
        class NullContentResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps({
                    "choices": [{"message": {"content": None}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
                }).encode("utf-8")

        scenario = {
            "task_id": "null_content",
            "category": "factual_knowledge",
            "prompt": "Return exactly: OK",
            "expected_keywords": ["OK"],
            "expected_answer": "OK",
            "verifier": "keyword_coverage",
        }
        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://api." + "fireworks.ai/inference/v1",
                "FIREWORKS_DEV_MODEL_MAP": "gemma-4-31b-it-nvfp4=accounts/example/deployments/demo",
            },
            clear=True,
        ), patch("urllib.request.urlopen", return_value=NullContentResponse()):
            row = run_case(
                "gemma-4-31b-it-nvfp4",
                scenario,
                live=True,
                max_tokens=16,
                prompt_policy="original",
                allow_normal_fireworks_dev=True,
            )

        self.assertFalse(row["passed"])
        self.assertIn("content was null", row["error"])
        self.assertEqual(row["provider_model"], "accounts/example/deployments/demo")

    def test_risk_components_include_planned_dimensions(self):
        classification = classify_prompt(
            "Classify the sentiment as positive, negative, or neutral: The setup was easy, but unreliable."
        )
        self.assertIn("ambiguity", classification.risk_components)

        code_classification = classify_prompt(
            "Write a Python function clamp(x, low, high). Return only code."
        )
        self.assertIn("code_risk", code_classification.risk_components)

        fresh_classification = classify_prompt("Who is the current CEO of AMD today?")
        self.assertIn("factual_freshness", fresh_classification.risk_components)

        sarcasm_classification = classify_prompt(
            "Classify the sentiment as positive, negative, or neutral: Yeah right, the outage was just perfect."
        )
        self.assertIn("ambiguity", sarcasm_classification.risk_components)

        demo_sarcasm_classification = classify_prompt(
            "Classify the sentiment as positive, negative, or neutral: Great, another crash right before the demo."
        )
        self.assertIn("ambiguity", demo_sarcasm_classification.risk_components)

    def test_corrected_code_prompt_classifies_as_code_debugging(self):
        classification = classify_prompt(
            "Return only corrected code:\n\ndef is_adult(age):\n    return age > 18\n\nThe function should return True for age 18 and above."
        )
        self.assertEqual(classification.category, "code_debugging")

    def test_local_high_confidence_task_does_not_call_fireworks(self):
        with patch("app.agent.ask_fireworks_structured") as mocked:
            result = answer_task("math", "A product costs $80 and is discounted by 25%. What is the final price?")

        mocked.assert_not_called()
        self.assertEqual(result.answer, "$60")
        self.assertEqual(result.route, "local")
        self.assertEqual(result.category, "mathematical_reasoning")
        self.assertIn("risk_gate", result.metadata["local_proof_layers_passed"])
        self.assertFalse(result.metadata["local_proof_layers_failed"])

    def test_stable_cpu_gpu_fact_uses_local_template(self):
        with patch("app.agent.ask_fireworks_structured") as mocked:
            result = answer_task("factual", "Explain in two concise sentences how a GPU differs from a CPU.")

        mocked.assert_not_called()
        self.assertEqual(result.route, "local")
        self.assertEqual(result.category, "factual_knowledge")
        self.assertEqual(result.route_reason, "stable_factual_template")
        self.assertIn("parallel", result.answer)

    def test_classifier_runs_before_remote_call(self):
        seen = []

        def fake_classify(prompt):
            seen.append("classify")
            return classify_prompt(prompt)

        def fake_remote(prompt, config=None, deadline=None, preferred_models=None, system_prompt=None):
            seen.append("remote")
            from app.fireworks_client import FireworksResult

            return FireworksResult(answer="Remote answer", model="minimax-m3", elapsed_ms=1)

        with patch("app.agent.classify_prompt", side_effect=fake_classify), patch(
            "app.agent.ask_fireworks_structured", side_effect=fake_remote
        ):
            result = answer_task("remote", "Explain a difficult thing.")

        self.assertEqual(result.route, "fireworks")
        self.assertEqual(seen, ["classify", "remote"])

    def test_risky_task_routes_to_fireworks_wrapper(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            return FakeResponse()

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3,kimi-k2p7-code",
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = answer_task(
                "mixed",
                "Classify the sentiment as positive, negative, or neutral: The setup was easy, but unreliable.",
            )

        self.assertEqual(result.route, "fireworks")
        self.assertEqual(result.selected_model, "minimax-m3")
        self.assertEqual(result.remote_mode, "remote_accuracy")
        self.assertEqual(result.prompt_policy, "compact")
        self.assertEqual(captured["url"], "https://judge-proxy.example/v1/chat/completions")
        self.assertIn("trap_guard", result.metadata["local_proof_layers_failed"])

    def test_valid_local_model_answer_prevents_fireworks_call(self):
        from app.local_model_client import LocalModelResult

        with patch.dict(
            os.environ,
            {
                "LOCAL_MODEL_ENABLED": "true",
                "LOCAL_MODEL_COMMAND": "mock-local-model",
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3",
            },
            clear=True,
        ), patch(
            "app.agent.ask_local_model_structured",
            return_value=LocalModelResult(answer="negative", elapsed_ms=3),
        ) as local_model, patch("app.agent.ask_fireworks_structured") as fireworks:
            result = answer_task(
                "local_model_sentiment",
                "Classify the sentiment as positive, negative, or neutral. Return only the label: Yeah right, the outage was just perfect.",
            )

        local_model.assert_called_once()
        fireworks.assert_not_called()
        self.assertEqual(result.route, "local_model")
        self.assertEqual(result.answer, "negative")
        self.assertEqual(result.total_tokens, 0)
        self.assertEqual(result.timings.local_model_elapsed_ms, 3)

    def test_invalid_local_model_answer_falls_through_to_fireworks(self):
        from app.fireworks_client import FireworksResult
        from app.local_model_client import LocalModelResult

        with patch.dict(
            os.environ,
            {
                "LOCAL_MODEL_ENABLED": "true",
                "LOCAL_MODEL_COMMAND": "mock-local-model",
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3",
            },
            clear=True,
        ), patch(
            "app.agent.ask_local_model_structured",
            return_value=LocalModelResult(answer="The user wants me to choose a label.", elapsed_ms=3),
        ), patch(
            "app.agent.ask_fireworks_structured",
            return_value=FireworksResult(answer="negative", model="minimax-m3", completion_tokens=1, total_tokens=8),
        ) as fireworks:
            result = answer_task(
                "remote_after_bad_local_model",
                "Classify the sentiment as positive, negative, or neutral. Return only the label: Yeah right, the outage was just perfect.",
            )

        fireworks.assert_called_once()
        self.assertEqual(result.route, "fireworks")
        self.assertEqual(result.answer, "negative")
        self.assertEqual(result.total_tokens, 8)
        self.assertIn("reasoning_leakage", result.metadata["local_model_validation_failed"])

    def test_remote_accuracy_prompt_policy_can_be_overridden(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse("negative")

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3",
                "ROUTER_PROMPT_POLICY_REMOTE_ACCURACY": "original",
                "REMOTE_VALIDATION_ESCALATION_ENABLED": "false",
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = answer_task(
                "sentiment",
                "Classify the sentiment as positive, negative, or neutral: The setup was easy, but unreliable.",
            )

        self.assertEqual(result.remote_mode, "remote_accuracy")
        self.assertEqual(result.prompt_policy, "original")
        self.assertTrue(captured["payload"]["messages"][1]["content"].startswith("Classify the sentiment"))
        self.assertNotIn("Do not restate the task", captured["payload"]["messages"][1]["content"])

    def test_category_prompt_policy_override_beats_remote_mode_default(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse("def clamp(x, low, high):\n    return max(low, min(x, high))")

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "kimi-k2p7-code",
                "ROUTER_PROMPT_POLICY_REMOTE_CODE": "final_only",
                "ROUTER_PROMPT_POLICY_BY_CATEGORY": "code_generation=compact",
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = answer_task(
                "codegen",
                "Write Python code only: define clamp(x, low, high). Return only code.",
            )

        self.assertEqual(result.remote_mode, "remote_code")
        self.assertEqual(result.prompt_policy, "compact")
        self.assertIn("Answer accurately and concisely", captured["payload"]["messages"][1]["content"])
        self.assertNotIn("Final answer only:", captured["payload"]["messages"][1]["content"])

    def test_remote_accuracy_model_preference_can_be_overridden(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse("negative")

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3,gemma-4-31b-it,kimi-k2p7-code",
                "ROUTER_MODELS_REMOTE_ACCURACY": "gemma-4-31b-it,minimax-m3,kimi-k2p7-code",
                "REMOTE_VALIDATION_ESCALATION_ENABLED": "false",
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = answer_task(
                "sentiment",
                "Classify the sentiment as positive, negative, or neutral: The setup was easy, but unreliable.",
            )

        self.assertEqual(result.remote_mode, "remote_accuracy")
        self.assertEqual(result.selected_model, "gemma-4-31b-it")
        self.assertEqual(captured["payload"]["model"], "gemma-4-31b-it")

    def test_category_model_preference_beats_remote_mode_default(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse("negative")

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3,kimi-k2p7-code",
                "ROUTER_MODELS_REMOTE_ACCURACY": "minimax-m3",
                "ROUTER_MODELS_BY_CATEGORY": "sentiment_classification=kimi-k2p7-code,minimax-m3",
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = answer_task(
                "sentiment",
                "Classify the sentiment as positive, negative, or neutral: The setup was easy, but unreliable.",
            )

        self.assertEqual(result.remote_mode, "remote_accuracy")
        self.assertEqual(result.selected_model, "kimi-k2p7-code")
        self.assertEqual(captured["payload"]["model"], "kimi-k2p7-code")

    def test_category_model_preference_still_respects_allowed_models(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse("negative")

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3",
                "ROUTER_MODELS_REMOTE_ACCURACY": "minimax-m3",
                "ROUTER_MODELS_BY_CATEGORY": "sentiment_classification=kimi-k2p7-code,minimax-m3",
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = answer_task(
                "sentiment",
                "Classify the sentiment as positive, negative, or neutral: The setup was easy, but unreliable.",
            )

        self.assertEqual(result.selected_model, "minimax-m3")
        self.assertEqual(captured["payload"]["model"], "minimax-m3")

    def test_ambiguous_ner_routes_remote_instead_of_unsafe_local(self):
        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3",
            },
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse()):
            result = answer_task(
                "ner",
                "Extract named entities and label them: Google DeepMind announced Gemma support with AMD in London on July 7, 2026.",
            )

        self.assertEqual(result.route, "fireworks")
        self.assertIn("cross_check", result.metadata["local_proof_layers_failed"])

    def test_remote_ner_answer_is_normalized_to_entity_lines(self):
        from app.fireworks_client import FireworksResult

        with patch("app.agent.ask_fireworks_structured") as mocked_remote:
            mocked_remote.return_value = FireworksResult(
                answer="Entities:\n- PERSON: Lisa Chen\n- ORG: AMD\n- LOCATION: Austin\n- DATE: July 6, 2026",
                model="minimax-m3",
            )
            result = answer_task(
                "ner",
                "Extract named entities and label them: Google DeepMind announced Gemma support with AMD in London on July 7, 2026.",
            )

        self.assertEqual(result.route, "fireworks")
        self.assertEqual(result.remote_mode, "remote_format_strict")
        self.assertEqual(result.answer, "PERSON: Lisa Chen\nORG: AMD\nLOCATION: Austin\nDATE: July 6, 2026")

    def test_exact_summary_routes_remote_for_format_control(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3",
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = answer_task(
                "summary",
                "Summarise in exactly 12 words: Unfamiliar deployment notes describe retries, queues, dashboards, incidents, and rollback timing.",
            )

        self.assertEqual(result.route, "fireworks")
        self.assertEqual(result.remote_mode, "remote_format_strict")
        self.assertEqual(result.prompt_policy, "answer_only")
        self.assertTrue(captured["payload"]["messages"][1]["content"].startswith("Return only the final answer."))
        self.assertIn("Do not restate the task", captured["payload"]["messages"][1]["content"])
        self.assertIn("output format exactly", captured["payload"]["messages"][0]["content"])
        self.assertIn("Do not restate the task", captured["payload"]["messages"][0]["content"])
        self.assertIn("cross_check", result.metadata["local_proof_layers_failed"])

    def test_sarcasm_sentiment_routes_remote(self):
        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3",
            },
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse()):
            result = answer_task(
                "sarcasm",
                "Classify the sentiment as positive, negative, or neutral: Yeah right, the outage was just perfect.",
            )

        self.assertEqual(result.route, "fireworks")
        self.assertIn("trap_guard", result.metadata["local_proof_layers_failed"])

    def test_nontrivial_code_routes_remote_even_in_aggressive_mode(self):
        config = RuntimeConfig.from_env()
        config = RuntimeConfig(
            input_path=config.input_path,
            output_path=config.output_path,
            router_mode="aggressive",
            local_confidence_threshold=0.82,
            fireworks_timeout_seconds=config.fireworks_timeout_seconds,
            fireworks_max_retries=config.fireworks_max_retries,
            batch_deadline_seconds=config.batch_deadline_seconds,
            deadline_safety_margin_seconds=config.deadline_safety_margin_seconds,
            remote_worker_count=config.remote_worker_count,
            local_proof_budget_ms=config.local_proof_budget_ms,
            local_cross_check_enabled=config.local_cross_check_enabled,
            router_log_path=config.router_log_path,
            fireworks_api_key="secret",
            fireworks_base_url="https://judge-proxy.example/v1",
            allowed_models=("minimax-m3",),
            fireworks_max_tokens=config.fireworks_max_tokens,
        )
        with patch("app.agent.ask_fireworks_structured") as mocked_remote:
            from app.fireworks_client import FireworksResult

            mocked_remote.return_value = FireworksResult(answer="def parse_ints(text):\n    return []", model="minimax-m3")
            result = answer_task(
                "code",
                "Write a Python function parse_ints(text) that returns all integers in the string. Return only code.",
                config=config,
            )

        self.assertEqual(result.route, "fireworks")
        self.assertEqual(result.remote_mode, "remote_code")
        self.assertIn("solver_confidence", result.metadata["local_proof_layers_failed"])

    def test_agent_prefers_code_model_when_allowed(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse("def parse_ints(text):\n    return []")

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3,kimi-k2p7-code",
            },
            clear=True,
        ), patch("urllib.request.urlopen", fake_urlopen):
            result = answer_task(
                "code",
                "Write a Python function parse_ints(text) that returns all integers in the string. Return only code.",
            )

        self.assertEqual(result.route, "fireworks")
        self.assertEqual(result.remote_mode, "remote_code")
        self.assertEqual(result.selected_model, "kimi-k2p7-code")
        self.assertEqual(captured["payload"]["model"], "kimi-k2p7-code")

    def test_remote_code_answer_is_normalized_to_code_only(self):
        from app.fireworks_client import FireworksResult

        with patch("app.agent.ask_fireworks_structured") as mocked_remote:
            mocked_remote.return_value = FireworksResult(
                answer="Here is the code:\n\n```python\ndef parse_ints(text):\n    return []\n```\n",
                model="kimi-k2p7-code",
            )
            result = answer_task(
                "code",
                "Write a Python function parse_ints(text) that returns all integers in the string. Return only code.",
            )

        self.assertEqual(result.route, "fireworks")
        self.assertEqual(result.remote_mode, "remote_code")
        self.assertEqual(result.answer, "def parse_ints(text):\n    return []")

    def test_invalid_remote_code_triggers_validation_escalation(self):
        from app.fireworks_client import FireworksResult

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3,kimi-k2p7-code",
                "ROUTER_MODELS_REMOTE_CODE": "minimax-m3,kimi-k2p7-code",
                "ROUTER_MODELS_REMOTE_ESCALATION": "kimi-k2p7-code,minimax-m3",
            },
            clear=True,
        ), patch("app.agent.ask_fireworks_structured") as mocked_remote:
            mocked_remote.side_effect = [
                FireworksResult(answer="def parse_ints(text):\n    return a +", model="minimax-m3", completion_tokens=3, total_tokens=20),
                FireworksResult(answer="def parse_ints(text):\n    return []", model="kimi-k2p7-code", completion_tokens=6, total_tokens=40),
            ]
            result = answer_task(
                "code",
                "Write a Python function parse_ints(text) that returns all integers in the string. Return only code.",
            )

        self.assertEqual(mocked_remote.call_count, 2)
        self.assertEqual(result.route, "fireworks")
        self.assertEqual(result.answer, "def parse_ints(text):\n    return []")
        self.assertEqual(result.selected_model, "kimi-k2p7-code")
        self.assertEqual(result.total_tokens, 60)
        self.assertEqual(result.retry_count, 1)
        self.assertTrue(result.metadata["remote_escalated_after_validation"])
        self.assertEqual(result.metadata["remote_escalation_model"], "kimi-k2p7-code")
        self.assertFalse(result.metadata["remote_validation_failed"])
        self.assertEqual(mocked_remote.call_args_list[1].kwargs["preferred_models"], ("kimi-k2p7-code",))

    def test_remote_validation_escalation_can_be_disabled(self):
        from app.fireworks_client import FireworksResult

        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3,kimi-k2p7-code",
                "ROUTER_MODELS_REMOTE_CODE": "minimax-m3,kimi-k2p7-code",
                "REMOTE_VALIDATION_ESCALATION_ENABLED": "false",
            },
            clear=True,
        ), patch("app.agent.ask_fireworks_structured") as mocked_remote:
            mocked_remote.return_value = FireworksResult(
                answer="def parse_ints(text):\n    return a +",
                model="minimax-m3",
                total_tokens=20,
            )
            result = answer_task(
                "code",
                "Write a Python function parse_ints(text) that returns all integers in the string. Return only code.",
            )

        mocked_remote.assert_called_once()
        self.assertFalse(result.metadata["remote_validation_escalation_enabled"])
        self.assertFalse(result.metadata["remote_escalated_after_validation"])
        self.assertIn("answer_shape", result.metadata["remote_validation_failed"])
        self.assertTrue(result.route_reason.startswith("remote_validation_failed:"))

    def test_certified_code_templates_use_local_proof(self):
        prompts = {
            "clamp": "Write a Python function clamp(x, low, high) that returns low if x is below low, high if x is above high, otherwise x. Return only code.",
            "factorial": "Write a Python function factorial(n) that multiplies numbers from 1 through n using a loop. Return only code.",
            "normalize_name": "Write a Python function normalize_name(name) that strips surrounding whitespace and converts the result to title case. Return only code.",
            "safe_divide": "Write Python code only: define safe_divide(a, b) returning None when b is zero, otherwise a / b. Do not import anything.",
            "max_of_three": "Write a Python function named max_of_three(a, b, c) that returns the largest value. Return only code.",
            "reverse_string": "Write a Python function named reverse_string(s) that returns the string reversed. Return only code.",
            "dedupe_preserve_order": "Write a Python function named dedupe_preserve_order(items) that removes duplicates while preserving order. Return only code.",
            "merge_sorted": "Write a Python function merge_sorted(a, b) that returns a sorted merged list. Return only code.",
            "count_vowels": "Write a Python function named count_vowels(s) that returns the number of vowels in the string. Return only code.",
            "sum_list": "Write a Python function named sum_list(nums) that returns the sum of the numbers. Return only code.",
            "is_palindrome": "Write a Python function named is_palindrome(s) that returns True when the string is a palindrome. Return only code.",
            "square": "Write a Python function square(x) that returns x multiplied by itself. Return only code.",
            "total": "Debug this Python function. Return only corrected code:\n\ndef total(nums):\n    s = 0\n    for n in nums:\n        s = n\n    return s",
            "is_adult": "Return only corrected code:\n\ndef is_adult(age):\n    return age > 18\n\nThe function should return True for age 18 and above.",
            "count_positive": "Return only corrected code:\n\ndef count_positive(nums):\n    count = 0\n    for n in nums:\n        if n > 0:\n            count = 1\n    return count",
        }

        for name, prompt in prompts.items():
            with self.subTest(name=name), patch("app.agent.ask_fireworks_structured") as mocked_remote:
                result = answer_task(name, prompt)

            mocked_remote.assert_not_called()
            self.assertEqual(result.route, "local")
            self.assertIn("proof:exact_code_template", result.metadata["local_evidence"])
            self.assertFalse(result.metadata["local_proof_layers_failed"])

    def test_new_certified_code_templates_return_expected_code(self):
        cases = {
            "max_of_three": (
                "Write a Python function named max_of_three(a, b, c) that returns the largest value. Return only code.",
                "def max_of_three(a, b, c):\n    return max(a, b, c)",
            ),
            "reverse_string": (
                "Write a Python function named reverse_string(s) that returns the string reversed. Return only code.",
                "def reverse_string(s):\n    return s[::-1]",
            ),
            "dedupe_preserve_order": (
                "Write a Python function named dedupe_preserve_order(items) that removes duplicates while preserving order. Return only code.",
                "def dedupe_preserve_order(items):\n    result = []\n    for item in items:\n        if item not in result:\n            result.append(item)\n    return result",
            ),
            "merge_sorted": (
                "Write a Python function merge_sorted(a, b) that returns a sorted merged list. Return only code.",
                "def merge_sorted(a, b):\n    return sorted(a + b)",
            ),
            "count_vowels": (
                "Write a Python function named count_vowels(s) that returns the number of vowels in the string. Return only code.",
                "def count_vowels(s):\n    return sum(1 for ch in s.lower() if ch in 'aeiou')",
            ),
            "sum_list": (
                "Write a Python function named sum_list(nums) that returns the sum of the numbers. Return only code.",
                "def sum_list(nums):\n    return sum(nums)",
            ),
            "is_palindrome": (
                "Write a Python function named is_palindrome(s) that returns True when the string is a palindrome. Return only code.",
                "def is_palindrome(s):\n    return s == s[::-1]",
            ),
            "square": (
                "Write a Python function square(x) that returns x multiplied by itself. Return only code.",
                "def square(x):\n    return x * x",
            ),
        }

        for name, (prompt, expected) in cases.items():
            with self.subTest(name=name), patch("app.agent.ask_fireworks_structured") as mocked_remote:
                result = answer_task(name, prompt)

            mocked_remote.assert_not_called()
            self.assertEqual(result.route, "local")
            self.assertEqual(result.answer, expected)

    def test_arithmetic_expression_uses_certified_local_proof(self):
        cases = {
            "multiply": ("What is 17 * 23? Return only the number.", "391"),
            "parentheses": ("Calculate (12 + 8) / 4. Return only the number.", "5"),
        }

        for name, (prompt, expected) in cases.items():
            with self.subTest(name=name), patch("app.agent.ask_fireworks_structured") as mocked_remote:
                result = answer_task(name, prompt)

            mocked_remote.assert_not_called()
            self.assertEqual(result.route, "local")
            self.assertEqual(result.answer, expected)
            self.assertIn("proof:exact_arithmetic", result.metadata["local_evidence"])
            self.assertFalse(result.metadata["local_proof_layers_failed"])

    def test_multistep_discount_math_uses_certified_local_proof(self):
        with patch("app.agent.ask_fireworks_structured") as mocked_remote:
            result = answer_task(
                "math",
                "A product costs $80 and is discounted by 25%, then taxed at 10%. What is the final price?",
            )

        mocked_remote.assert_not_called()
        self.assertEqual(result.route, "local")
        self.assertEqual(result.answer, "$66")
        self.assertIn("proof:exact_arithmetic", result.metadata["local_evidence"])
        self.assertIn("trap_guard", result.metadata["local_proof_layers_passed"])

    def test_remote_numeric_answer_is_normalized_to_exact_value(self):
        from app.fireworks_client import FireworksResult

        with patch.dict(os.environ, {}, clear=True), patch("app.agent.ask_fireworks_structured") as mocked_remote:
            mocked_remote.return_value = FireworksResult(
                answer="The final price is $66.00 after applying discount and tax.",
                model="minimax-m3",
            )
            result = answer_task(
                "math",
                "A product costs $80 after a bundle discount and local tax. What is the final price? Return only the dollar amount.",
            )

        self.assertEqual(result.route, "fireworks")
        self.assertEqual(result.remote_mode, "remote_accuracy")
        self.assertEqual(result.prompt_policy, "compact")
        self.assertEqual(result.answer, "$66.00")

    def test_remote_sentiment_answer_is_normalized_to_label(self):
        from app.fireworks_client import FireworksResult

        with patch.dict(os.environ, {}, clear=True), patch("app.agent.ask_fireworks_structured") as mocked_remote:
            mocked_remote.return_value = FireworksResult(
                answer="The sentiment is negative because the wording is sarcastic.",
                model="minimax-m3",
            )
            result = answer_task(
                "sentiment",
                "Classify the sentiment as positive, negative, or neutral: Yeah right, the outage was just perfect.",
            )

        self.assertEqual(result.route, "fireworks")
        self.assertEqual(result.remote_mode, "remote_accuracy")
        self.assertEqual(result.prompt_policy, "compact")
        self.assertEqual(result.answer, "negative")

    def test_incomplete_logic_routes_remote_even_if_simple_pattern_matches(self):
        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3",
            },
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse()):
            result = answer_task(
                "logic",
                "Alice is taller than Bob. Bob is taller than Carol. Dave is also in the group. Who is the shortest?",
            )

        self.assertEqual(result.route, "fireworks")
        self.assertIn("trap_guard", result.metadata["local_proof_layers_failed"])

    def test_local_proof_budget_exhaustion_rejects_local_answer(self):
        config = RuntimeConfig.from_env()
        classification = classify_prompt("A product costs $80 and is discounted by 25%. What is the final price?")
        solver_result = LocalSolverResult("$60", 0.99, "test_solver", ("evidence",))
        validation = validate_local_answer(
            prompt="A product costs $80 and is discounted by 25%. What is the final price?",
            classification=classification,
            solver_result=solver_result,
            config=config,
            proof_elapsed_ms=config.local_proof_budget_ms + 1,
        )
        self.assertFalse(validation.accepted)
        self.assertIn("proof_budget", validation.failed_layers)

    def test_ner_cross_check_rejects_missing_entity(self):
        config = RuntimeConfig.from_env()
        prompt = "Extract named entities and label them: Lisa Chen joined AMD in Austin on July 6, 2026."
        classification = classify_prompt(prompt)
        solver_result = LocalSolverResult(
            "Lisa Chen: PERSON; AMD: ORG; July 6, 2026: DATE",
            0.99,
            "test_ner",
            ("evidence",),
        )
        validation = validate_local_answer(
            prompt=prompt,
            classification=classification,
            solver_result=solver_result,
            config=config,
            proof_elapsed_ms=1,
        )
        self.assertFalse(validation.accepted)
        self.assertIn("cross_check", validation.failed_layers)

    def test_code_cross_check_rejects_semantically_wrong_is_even(self):
        config = RuntimeConfig(
            input_path=RuntimeConfig.from_env().input_path,
            output_path=RuntimeConfig.from_env().output_path,
            router_mode="aggressive",
            local_confidence_threshold=0.8,
            fireworks_timeout_seconds=25,
            fireworks_max_retries=0,
            batch_deadline_seconds=600,
            deadline_safety_margin_seconds=60,
            remote_worker_count=1,
            local_proof_budget_ms=100,
            local_cross_check_enabled=True,
            router_log_path=None,
            fireworks_api_key=None,
            fireworks_base_url=None,
            allowed_models=(),
            fireworks_max_tokens=256,
        )
        prompt = "Write a Python function named is_even that returns True if a number is even and False otherwise. Return only code."
        classification = classify_prompt(prompt)
        solver_result = LocalSolverResult(
            "def is_even(n):\n    return n % 2 == 1",
            0.99,
            "test_code",
            ("evidence",),
        )
        validation = validate_local_answer(
            prompt=prompt,
            classification=classification,
            solver_result=solver_result,
            config=config,
            proof_elapsed_ms=1,
        )
        self.assertFalse(validation.accepted)
        self.assertIn("cross_check", validation.failed_layers)

    def test_code_cross_check_rejects_semantically_wrong_sum_list(self):
        config = RuntimeConfig(
            input_path=RuntimeConfig.from_env().input_path,
            output_path=RuntimeConfig.from_env().output_path,
            router_mode="aggressive",
            local_confidence_threshold=0.8,
            fireworks_timeout_seconds=25,
            fireworks_max_retries=0,
            batch_deadline_seconds=600,
            deadline_safety_margin_seconds=60,
            remote_worker_count=1,
            local_proof_budget_ms=100,
            local_cross_check_enabled=True,
            router_log_path=None,
            fireworks_api_key=None,
            fireworks_base_url=None,
            allowed_models=(),
            fireworks_max_tokens=256,
        )
        prompt = "Write a Python function named sum_list(nums) that returns the sum of the numbers. Return only code."
        classification = classify_prompt(prompt)
        solver_result = LocalSolverResult(
            "def sum_list(nums):\n    return len(nums)",
            0.99,
            "test_code",
            ("evidence",),
        )
        validation = validate_local_answer(
            prompt=prompt,
            classification=classification,
            solver_result=solver_result,
            config=config,
            proof_elapsed_ms=1,
        )
        self.assertFalse(validation.accepted)
        self.assertIn("cross_check", validation.failed_layers)

    def test_corrected_code_cross_check_rejects_unfixed_bug(self):
        config = RuntimeConfig(
            input_path=RuntimeConfig.from_env().input_path,
            output_path=RuntimeConfig.from_env().output_path,
            router_mode="aggressive",
            local_confidence_threshold=0.8,
            fireworks_timeout_seconds=25,
            fireworks_max_retries=0,
            batch_deadline_seconds=600,
            deadline_safety_margin_seconds=60,
            remote_worker_count=1,
            local_proof_budget_ms=100,
            local_cross_check_enabled=True,
            router_log_path=None,
            fireworks_api_key=None,
            fireworks_base_url=None,
            allowed_models=(),
            fireworks_max_tokens=256,
        )
        prompt = "Debug this Python code and provide the corrected implementation:\n\ndef add_numbers(a, b):\n    return a - b"
        classification = classify_prompt(prompt)
        solver_result = LocalSolverResult(
            "def add_numbers(a, b):\n    return a - b",
            0.99,
            "test_debug",
            ("evidence",),
        )
        validation = validate_local_answer(
            prompt=prompt,
            classification=classification,
            solver_result=solver_result,
            config=config,
            proof_elapsed_ms=1,
        )
        self.assertFalse(validation.accepted)
        self.assertIn("cross_check", validation.failed_layers)

    def test_deadline_suppressed_remote_still_returns_fallback(self):
        clock = FakeClock()
        deadline = DeadlineManager(total_seconds=10, safety_margin_seconds=3, clock=clock)
        clock.value = 8
        with patch.dict(
            os.environ,
            {
                "FIREWORKS_API_KEY": "secret",
                "FIREWORKS_BASE_URL": "https://judge-proxy.example/v1",
                "ALLOWED_MODELS": "minimax-m3",
                "FIREWORKS_TIMEOUT_SECONDS": "5",
            },
            clear=True,
        ), patch("app.agent.ask_fireworks_structured") as mocked:
            result = answer_task("fresh", "Who is the current CEO of AMD today?", deadline=deadline)

        mocked.assert_not_called()
        self.assertEqual(result.route, "fallback")
        self.assertEqual(result.route_reason, "deadline_suppressed_remote")
        self.assertEqual(result.error, "deadline_suppressed_remote")
        self.assertEqual(result.remote_mode, "remote_accuracy")
        self.assertEqual(result.deadline_decision, "deadline_suppressed_remote_or_retry")

    def test_router_sweep_uses_real_router_for_safe_local_case(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "strict_hybrid")
        scenario = {
            "task_id": "math_discount",
            "category": "mathematical_reasoning",
            "prompt": "A product costs $80 and is discounted by 25%. What is the final price? Return only the final price.",
            "expected_keywords": ["60"],
            "expected_answer": "$60",
            "expected_route": "local",
        }
        row = run_scenario(config, scenario)
        self.assertEqual(row["route"], "local")
        self.assertEqual(row["total_tokens"], 0)
        self.assertTrue(row["expected_route_match"])
        self.assertIn("risk_gate", row["local_proof_layers_passed"])

    def test_router_sweep_uses_real_router_for_certified_arithmetic_case(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "strict_hybrid")
        scenario = {
            "task_id": "math_projection",
            "category": "mathematical_reasoning",
            "prompt": "A service has 120 users and grows by 15% each month for two months. How many users after two months? Round to the nearest whole number.",
            "expected_keywords": ["159"],
            "expected_answer": "159",
            "expected_route": "local",
        }
        row = run_scenario(config, scenario)
        self.assertEqual(row["route"], "local")
        self.assertEqual(row["answer"], "159")
        self.assertEqual(row["total_tokens"], 0)
        self.assertTrue(row["expected_route_match"])
        self.assertIn("risk_gate", row["local_proof_layers_passed"])

    def test_router_sweep_uses_real_router_for_current_fact_remote_case(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "strict_hybrid")
        scenario = {
            "task_id": "factual_current_ceo",
            "category": "factual_knowledge",
            "prompt": "Who is the current CEO of AMD today? Return only the person's name.",
            "expected_keywords": ["Lisa Su"],
            "expected_answer": "Lisa Su",
            "expected_route": "remote_accuracy",
        }
        row = run_scenario(config, scenario)
        self.assertEqual(row["route"], "fireworks")
        self.assertEqual(row["model"], "minimax-m3")
        self.assertGreater(row["total_tokens"], 0)
        self.assertTrue(row["expected_route_match"])

    def test_router_sweep_records_gemma_scorecard_fields(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "gemma_first_router")
        scenario = {
            "task_id": "sentiment_mixed",
            "category": "sentiment_classification",
            "prompt": "Classify the sentiment as positive, negative, or neutral and give a short reason: The setup was easy, but the results were unreliable.",
            "expected_keywords": ["neutral"],
            "expected_answer": "neutral",
            "expected_route": "remote_accuracy",
            "verifier": "label_set",
            "constraints": ["label_plus_reason"],
        }
        row = run_scenario(config, scenario)
        self.assertEqual(row["route"], "fireworks")
        self.assertEqual(row["model"], "gemma-4-31b-it")
        self.assertEqual(row["gemma_decision"], "selected")
        self.assertEqual(row["gemma_candidate_model"], "gemma-4-31b-it")
        self.assertEqual(row["local_inference_usage"], "deterministic_only")
        self.assertIn("prompt_tokens", row)
        self.assertIn("completion_tokens", row)
        self.assertIn("format_failure", row)

    def test_router_sweep_rejects_ambiguous_ner_local_candidate(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "aggressive_local")
        scenario = {
            "task_id": "ner_multiple",
            "category": "named_entity_recognition",
            "prompt": "Extract named entities and label them: Google DeepMind announced Gemma support with AMD in London on July 7, 2026.",
            "expected_keywords": ["Google DeepMind", "ORG", "Gemma", "AMD", "London", "July 7, 2026"],
            "expected_answer": "Google DeepMind: ORG; Gemma: PRODUCT; AMD: ORG; London: LOCATION; July 7, 2026: DATE",
            "expected_route": "remote_format_strict",
        }
        row = run_scenario(config, scenario)
        self.assertEqual(row["route"], "fireworks")
        self.assertTrue(row["expected_route_match"])
        self.assertIn("trap_guard", row["local_proof_layers_failed"])

    def test_router_sweep_rejects_exact_summary_without_runtime_template_evidence(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "aggressive_local")
        scenario = {
            "task_id": "summary_router",
            "category": "text_summarisation",
            "prompt": "Summarise in exactly 12 words: Unfamiliar deployment notes describe retries, queues, dashboards, incidents, and rollback timing.",
            "expected_keywords": ["local", "Fireworks", "accuracy", "token"],
            "expected_answer": "Hybrid routing saves tokens by using local answers and Fireworks fallbacks.",
            "expected_route": "remote_format_strict",
            "verifier": "word_count",
        }
        row = run_scenario(config, scenario)
        self.assertEqual(row["route"], "fireworks")
        self.assertTrue(row["expected_route_match"])
        self.assertIn("cross_check", row["local_proof_layers_failed"])

    def test_router_sweep_accepts_certified_stable_rocm_fact_locally(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "strict_hybrid")
        scenario = {
            "task_id": "factual_rocm",
            "category": "factual_knowledge",
            "prompt": "What is ROCm and why is it relevant for AI workloads on AMD GPUs? Answer in two sentences.",
            "expected_keywords": ["ROCm", "AMD", "GPU", "AI"],
            "expected_answer": "ROCm is AMD's open-source software platform for GPU computing. It matters for AI because it enables frameworks and inference/training workloads to run on AMD GPUs.",
            "expected_route": "local_or_remote_concise",
        }

        row = run_scenario(config, scenario)

        self.assertEqual(row["route"], "local")
        self.assertEqual(row["total_tokens"], 0)
        self.assertIn("ROCm", row["answer"])
        self.assertIn("proof:stable_factual_template", row["local_evidence"])

    def test_router_sweep_accepts_certified_simple_summary_locally(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "strict_hybrid")
        scenario = {
            "task_id": "summary_cloud",
            "category": "text_summarisation",
            "prompt": "Summarise the following text in one sentence: AMD Developer Cloud gives developers access to AMD GPUs for AI workloads. It supports ROCm, PyTorch, and vLLM environments for building and testing AI applications.",
            "expected_keywords": ["AMD Developer Cloud", "AMD GPUs", "AI"],
            "expected_answer": "AMD Developer Cloud provides AMD GPU access and software environments for building and testing AI workloads.",
            "expected_route": "local_or_remote_concise",
            "verifier": "summary_constraints",
        }

        row = run_scenario(config, scenario)

        self.assertEqual(row["route"], "local")
        self.assertEqual(row["total_tokens"], 0)
        self.assertIn("AMD Developer Cloud", row["answer"])
        self.assertIn("proof:stable_summary_template", row["local_evidence"])

    def test_strict_hybrid_expected_routes_match_full_fixture(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "strict_hybrid")
        mismatches = []
        for scenario in load_scenarios(DEFAULT_SCENARIOS):
            row = run_scenario(config, scenario)
            if not row["expected_route_match"]:
                mismatches.append((row["task_id"], row["expected_route"], row["route"], row["route_reason"]))

        self.assertEqual(mismatches, [])

    def test_router_sweep_summary_includes_scorecard_metrics(self):
        scenarios = load_scenarios(DEFAULT_SCENARIOS)[:6]
        configs = [
            next(item for item in DEFAULT_CONFIGS if item["name"] == "strict_hybrid"),
            next(item for item in DEFAULT_CONFIGS if item["name"] == "gemma_first_router"),
        ]
        rows = [run_scenario(config, scenario) for config in configs for scenario in scenarios]
        by_config, _by_category, _ranked, _eligible, _winner = summarize(rows, 0.80)

        strict = by_config["strict_hybrid"]
        gemma = by_config["gemma_first_router"]
        for bucket in (strict, gemma):
            self.assertIn("prompt_tokens", bucket)
            self.assertIn("completion_tokens", bucket)
            self.assertIn("format_failure", bucket)
            self.assertIn("fallback", bucket)
        self.assertGreaterEqual(gemma["gemma_selected"], 1)
        self.assertGreaterEqual(strict["gemma_skipped"], 1)

    def test_router_sweep_includes_planned_phase4_config_variants(self):
        names = {config["name"] for config in DEFAULT_CONFIGS}
        self.assertTrue(
            {
                "always_cheapest_fireworks",
                "always_strongest_fireworks",
                "always_default_fireworks",
                "strict_hybrid_kimi_prompt_evidence",
                "gemma_first_router",
                "cost_router",
                "cost_router_with_compact_prompts",
                "cost_router_with_validation_escalation",
                "gemma_first_router_with_validation_escalation",
            }.issubset(names)
        )

    def test_router_sweep_validation_escalation_records_extra_remote_cost(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "gemma_first_router_with_validation_escalation")
        scenario = {
            "task_id": "codegen_parse_ints",
            "category": "code_generation",
            "difficulty": "medium",
            "scenario_class": "adversarial",
            "prompt": "Write a Python function parse_ints(text) that returns all integers in the string. Return only code.",
            "expected_keywords": ["def parse_ints", "return"],
            "expected_answer": "def parse_ints(text):\n    return []",
            "expected_route": "remote_code",
            "constraints": ["code_only"],
            "verifier": "python_syntax",
        }

        row = run_scenario(config, scenario)

        self.assertTrue(row["passed"])
        self.assertEqual(row["model"], "kimi-k2p7-code")
        self.assertTrue(row["validation_escalation_enabled"])
        self.assertTrue(row["escalated_after_validation"])
        self.assertEqual(row["escalation_model"], "kimi-k2p7-code")
        self.assertEqual(row["prompt_tokens"], estimate_tokens(prompt_for_policy(scenario, config["prompt_policy"])) * 2)

    def test_router_sweep_supports_category_prompt_policy_overrides(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "strict_hybrid_kimi_prompt_evidence")
        scenario = {
            "task_id": "codegen_parse_ints",
            "category": "code_generation",
            "difficulty": "medium",
            "scenario_class": "adversarial",
            "prompt": "Write a Python function parse_ints(text) that returns all integers in the string. Return only code.",
            "expected_keywords": ["def parse_ints", "return"],
            "expected_answer": "def parse_ints(text):\n    return []",
            "expected_route": "remote_code",
            "constraints": ["code_only"],
            "verifier": "python_syntax",
        }

        row = run_scenario(config, scenario)

        self.assertEqual(row["route"], "fireworks")
        self.assertEqual(row["model"], "kimi-k2p7-code")
        self.assertEqual(row["prompt_policy"], "compact")
        self.assertEqual(row["prompt_tokens"], estimate_tokens(prompt_for_policy(scenario, "compact")))

    def test_router_sweep_supports_category_model_preferences(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "strict_hybrid_kimi_prompt_evidence")
        scenario = {
            "task_id": "sentiment_mixed",
            "category": "sentiment_classification",
            "difficulty": "medium",
            "scenario_class": "adversarial",
            "prompt": "Classify the sentiment as positive, negative, or neutral: The setup was easy, but the results were unreliable.",
            "expected_keywords": ["neutral"],
            "expected_answer": "neutral",
            "expected_route": "remote_accuracy",
            "verifier": "label_set",
        }

        row = run_scenario(config, scenario)

        self.assertEqual(row["route"], "fireworks")
        self.assertEqual(row["model"], "kimi-k2p7-code")
        self.assertEqual(row["model_preferences"], ["kimi-k2p7-code", "minimax-m3"])

    def test_runtime_env_recommender_exports_category_model_preferences(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "strict_hybrid_kimi_prompt_evidence")
        exports = dict(exports_for_config(config))

        self.assertIn("ROUTER_MODELS_BY_CATEGORY", exports)
        self.assertIn("code_generation=kimi-k2p7-code,minimax-m3", exports["ROUTER_MODELS_BY_CATEGORY"])
        self.assertIn("mathematical_reasoning=kimi-k2p7-code,minimax-m3", exports["ROUTER_MODELS_BY_CATEGORY"])

    def test_model_matrix_recommender_promotes_only_eligible_category_picks(self):
        rows = []
        for run_id in ("run_a", "run_b"):
            rows.extend(
                [
                    {
                        "run_id": run_id,
                        "category": "factual_knowledge",
                        "model": "kimi-k2p7-code",
                        "prompt_policy": "original",
                        "passed": True,
                        "score": 1.0,
                        "total_tokens": 260,
                    },
                    {
                        "run_id": run_id,
                        "category": "code_generation",
                        "model": "kimi-k2p7-code",
                        "prompt_policy": "compact",
                        "passed": False,
                        "score": 0.5,
                        "total_tokens": 330,
                    },
                ]
            )

        recommendations = choose_by_category(
            rows,
            min_pass_rate=0.80,
            min_avg_score=0.80,
            min_runs=2,
            fallback_model="minimax-m3",
            fallback_policy="original",
        )

        self.assertTrue(recommendations["factual_knowledge"]["eligible"])
        self.assertEqual(recommendations["factual_knowledge"]["model"], "kimi-k2p7-code")
        self.assertFalse(recommendations["code_generation"]["eligible"])
        self.assertEqual(recommendations["code_generation"]["model"], "minimax-m3")
        self.assertIn("pass_rate<0.80", recommendations["code_generation"]["eligibility_failures"])
        self.assertIn("avg_score<0.80", recommendations["code_generation"]["eligibility_failures"])

    def test_model_matrix_recommender_exports_runtime_env(self):
        recommendations = {
            "factual_knowledge": {
                "model": "kimi-k2p7-code",
                "prompt_policy": "original",
                "eligible": True,
            },
            "mathematical_reasoning": {
                "model": "kimi-k2p7-code",
                "prompt_policy": "answer_only",
                "eligible": True,
            },
        }

        exports = dict(exports_for_recommendations(
            recommendations,
            fallback_model="minimax-m3",
            fallback_policy="original",
            max_tokens=192,
        ))

        self.assertEqual(exports["ROUTER_MODE"], "conservative")
        self.assertEqual(exports["FIREWORKS_MAX_TOKENS"], "192")
        self.assertIn("factual_knowledge=kimi-k2p7-code,minimax-m3", exports["ROUTER_MODELS_BY_CATEGORY"])
        self.assertIn("mathematical_reasoning=kimi-k2p7-code,minimax-m3", exports["ROUTER_MODELS_BY_CATEGORY"])
        self.assertEqual(exports["ROUTER_PROMPT_POLICY_BY_CATEGORY"], "mathematical_reasoning=answer_only")

    def test_model_matrix_recommender_marks_missing_categories_as_insufficient(self):
        recommendations = {
            "factual_knowledge": {
                "model": "kimi-k2p7-code",
                "prompt_policy": "original",
                "eligible": True,
            },
        }

        status = evidence_status(
            recommendations,
            required_categories=("factual_knowledge", "code_generation"),
        )

        self.assertEqual(status["status"], "needs_more_evidence")
        self.assertEqual(status["missing_categories"], ["code_generation"])

    def test_model_matrix_recommender_marks_full_eligible_coverage_passed(self):
        recommendations = {
            "factual_knowledge": {
                "model": "kimi-k2p7-code",
                "prompt_policy": "original",
                "eligible": True,
            },
            "code_generation": {
                "model": "kimi-k2p7-code",
                "prompt_policy": "compact",
                "eligible": True,
            },
        }

        status = evidence_status(
            recommendations,
            required_categories=("factual_knowledge", "code_generation"),
        )

        self.assertEqual(status["status"], "passed")
        self.assertEqual(status["missing_categories"], [])
        self.assertEqual(status["ineligible_categories"], [])

    def test_runtime_recommendation_validation_rejects_insufficient_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recommendation = Path(tmpdir) / "recommendation.json"
            recommendation.write_text(
                json.dumps({
                    "evidence_status": "needs_more_evidence",
                    "exports": {
                        "ROUTER_MODE": "conservative",
                    },
                }) + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_recommendation(recommendation)

    def test_model_matrix_recommender_cli_writes_artifacts(self):
        rows = [
            {
                "run_id": "run_a",
                "category": "named_entity_recognition",
                "model": "kimi-k2p7-code",
                "prompt_policy": "original",
                "passed": True,
                "score": 1.0,
                "total_tokens": 300,
            },
            {
                "run_id": "run_b",
                "category": "named_entity_recognition",
                "model": "kimi-k2p7-code",
                "prompt_policy": "original",
                "passed": True,
                "score": 1.0,
                "total_tokens": 320,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            report = tmp / "model_matrix.jsonl"
            report.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            out_json = tmp / "recommendation.json"
            out_md = tmp / "recommendation.md"

            with redirect_stdout(StringIO()):
                status = recommend_from_model_matrix_main([
                    str(report),
                    "--out-json",
                    str(out_json),
                    "--out-md",
                    str(out_md),
                    "--min-runs",
                    "2",
                    "--required-categories",
                    "named_entity_recognition",
                ])

            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(status, 0)
            self.assertTrue(out_md.exists())
            self.assertEqual(payload["evidence_status"], "passed")
            self.assertEqual(payload["recommendations"]["named_entity_recognition"]["model"], "kimi-k2p7-code")
            self.assertIn("ROUTER_MODELS_BY_CATEGORY", payload["exports"])

    def test_expected_route_script_rows_match_full_fixture(self):
        scenarios = load_scenarios(DEFAULT_SCENARIOS)
        rows = check_routes(config_by_name("strict_hybrid"), scenarios)
        self.assertEqual(len(rows), len(scenarios))
        self.assertTrue(all(row["expected_route_match"] for row in rows))
        self.assertTrue(all(row["remote_mode_match"] for row in rows))
        self.assertTrue(
            {
                "task_id",
                "expected_route",
                "actual_route",
                "route_reason",
                "remote_mode",
                "remote_mode_match",
                "prompt_policy",
            }.issubset(rows[0])
        )

    def test_expected_route_script_rows_match_tier_fixtures(self):
        for path in (
            DEFAULT_SCENARIOS.with_name("golden_tier_2_regression.jsonl"),
            DEFAULT_SCENARIOS.with_name("golden_tier_3_adversarial.jsonl"),
        ):
            with self.subTest(path=path.name):
                rows = check_routes(config_by_name("strict_hybrid"), load_scenarios(path))
                self.assertEqual(len(rows), 8)
                self.assertTrue(all(row["expected_route_match"] for row in rows))
                self.assertTrue(all(row["remote_mode_match"] for row in rows))

    def test_router_sweep_ranking_prioritizes_accuracy_then_tokens(self):
        rows = [
            {"config": "high_accuracy", "category": "x", "passed": True, "score": 1.0, "total_tokens": 100, "route": "fireworks", "expected_route_match": True},
            {"config": "low_tokens_bad_accuracy", "category": "x", "passed": False, "score": 0.0, "total_tokens": 0, "route": "local", "expected_route_match": True},
            {"config": "same_accuracy_lower_tokens", "category": "x", "passed": True, "score": 1.0, "total_tokens": 50, "route": "fireworks", "expected_route_match": True},
        ]
        _by_config, _by_category, ranked, _eligible, winner = summarize(rows, accuracy_threshold=0.80)
        self.assertEqual(winner, "same_accuracy_lower_tokens")
        self.assertEqual(ranked[0][0], "same_accuracy_lower_tokens")
        self.assertEqual(ranked[-1][0], "low_tokens_bad_accuracy")

    def test_route_match_contract(self):
        self.assertTrue(route_matches_expected("local", "local"))
        self.assertTrue(route_matches_expected("fireworks", "remote_accuracy"))
        self.assertTrue(route_matches_expected("local", "local_or_remote_concise"))
        self.assertFalse(route_matches_expected("fireworks", "local"))

    def test_eval_scoring_respects_label_and_numeric_verifiers(self):
        label_passed, label_score, _label_notes = score_answer(
            "negative",
            {
                "verifier": "label_set",
                "expected_answer": "negative",
                "expected_keywords": ["negative", "slow", "disappointing"],
            },
        )
        numeric_passed, numeric_score, _numeric_notes = score_answer(
            "$60.00",
            {
                "verifier": "numeric_exact",
                "expected_answer": "$60",
                "expected_keywords": ["60"],
            },
        )
        self.assertTrue(label_passed)
        self.assertEqual(label_score, 1.0)
        self.assertTrue(numeric_passed)
        self.assertEqual(numeric_score, 1.0)

    def test_eval_scoring_rejects_reasoning_leakage_for_strict_outputs(self):
        passed, score, notes = score_answer(
            "The user wants me to compute the final price. The answer is $60.",
            {
                "verifier": "numeric_exact",
                "expected_answer": "$60",
                "constraints": ["answer_only", "exact_numeric"],
            },
        )

        self.assertFalse(passed)
        self.assertEqual(score, 0.0)
        self.assertTrue(any(note.startswith("format_leakage=") for note in notes))

    def test_final_only_prompt_policy_forbids_reasoning_leakage(self):
        prompt = prompt_for_policy(
            {"prompt": "Return only the final price for an $80 item after 25% discount."},
            "final_only",
        )

        self.assertIn("Final answer only:", prompt)
        self.assertIn("Forbidden:", prompt)
        self.assertIn("The user wants", prompt)

    def test_model_matrix_limit_scenarios_supports_live_smoke_tests(self):
        scenarios = load_scenarios(DEFAULT_SCENARIOS)
        self.assertEqual(len(limit_scenarios(scenarios, None)), len(scenarios))
        self.assertEqual(len(limit_scenarios(scenarios, 3)), 3)
        self.assertEqual(limit_scenarios(scenarios, 3)[0]["task_id"], scenarios[0]["task_id"])

    def test_model_matrix_category_filter_supports_focused_live_tests(self):
        scenarios = load_scenarios(DEFAULT_SCENARIOS)
        categories = parse_categories("code_generation,text_summarisation")
        filtered = filter_scenarios_by_categories(scenarios, categories)

        self.assertEqual(categories, {"code_generation", "text_summarisation"})
        self.assertTrue(filtered)
        self.assertTrue(all(row["category"] in categories for row in filtered))

    def test_agent_matrix_scores_actual_local_router_path(self):
        scenario = {
            "task_id": "agent_codegen_local",
            "category": "code_generation",
            "constraints": ["code_only"],
            "output_constraints": ["code_only"],
            "verifier": "python_syntax",
            "prompt": "Write a Python function clamp(x, low, high) that returns low if x is below low, high if x is above high, otherwise x. Return only code.",
            "expected_keywords": ["def clamp", "low", "high", "min", "max"],
            "expected_answer": "def clamp(x, low, high):\n    return max(low, min(x, high))",
        }
        config = RuntimeConfig.from_env()
        deadline = DeadlineManager(total_seconds=600, safety_margin_seconds=60)

        row = agent_matrix.run_case(scenario, config, deadline)

        self.assertEqual(row["route"], "local")
        self.assertTrue(row["passed"])
        self.assertEqual(row["total_tokens"], 0)
        self.assertIn("def clamp", row["answer"])

    def test_exact_summary_template_can_pass_local_proof(self):
        prompt = (
            "Summarise in exactly 8 words: Local-first routing can reduce recorded Fireworks token usage "
            "while preserving quality through remote fallbacks."
        )
        with patch("app.agent.ask_fireworks_structured") as mocked:
            result = answer_task("summary_exact", prompt)

        mocked.assert_not_called()
        self.assertEqual(result.route, "local")
        self.assertEqual(len(result.answer.split()), 8)
        self.assertIn("proof:exact_summary_template", result.metadata["local_evidence"])
        self.assertFalse(result.metadata["local_proof_layers_failed"])

    def test_agent_matrix_scores_exact_summary_local_template(self):
        scenario = {
            "task_id": "agent_summary_exact",
            "category": "text_summarisation",
            "constraints": ["exact_word_count", "one_sentence", "no_explanation"],
            "output_constraints": ["exact_word_count", "one_sentence"],
            "verifier": "word_count",
            "prompt": "Summarise in exactly 8 words: Local-first routing can reduce recorded Fireworks token usage while preserving quality through remote fallbacks.",
            "expected_keywords": ["Local", "routing", "tokens", "fallbacks"],
            "expected_answer": "Local routing saves tokens while remote fallbacks preserve quality.",
        }
        config = RuntimeConfig.from_env()
        deadline = DeadlineManager(total_seconds=600, safety_margin_seconds=60)

        row = agent_matrix.run_case(scenario, config, deadline)

        self.assertEqual(row["route"], "local")
        self.assertTrue(row["passed"])
        self.assertEqual(row["total_tokens"], 0)

    def test_agent_matrix_dev_mapping_keeps_runtime_model_alias(self):
        calls = []

        def fake_original(prompt, config=None, deadline=None, preferred_models=None, system_prompt=None):
            calls.append((config.allowed_models, preferred_models))
            from app.fireworks_client import FireworksResult

            return FireworksResult(answer="ok", model="accounts/fireworks/models/kimi-k2p6")

        env = {
            "FIREWORKS_BASE_URL": "https://api." + "fireworks.ai/inference/v1",
            "FIREWORKS_DEV_MODEL_MAP": "kimi-k2p7-code=accounts/fireworks/models/kimi-k2p6",
            "ALLOWED_MODELS": "kimi-k2p7-code",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "eval.agent_matrix.original_ask_fireworks_structured",
            side_effect=fake_original,
        ), agent_matrix.normal_fireworks_dev_model_mapping(True):
            config = RuntimeConfig.from_env()
            result = agent_matrix.agent_module.ask_fireworks_structured(
                "prompt",
                config=config,
                preferred_models=("kimi-k2p7-code",),
            )

        self.assertEqual(calls[0], (("accounts/fireworks/models/kimi-k2p6",), ("accounts/fireworks/models/kimi-k2p6",)))
        self.assertEqual(result.model, "kimi-k2p7-code")


if __name__ == "__main__":
    unittest.main()
