# V2.5 — private v4 condition benchmark

extractor: `gemini-flash-lite-latest` @ `https://generativelanguage.googleapis.com/v1beta/openai` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

30 items (PRIVATE fixture, not published), categories: A=9, B=5, C=7, D=3, E=6

| metric | compact_r0 | expanded_r0 | v25_r0 |
|---|---|---|---|
| condition_field_accuracy | 0.105 | 0.243 | 0.229 |
| parameter_value_accuracy | 0.367 | 0.400 | 0.600 |
| parameter_unit_accuracy | 0.400 | 0.367 | 0.433 |
| invented_condition_rate | 0.367 | 0.533 | 0.467 |
| abstention_rate | 0.500 | 0.433 | 0.400 |

Per-field accuracy:

| field | compact_r0 | expanded_r0 | v25_r0 |
|---|---|---|---|
| chemistry | 0.000 | 0.000 | 0.000 |
| cell | 0.267 | 0.353 | 0.167 |
| format | 0.267 | 0.941 | 1.000 |
| temperature_k | 0.067 | 0.529 | 0.556 |
| soc | 0.400 | 0.412 | 0.444 |
| method | 0.467 | 0.647 | 0.500 |
| protocol | 0.000 | 0.118 | 0.000 |
