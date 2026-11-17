# V2.5 — private v4 condition benchmark

extractor: `gemini-flash-lite-latest` @ `https://generativelanguage.googleapis.com/v1beta/openai` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

30 items (PRIVATE fixture, not published), categories: A=9, B=5, C=7, D=3, E=6

| metric | compact_r0 | compact_r1 | compact_r2 | expanded_r0 | expanded_r1 | expanded_r2 | v25_r0 | v25_r1 | v25_r2 |
|---|---|---|---|---|---|---|---|---|---|
| condition_field_accuracy | 0.118 | 0.071 | 0.076 | 0.238 | 0.219 | 0.248 | 0.267 | 0.243 | 0.238 |
| parameter_value_accuracy | 0.529 | 0.278 | 0.367 | 0.400 | 0.433 | 0.467 | 0.467 | 0.567 | 0.500 |
| parameter_unit_accuracy | 0.529 | 0.278 | 0.433 | 0.400 | 0.433 | 0.433 | 0.400 | 0.400 | 0.400 |
| invented_condition_rate | 0.471 | 0.278 | 0.400 | 0.433 | 0.467 | 0.500 | 0.500 | 0.433 | 0.400 |
| abstention_rate | 0.353 | 0.611 | 0.467 | 0.467 | 0.500 | 0.433 | 0.433 | 0.433 | 0.467 |

Per-field accuracy:

| field | compact_r0 | compact_r1 | compact_r2 | expanded_r0 | expanded_r1 | expanded_r2 | v25_r0 | v25_r1 | v25_r2 |
|---|---|---|---|---|---|---|---|---|---|
| chemistry | 0.000 | 0.143 | 0.000 | 0.062 | 0.133 | 0.118 | 0.176 | 0.059 | 0.188 |
| cell | 0.273 | 0.143 | 0.188 | 0.375 | 0.400 | 0.353 | 0.176 | 0.176 | 0.125 |
| format | 0.273 | 0.143 | 0.188 | 0.938 | 1.000 | 0.941 | 1.000 | 1.000 | 1.000 |
| temperature_k | 0.000 | 0.143 | 0.062 | 0.688 | 0.600 | 0.647 | 0.765 | 0.588 | 0.688 |
| soc | 0.364 | 0.429 | 0.312 | 0.375 | 0.267 | 0.353 | 0.471 | 0.471 | 0.375 |
| method | 0.364 | 0.286 | 0.250 | 0.625 | 0.533 | 0.588 | 0.412 | 0.529 | 0.562 |
| protocol | 0.000 | 0.000 | 0.000 | 0.062 | 0.133 | 0.059 | 0.294 | 0.176 | 0.188 |
