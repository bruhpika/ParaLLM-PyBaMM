# V2.5 — private v4 condition benchmark

extractor: `deterministic (no LLM)` @ `None` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

30 items (PRIVATE fixture, not published), categories: A=9, B=5, C=7, D=3, E=6

| metric | offline_bm25_tuned_r0 |
|---|---|
| condition_field_accuracy | 0.257 |
| parameter_value_accuracy | 0.633 |
| parameter_unit_accuracy | 0.233 |
| value_found_rate | 0.633 |
| invented_condition_rate | 0.000 |
| abstention_rate | 0.000 |
| mean_dropped_conditions | 118.800 |
| quote_in_evidence_rate | 1.000 |
| raw_condition_field_accuracy | 0.257 |
| raw_invented_condition_rate | 0.000 |

Per-field accuracy:

| field | offline_bm25_tuned_r0 |
|---|---|
| chemistry | 0.033 |
| cell | 0.033 |
| format | 0.000 |
| temperature_k | 0.067 |
| soc | 0.667 |
| method | 0.400 |
| protocol | 0.600 |
