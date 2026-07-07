import json
import os
import unittest
from unittest.mock import patch

from app.agent import answer_task
from app.classifier import classify_prompt
from app.config import RuntimeConfig
from app.deadline import DeadlineManager
from app.solvers.basic import LocalSolverResult
from app.validators import validate_local_answer
from eval.model_matrix import DEFAULT_SCENARIOS, load_scenarios, score_answer
from eval.router_config_sweep import DEFAULT_CONFIGS, route_matches_expected, run_scenario, summarize


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps({
            "choices": [{"message": {"content": "Remote answer"}}],
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

    def test_local_high_confidence_task_does_not_call_fireworks(self):
        with patch("app.agent.ask_fireworks_structured") as mocked:
            result = answer_task("math", "A product costs $80 and is discounted by 25%. What is the final price?")

        mocked.assert_not_called()
        self.assertEqual(result.answer, "$60")
        self.assertEqual(result.route, "local")
        self.assertEqual(result.category, "mathematical_reasoning")
        self.assertIn("risk_gate", result.metadata["local_proof_layers_passed"])
        self.assertFalse(result.metadata["local_proof_layers_failed"])

    def test_classifier_runs_before_remote_call(self):
        seen = []

        def fake_classify(prompt):
            seen.append("classify")
            return classify_prompt(prompt)

        def fake_remote(prompt, config=None, deadline=None):
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
        self.assertEqual(captured["url"], "https://judge-proxy.example/v1/chat/completions")
        self.assertIn("trap_guard", result.metadata["local_proof_layers_failed"])

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
        self.assertIn("trap_guard", result.metadata["local_proof_layers_failed"])

    def test_exact_summary_routes_remote_for_format_control(self):
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
                "summary",
                "Summarise in exactly 12 words: A hybrid router should answer easy tasks locally and send risky tasks to Fireworks.",
            )

        self.assertEqual(result.route, "fireworks")
        self.assertIn("trap_guard", result.metadata["local_proof_layers_failed"])

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

            mocked_remote.return_value = FireworksResult(answer="def clamp(x, low, high):\n    return max(low, min(x, high))", model="minimax-m3")
            result = answer_task(
                "code",
                "Write a Python function clamp(x, low, high) that returns low if x is below low, high if x is above high, otherwise x. Return only code.",
                config=config,
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
        ), patch("urllib.request.urlopen") as mocked:
            result = answer_task("fresh", "Who is the current CEO of AMD today?", deadline=deadline)

        mocked.assert_not_called()
        self.assertEqual(result.route, "fallback")
        self.assertEqual(result.route_reason, "deadline_suppressed_remote")

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

    def test_router_sweep_uses_real_router_for_remote_case(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "strict_hybrid")
        scenario = {
            "task_id": "math_projection",
            "category": "mathematical_reasoning",
            "prompt": "A service has 120 users and grows by 15% each month for two months. How many users after two months? Round to the nearest whole number.",
            "expected_keywords": ["159"],
            "expected_answer": "159",
            "expected_route": "remote_accuracy",
        }
        row = run_scenario(config, scenario)
        self.assertEqual(row["route"], "fireworks")
        self.assertEqual(row["model"], "minimax-m3")
        self.assertGreater(row["total_tokens"], 0)
        self.assertTrue(row["expected_route_match"])

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

    def test_router_sweep_rejects_exact_summary_local_candidate(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "aggressive_local")
        scenario = {
            "task_id": "summary_router",
            "category": "text_summarisation",
            "prompt": "Summarise in exactly 12 words: A hybrid router should answer easy tasks locally and send risky tasks to Fireworks so it can preserve accuracy while reducing recorded token usage.",
            "expected_keywords": ["local", "Fireworks", "accuracy", "token"],
            "expected_answer": "Hybrid routing saves tokens by using local answers and Fireworks fallbacks.",
            "expected_route": "remote_format_strict",
            "verifier": "word_count",
        }
        row = run_scenario(config, scenario)
        self.assertEqual(row["route"], "fireworks")
        self.assertTrue(row["expected_route_match"])
        self.assertIn("trap_guard", row["local_proof_layers_failed"])


    def test_strict_hybrid_expected_routes_match_full_fixture(self):
        config = next(item for item in DEFAULT_CONFIGS if item["name"] == "strict_hybrid")
        mismatches = []
        for scenario in load_scenarios(DEFAULT_SCENARIOS):
            row = run_scenario(config, scenario)
            if not row["expected_route_match"]:
                mismatches.append((row["task_id"], row["expected_route"], row["route"], row["route_reason"]))

        self.assertEqual(mismatches, [])

    def test_router_sweep_ranking_prioritizes_accuracy_then_tokens(self):
        rows = [
            {"config": "high_accuracy", "category": "x", "passed": True, "score": 1.0, "total_tokens": 100, "route": "fireworks", "expected_route_match": True},
            {"config": "low_tokens_bad_accuracy", "category": "x", "passed": False, "score": 0.0, "total_tokens": 0, "route": "local", "expected_route_match": True},
            {"config": "same_accuracy_lower_tokens", "category": "x", "passed": True, "score": 1.0, "total_tokens": 50, "route": "fireworks", "expected_route_match": True},
        ]
        _by_config, _by_category, ranked, _eligible, winner = summarize(rows, accuracy_threshold=0.85)
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


if __name__ == "__main__":
    unittest.main()
