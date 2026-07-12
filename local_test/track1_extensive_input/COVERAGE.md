# Track 1 Extensive Local Fixture Coverage

This fixture mirrors the official submission shape: each task has a `task_id` and `prompt`. Extra metadata is included only for local scoring, coverage checks, and debugging.

## Summary

- Total tasks: 64
- Categories: 8
- Tasks per category: {'code_debugging': 8, 'code_generation': 8, 'factual_knowledge': 8, 'logical_deductive_reasoning': 8, 'mathematical_reasoning': 8, 'named_entity_recognition': 8, 'sentiment_classification': 8, 'text_summarisation': 8}
- Difficulty mix: {'easy': 12, 'hard': 16, 'medium': 36}
- Scenario classes: {'adversarial': 27, 'exact_format': 5, 'remote_candidate': 5, 'safe_local_candidate': 27}
- Answer shapes: {'code': 8, 'corrected_code': 8, 'entity_list': 8, 'label': 15, 'number': 8, 'short_text': 9, 'summary': 8}

## Constraints Covered

- `answer_only`: 20
- `code_only`: 15
- `entity_labels`: 7
- `exact_numeric`: 8
- `exact_word_count`: 4
- `include_corrected_code`: 5
- `label_plus_reason`: 4
- `no_explanation`: 11
- `one_sentence`: 12
- `rounding_required`: 3
- `two_sentences`: 3

## Risk Components Covered

- `ambiguity`: 16
- `code_risk`: 16
- `factual_freshness`: 2
- `format_strictness`: 52
- `local_validator_weakness`: 18
- `reasoning_depth`: 22

## Category Coverage

### code_debugging

Bug diagnosis and corrected implementations for mutable defaults, boolean conditions, division guards, boundary logic, and formatting constraints.

- `debug_add`: easy / safe_local_candidate / corrected_code / constraints: include_corrected_code / risks: code_risk, format_strictness
- `debug_loop`: medium / safe_local_candidate / corrected_code / constraints: code_only, include_corrected_code / risks: code_risk, reasoning_depth
- `debug_total_verbose`: medium / safe_local_candidate / corrected_code / constraints: code_only, include_corrected_code / risks: code_risk, reasoning_depth
- `debug_off_by_one_range`: medium / safe_local_candidate / corrected_code / constraints: code_only, include_corrected_code / risks: code_risk, reasoning_depth, format_strictness
- `debug_mutable_default`: hard / adversarial / corrected_code / constraints: code_only, include_corrected_code / risks: code_risk, reasoning_depth, format_strictness
- `debug_boolean_condition`: medium / safe_local_candidate / corrected_code / constraints: code_only / risks: code_risk, reasoning_depth, format_strictness
- `debug_string_strip`: easy / safe_local_candidate / corrected_code / constraints: code_only / risks: code_risk, format_strictness
- `debug_dict_count`: medium / safe_local_candidate / corrected_code / constraints: code_only / risks: code_risk, reasoning_depth, format_strictness

### code_generation

Small Python functions from specs, list and string utilities, sorting/top-n helpers, merge/format functions, and code-only output.

- `codegen_is_even`: easy / safe_local_candidate / code / constraints: code_only / risks: code_risk, format_strictness
- `codegen_clamp`: medium / safe_local_candidate / code / constraints: code_only / risks: code_risk, reasoning_depth, format_strictness
- `codegen_factorial`: medium / safe_local_candidate / code / constraints: code_only / risks: code_risk, reasoning_depth, format_strictness
- `codegen_merge_sorted`: medium / safe_local_candidate / code / constraints: code_only / risks: code_risk, format_strictness
- `codegen_parse_csv_ints`: medium / remote_candidate / code / constraints: code_only / risks: code_risk, reasoning_depth, format_strictness
- `codegen_top_n`: medium / safe_local_candidate / code / constraints: code_only / risks: code_risk, format_strictness
- `codegen_no_import_slugify`: medium / safe_local_candidate / code / constraints: code_only / risks: code_risk, format_strictness
- `codegen_filter_even`: easy / safe_local_candidate / code / constraints: code_only / risks: code_risk, format_strictness

### factual_knowledge

Concept explanations, definitions, AMD/ROCm facts, Fireworks proxy behavior, local token-use rationale, and freshness-sensitive facts.

- `factual_gpu_cpu`: easy / safe_local_candidate / short_text / constraints: one_sentence / risks: local_validator_weakness
- `factual_rocm`: medium / safe_local_candidate / short_text / constraints: one_sentence / risks: factual_freshness, local_validator_weakness
- `factual_current_ceo`: medium / remote_candidate / short_text / constraints: answer_only / risks: factual_freshness
- `factual_rocm_pytorch_vllm`: medium / safe_local_candidate / short_text / constraints: two_sentences / risks: local_validator_weakness
- `factual_vram_inference`: medium / remote_candidate / short_text / constraints: one_sentence / risks: local_validator_weakness
- `factual_hackathon_proxy`: hard / adversarial / short_text / constraints: two_sentences / risks: format_strictness, local_validator_weakness
- `factual_local_tokens_zero`: medium / safe_local_candidate / short_text / constraints: one_sentence / risks: local_validator_weakness
- `factual_gpu_parallel_limit`: medium / safe_local_candidate / short_text / constraints: two_sentences / risks: local_validator_weakness

### logical_deductive_reasoning

Constraint puzzles, ordering, insufficient-information answers, double negatives, seating/relative-position logic, and exact label outputs.

- `logic_shortest`: easy / safe_local_candidate / label / constraints: answer_only, no_explanation / risks: reasoning_depth, format_strictness
- `logic_order`: medium / adversarial / label / constraints: answer_only, no_explanation / risks: reasoning_depth, ambiguity, format_strictness
- `logic_latency_rank`: medium / adversarial / label / constraints: answer_only, no_explanation / risks: reasoning_depth, format_strictness
- `logic_insufficient_order`: hard / adversarial / short_text / constraints: answer_only / risks: ambiguity, reasoning_depth, format_strictness
- `logic_seating_left`: medium / adversarial / label / constraints: answer_only, no_explanation / risks: reasoning_depth, format_strictness
- `logic_color_exclusion`: medium / adversarial / label / constraints: answer_only / risks: reasoning_depth, format_strictness
- `logic_double_negative`: hard / adversarial / label / constraints: answer_only / risks: ambiguity, reasoning_depth, format_strictness
- `logic_tournament_points`: medium / adversarial / label / constraints: answer_only / risks: reasoning_depth, format_strictness

### mathematical_reasoning

Arithmetic word problems, discounts, tax, budgets, weighted scores, projections, rounding, and exact numeric formatting.

- `math_discount`: easy / safe_local_candidate / number / constraints: answer_only, exact_numeric, no_explanation / risks: format_strictness
- `math_projection`: medium / adversarial / number / constraints: exact_numeric, rounding_required / risks: reasoning_depth, format_strictness
- `math_discount_tax`: medium / adversarial / number / constraints: exact_numeric, rounding_required / risks: reasoning_depth, format_strictness
- `math_average_latency`: easy / safe_local_candidate / number / constraints: answer_only, exact_numeric / risks: format_strictness
- `math_ratio_tokens`: medium / adversarial / number / constraints: answer_only, exact_numeric / risks: reasoning_depth, format_strictness
- `math_batches_retries`: medium / adversarial / number / constraints: answer_only, exact_numeric / risks: reasoning_depth, format_strictness
- `math_weighted_score`: hard / adversarial / number / constraints: answer_only, exact_numeric, rounding_required / risks: reasoning_depth, format_strictness
- `math_budget_remaining`: medium / safe_local_candidate / number / constraints: answer_only, exact_numeric / risks: format_strictness

### named_entity_recognition

Person, organization, location, date extraction, table-style output, multiple entities, and no-entity cases.

- `ner_person_org`: easy / safe_local_candidate / entity_list / constraints: entity_labels / risks: format_strictness
- `ner_multiple`: hard / adversarial / entity_list / constraints: entity_labels / risks: ambiguity, format_strictness
- `ner_gemma_london`: hard / adversarial / entity_list / constraints: entity_labels / risks: ambiguity, format_strictness
- `ner_table_style`: medium / remote_candidate / entity_list / constraints: entity_labels / risks: format_strictness, local_validator_weakness
- `ner_event_model_names`: hard / adversarial / entity_list / constraints: entity_labels / risks: ambiguity, format_strictness
- `ner_ambiguous_jordan`: hard / adversarial / entity_list / constraints: entity_labels / risks: ambiguity, format_strictness
- `ner_no_entities`: medium / adversarial / entity_list / constraints: answer_only / risks: format_strictness, ambiguity
- `ner_multi_org_product`: hard / remote_candidate / entity_list / constraints: entity_labels / risks: format_strictness, ambiguity

### sentiment_classification

Positive, negative, neutral, sarcasm, mixed tradeoffs, negation, and label-only constraints.

- `sentiment_negative`: easy / safe_local_candidate / label / constraints: label_plus_reason / risks: format_strictness
- `sentiment_mixed`: medium / adversarial / label / constraints: label_plus_reason / risks: ambiguity, local_validator_weakness
- `sentiment_sarcasm_outage`: medium / adversarial / label / constraints: answer_only / risks: ambiguity, local_validator_weakness
- `sentiment_delayed_but_helpful`: medium / adversarial / label / constraints: label_plus_reason / risks: ambiguity, format_strictness
- `sentiment_neutral_tradeoff`: medium / adversarial / label / constraints: answer_only / risks: ambiguity, format_strictness
- `sentiment_negative_polite`: medium / adversarial / label / constraints: answer_only / risks: ambiguity, format_strictness
- `sentiment_positive_qualified`: easy / safe_local_candidate / label / constraints: label_plus_reason / risks: format_strictness
- `sentiment_sarcasm_great_crash`: hard / adversarial / label / constraints: answer_only / risks: ambiguity, local_validator_weakness, format_strictness

### text_summarisation

One-sentence summaries, exact word counts, noise removal, forbidden/required terms, and concise domain summaries.

- `summary_cloud`: easy / safe_local_candidate / summary / constraints: one_sentence / risks: local_validator_weakness
- `summary_router`: hard / exact_format / summary / constraints: exact_word_count, one_sentence, no_explanation / risks: format_strictness, local_validator_weakness
- `summary_exact_eight`: hard / exact_format / summary / constraints: exact_word_count, one_sentence, no_explanation / risks: format_strictness, local_validator_weakness
- `summary_json_one_sentence`: medium / exact_format / summary / constraints: one_sentence, no_explanation / risks: format_strictness, local_validator_weakness
- `summary_exact_11_long`: hard / exact_format / summary / constraints: exact_word_count, one_sentence, no_explanation / risks: format_strictness, local_validator_weakness
- `summary_remove_noise`: medium / adversarial / summary / constraints: one_sentence / risks: local_validator_weakness, format_strictness
- `summary_exact_7`: hard / exact_format / summary / constraints: exact_word_count, one_sentence, no_explanation / risks: format_strictness, local_validator_weakness
- `summary_two_constraints`: hard / adversarial / summary / constraints: one_sentence, no_explanation / risks: format_strictness, ambiguity

## Local Run

```bash
INPUT_PATH=local_test/track1_extensive_input/tasks.json OUTPUT_PATH=/tmp/track1_extensive_results.json python3 -m app.main
python3 scripts/validate_submission_io.py /tmp/track1_extensive_results.json
python3 scripts/score_submission_fixture.py local_test/track1_extensive_input/tasks.json /tmp/track1_extensive_results.json
```
