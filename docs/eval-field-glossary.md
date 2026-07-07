# Eval Field Glossary

Purpose: avoid confusion between related scenario and routing fields.

## Scenario Fields

- `category`: the Track 1 task category.
- `difficulty`: local estimate of scenario hardness: `easy`, `medium`, or `hard`.
- `scenario_class`: why the scenario exists, such as `safe_local_candidate`, `remote_candidate`, `adversarial`, or `exact_format`.
- `intent`: the parsed task intent we expect a future router to infer.
- `answer_shape`: the expected output family, such as `number`, `label`, `summary`, `entity_list`, `code`, or `corrected_code`.
- `constraints`: semantic output constraints extracted from the prompt, such as `answer_only`, `no_explanation`, or `code_only`.
- `output_constraints`: legacy/reporting-friendly constraint labels used by current eval reports.
- `risk_components`: risk reasons the router should notice.
- `expected_route`: the expected routing posture for future real-router tests.
- `remote_mode_hint`: the expected Fireworks mode if the task routes remote.
- `verifier`: the local verifier type that should check the answer.
- `retry_policy`: when a future implementation may retry.
- `failure_taxonomy`: failure labels this scenario is intended to expose.

## Runtime Fields

- `route`: what the agent actually chose: local, Fireworks, or fallback.
- `route_reason`: short explanation for that choice.
- `router_mode`: conservative, balanced, or aggressive.
- `remote_mode`: concise, accuracy, format-strict, or code.
- `selected_model`: model chosen from `ALLOWED_MODELS`.
- `prompt_policy`: original, compact, or answer-only.
- `validator_passed`: whether local/remote output passed local checks.
- `retry_count`: number of retries used, capped by config.
- `error`: sanitized error label/message; must not contain secrets.

## Current Limitation

Many scenario fields are currently test metadata. They become behavioral assertions after the runtime router implements classifier, validators, remote modes, and structured decision logging.
