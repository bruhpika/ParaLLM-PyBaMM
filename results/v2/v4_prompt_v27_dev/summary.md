# V2.5 — private v4 condition benchmark

extractor: `mimo-v2.6-flash` @ `https://token-plan-sgp.xiaomimimo.com/v1` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

15 items (PRIVATE fixture, not published), categories: A=5, B=2, C=3, D=2, E=3

discipline: `trace` (split: dev); prompt: `v27`

| metric | v25_r0 | v25_r1 | v25_r2 |
|---|---|---|---|
| condition_field_accuracy | 0.400 | 0.362 | 0.448 |
| parameter_value_accuracy | 0.533 | 0.400 | 0.533 |
| parameter_unit_accuracy | 0.533 | 0.533 | 0.667 |
| value_found_rate | 0.533 | 0.400 | 0.533 |
| invented_condition_rate | 0.267 | 0.400 | 0.467 |
| abstention_rate | 0.133 | 0.133 | 0.067 |
| mean_dropped_conditions | 4.400 | 5.133 | 4.200 |
| quote_in_evidence_rate | 0.949 | 0.897 | 0.857 |
| raw_condition_field_accuracy | 0.476 | 0.467 | 0.533 |
| raw_invented_condition_rate | 0.533 | 0.600 | 0.667 |

Per-field accuracy:

| field | v25_r0 | v25_r1 | v25_r2 |
|---|---|---|---|
| chemistry | 0.462 | 0.538 | 0.786 |
| cell | 0.308 | 0.154 | 0.214 |
| format | 0.385 | 0.385 | 0.500 |
| temperature_k | 0.462 | 0.538 | 0.571 |
| soc | 0.538 | 0.462 | 0.429 |
| method | 0.538 | 0.462 | 0.429 |
| protocol | 0.538 | 0.385 | 0.429 |
