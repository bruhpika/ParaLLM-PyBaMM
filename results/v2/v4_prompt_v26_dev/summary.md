# V2.5 — private v4 condition benchmark

extractor: `mimo-v2.6-flash` @ `https://token-plan-sgp.xiaomimimo.com/v1` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

15 items (PRIVATE fixture, not published), categories: A=5, B=2, C=3, D=2, E=3

discipline: `trace` (split: dev); prompt: `v26`

| metric | v25_r0 | v25_r1 | v25_r2 |
|---|---|---|---|
| condition_field_accuracy | 0.210 | 0.181 | 0.210 |
| parameter_value_accuracy | 0.600 | 0.467 | 0.400 |
| parameter_unit_accuracy | 0.533 | 0.400 | 0.400 |
| value_found_rate | 0.600 | 0.467 | 0.400 |
| invented_condition_rate | 0.200 | 0.067 | 0.333 |
| abstention_rate | 0.333 | 0.467 | 0.400 |
| mean_dropped_conditions | 20.933 | 19.600 | 8.200 |
| quote_in_evidence_rate | 0.798 | 0.902 | 0.947 |
| raw_condition_field_accuracy | 0.381 | 0.295 | 0.314 |
| raw_invented_condition_rate | 0.333 | 0.200 | 0.600 |

Per-field accuracy:

| field | v25_r0 | v25_r1 | v25_r2 |
|---|---|---|---|
| chemistry | 0.100 | 0.125 | 0.333 |
| cell | 0.100 | 0.000 | 0.111 |
| format | 0.200 | 0.000 | 0.222 |
| temperature_k | 0.400 | 0.500 | 0.444 |
| soc | 0.600 | 0.625 | 0.556 |
| method | 0.400 | 0.500 | 0.444 |
| protocol | 0.400 | 0.625 | 0.333 |
