# V2.5 — private v4 condition benchmark

extractor: `deterministic (no LLM)` @ `None` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

30 items (PRIVATE fixture, not published), categories: A=9, B=5, C=7, D=3, E=6

| metric | compact_r0 |
|---|---|
| condition_field_accuracy | 0.186 |
| parameter_value_accuracy | 0.267 |
| parameter_unit_accuracy | 0.200 |
| value_found_rate | 0.267 |
| invented_condition_rate | 0.133 |
| abstention_rate | 0.333 |
| mean_dropped_conditions | 4.100 |
| quote_in_evidence_rate | 1.000 |
| raw_condition_field_accuracy | 0.186 |
| raw_invented_condition_rate | 0.133 |

Per-field accuracy:

| field | compact_r0 |
|---|---|
| chemistry | 0.000 |
| cell | 0.000 |
| format | 0.000 |
| temperature_k | 0.100 |
| soc | 0.550 |
| method | 0.550 |
| protocol | 0.750 |
