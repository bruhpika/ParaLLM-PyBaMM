# V2.5 — private v4 condition benchmark

extractor: `gemini-flash-lite-latest` @ `https://generativelanguage.googleapis.com/v1beta/openai` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

30 items (PRIVATE fixture, not published), categories: A=9, B=5, C=7, D=3, E=6

## Arms (mean +/- std over repeats)

| metric | compact | expanded | v25 |
|---|---|---|---|
| condition_field_accuracy | 0.144 +/- 0.016 | 0.294 +/- 0.018 | 0.310 +/- 0.022 |
| parameter_value_accuracy | 0.389 +/- 0.016 | 0.389 +/- 0.042 | 0.583 +/- 0.014 |
| parameter_unit_accuracy | 0.433 +/- 0.027 | 0.367 +/- 0.027 | 0.403 +/- 0.024 |
| value_found_rate | 0.389 +/- 0.016 | 0.389 +/- 0.042 | 0.583 +/- 0.014 |
| invented_condition_rate | 0.067 +/- 0.000 | 0.200 +/- 0.000 | 0.058 +/- 0.012 |
| abstention_rate | 0.433 +/- 0.047 | 0.444 +/- 0.016 | 0.417 +/- 0.014 |
| mean_dropped_conditions | 3.656 +/- 0.427 | 3.478 +/- 0.833 | 14.903 +/- 2.541 |
| quote_in_evidence_rate | 0.991 +/- 0.013 | 1.000 +/- 0.000 | 1.000 +/- 0.000 |
| raw_condition_field_accuracy | 0.165 +/- 0.015 | 0.300 +/- 0.018 | 0.320 +/- 0.022 |
| raw_invented_condition_rate | 0.067 +/- 0.000 | 0.200 +/- 0.000 | 0.058 +/- 0.012 |

## Per condition field (mean +/- std over repeats)

| field | compact | expanded | v25 |
|---|---|---|---|
| chemistry | 0.000 +/- 0.000 | 0.178 +/- 0.126 | 0.143 +/- 0.027 |
| cell | 0.196 +/- 0.023 | 0.360 +/- 0.010 | 0.186 +/- 0.021 |
| format | 0.196 +/- 0.023 | 0.980 +/- 0.028 | 0.976 +/- 0.034 |
| temperature_k | 0.059 +/- 0.005 | 0.479 +/- 0.038 | 0.591 +/- 0.040 |
| soc | 0.374 +/- 0.029 | 0.461 +/- 0.037 | 0.515 +/- 0.053 |
| method | 0.352 +/- 0.026 | 0.620 +/- 0.024 | 0.568 +/- 0.164 |
| protocol | 0.607 +/- 0.046 | 0.619 +/- 0.062 | 0.743 +/- 0.082 |

transport errors excluded from scoring: compact=0, expanded=0, v25=6


Per-repeat summaries:

| metric | compact_r0 | compact_r1 | compact_r2 | expanded_r0 | expanded_r1 | expanded_r2 | v25_r0 | v25_r1 | v25_r2 |
|---|---|---|---|---|---|---|---|---|---|
| condition_field_accuracy | 0.129 | 0.138 | 0.167 | 0.314 | 0.271 | 0.295 | 0.286 | 0.339 | 0.305 |
| parameter_value_accuracy | 0.367 | 0.400 | 0.400 | 0.400 | 0.433 | 0.333 | 0.600 | 0.583 | 0.567 |
| parameter_unit_accuracy | 0.400 | 0.467 | 0.433 | 0.367 | 0.400 | 0.333 | 0.433 | 0.375 | 0.400 |
| value_found_rate | 0.367 | 0.400 | 0.400 | 0.400 | 0.433 | 0.333 | 0.600 | 0.583 | 0.567 |
| invented_condition_rate | 0.067 | 0.067 | 0.067 | 0.200 | 0.200 | 0.200 | 0.067 | 0.042 | 0.067 |
| abstention_rate | 0.500 | 0.400 | 0.400 | 0.433 | 0.467 | 0.433 | 0.400 | 0.417 | 0.433 |
| mean_dropped_conditions | 3.067 | 3.833 | 4.067 | 4.067 | 4.067 | 2.300 | 13.967 | 18.375 | 12.367 |
| quote_in_evidence_rate | 1.000 | 1.000 | 0.972 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| raw_condition_field_accuracy | 0.152 | 0.157 | 0.186 | 0.324 | 0.281 | 0.295 | 0.305 | 0.351 | 0.305 |
| raw_invented_condition_rate | 0.067 | 0.067 | 0.067 | 0.200 | 0.200 | 0.200 | 0.067 | 0.042 | 0.067 |
