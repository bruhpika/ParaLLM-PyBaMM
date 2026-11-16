# V2.5 — private v4 condition benchmark

extractor: `gemini-flash-lite-latest` @ `https://generativelanguage.googleapis.com/v1beta/openai` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

30 items (PRIVATE fixture, not published), categories: A=9, B=5, C=7, D=3, E=6

## Arms (mean +/- std over repeats)

| metric | compact | expanded | v25 |
|---|---|---|---|
| condition_field_accuracy | 0.111 +/- 0.009 | 0.240 +/- 0.004 | 0.249 +/- 0.022 |
| parameter_value_accuracy | 0.389 +/- 0.016 | 0.389 +/- 0.042 | 0.583 +/- 0.014 |
| parameter_unit_accuracy | 0.433 +/- 0.027 | 0.367 +/- 0.027 | 0.403 +/- 0.024 |
| value_found_rate | 0.389 +/- 0.016 | 0.389 +/- 0.042 | 0.583 +/- 0.014 |
| invented_condition_rate | 0.411 +/- 0.042 | 0.500 +/- 0.027 | 0.439 +/- 0.021 |
| abstention_rate | 0.433 +/- 0.047 | 0.444 +/- 0.016 | 0.417 +/- 0.014 |

## Per condition field (mean +/- std over repeats)

| field | compact | expanded | v25 |
|---|---|---|---|
| chemistry | 0.000 +/- 0.000 | 0.000 +/- 0.000 | 0.000 +/- 0.000 |
| cell | 0.219 +/- 0.041 | 0.360 +/- 0.010 | 0.186 +/- 0.021 |
| format | 0.219 +/- 0.041 | 0.980 +/- 0.028 | 0.976 +/- 0.034 |
| temperature_k | 0.059 +/- 0.005 | 0.479 +/- 0.038 | 0.591 +/- 0.040 |
| soc | 0.374 +/- 0.029 | 0.461 +/- 0.037 | 0.515 +/- 0.053 |
| method | 0.507 +/- 0.037 | 0.661 +/- 0.019 | 0.629 +/- 0.162 |
| protocol | 0.000 +/- 0.000 | 0.080 +/- 0.027 | 0.091 +/- 0.090 |

transport errors excluded from scoring: compact=0, expanded=0, v25=6


Per-repeat summaries:

| metric | compact_r0 | compact_r1 | compact_r2 | expanded_r0 | expanded_r1 | expanded_r2 | v25_r0 | v25_r1 | v25_r2 |
|---|---|---|---|---|---|---|---|---|---|
| condition_field_accuracy | 0.105 | 0.105 | 0.124 | 0.243 | 0.233 | 0.243 | 0.229 | 0.280 | 0.238 |
| parameter_value_accuracy | 0.367 | 0.400 | 0.400 | 0.400 | 0.433 | 0.333 | 0.600 | 0.583 | 0.567 |
| parameter_unit_accuracy | 0.400 | 0.467 | 0.433 | 0.367 | 0.400 | 0.333 | 0.433 | 0.375 | 0.400 |
| value_found_rate | 0.367 | 0.400 | 0.400 | 0.400 | 0.433 | 0.333 | 0.600 | 0.583 | 0.567 |
| invented_condition_rate | 0.367 | 0.400 | 0.467 | 0.533 | 0.467 | 0.500 | 0.467 | 0.417 | 0.433 |
| abstention_rate | 0.500 | 0.400 | 0.400 | 0.433 | 0.467 | 0.433 | 0.400 | 0.417 | 0.433 |
