# V2.5 — private v4 condition benchmark

extractor: `deterministic (no LLM)` @ `None` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

30 items (PRIVATE fixture, not published), categories: A=9, B=5, C=7, D=3, E=6

| metric | retrieval_r0 |
|---|---|
| condition_field_accuracy | 0.252 |
| parameter_value_accuracy | 0.567 |
| parameter_unit_accuracy | 0.233 |
| value_found_rate | 0.567 |
| invented_condition_rate | 0.000 |
| abstention_rate | 0.000 |
| mean_dropped_conditions | 111.900 |
| quote_in_evidence_rate | 1.000 |
| raw_condition_field_accuracy | 0.252 |
| raw_invented_condition_rate | 0.000 |

Per-field accuracy:

| field | retrieval_r0 |
|---|---|
| chemistry | 0.033 |
| cell | 0.033 |
| format | 0.000 |
| temperature_k | 0.067 |
| soc | 0.633 |
| method | 0.400 |
| protocol | 0.600 |
