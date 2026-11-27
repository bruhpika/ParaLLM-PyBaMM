# V2.5 — private v4 condition benchmark

extractor: `mimo-v2.6-flash` @ `https://token-plan-sgp.xiaomimimo.com/v1` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

15 items (PRIVATE fixture, not published), categories: A=5, B=2, C=3, D=2, E=3

discipline: `trace` (split: dev); prompt: `v28`

| metric | v25_r0 | v25_r1 | v25_r2 |
|---|---|---|---|
| condition_field_accuracy | 0.429 | 0.429 | 0.495 |
| parameter_value_accuracy | 0.467 | 0.400 | 0.467 |
| parameter_unit_accuracy | 0.733 | 0.600 | 0.667 |
| value_found_rate | 0.467 | 0.400 | 0.467 |
| invented_condition_rate | 0.133 | 0.067 | 0.133 |
| abstention_rate | 0.067 | 0.133 | 0.000 |
| mean_dropped_conditions | 5.200 | 4.667 | 5.867 |
| quote_in_evidence_rate | 0.905 | 0.923 | 1.000 |
| raw_condition_field_accuracy | 0.562 | 0.524 | 0.581 |
| raw_invented_condition_rate | 0.333 | 0.200 | 0.467 |

Per-field accuracy:

| field | v25_r0 | v25_r1 | v25_r2 |
|---|---|---|---|
| chemistry | 0.571 | 0.462 | 0.533 |
| cell | 0.214 | 0.231 | 0.267 |
| format | 0.214 | 0.462 | 0.400 |
| temperature_k | 0.571 | 0.538 | 0.533 |
| soc | 0.500 | 0.615 | 0.533 |
| method | 0.429 | 0.615 | 0.467 |
| protocol | 0.714 | 0.538 | 0.733 |
