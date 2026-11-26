# V2.5 — private v4 condition benchmark

extractor: `mimo-v2.6-flash` @ `https://token-plan-sgp.xiaomimimo.com/v1` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

30 items (PRIVATE fixture, not published), categories: A=9, B=5, C=7, D=3, E=6

discipline: `trace` (split: all); prompt: `v27`

| metric | v25_r0 | v25_r1 | v25_r2 |
|---|---|---|---|
| condition_field_accuracy | 0.419 | 0.390 | 0.343 |
| parameter_value_accuracy | 0.533 | 0.433 | 0.400 |
| parameter_unit_accuracy | 0.533 | 0.600 | 0.500 |
| value_found_rate | 0.533 | 0.433 | 0.400 |
| invented_condition_rate | 0.267 | 0.400 | 0.433 |
| abstention_rate | 0.200 | 0.133 | 0.167 |
| mean_dropped_conditions | 3.733 | 4.800 | 4.800 |
| quote_in_evidence_rate | 0.847 | 0.968 | 0.920 |
| raw_condition_field_accuracy | 0.467 | 0.481 | 0.433 |
| raw_invented_condition_rate | 0.467 | 0.633 | 0.667 |

Per-field accuracy:

| field | v25_r0 | v25_r1 | v25_r2 |
|---|---|---|---|
| chemistry | 0.583 | 0.500 | 0.360 |
| cell | 0.375 | 0.231 | 0.160 |
| format | 0.417 | 0.346 | 0.360 |
| temperature_k | 0.625 | 0.654 | 0.640 |
| soc | 0.500 | 0.462 | 0.360 |
| method | 0.542 | 0.462 | 0.440 |
| protocol | 0.625 | 0.500 | 0.560 |
