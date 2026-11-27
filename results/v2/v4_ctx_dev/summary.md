# V2.5 — private v4 condition benchmark

extractor: `mimo-v2.6-flash` @ `https://token-plan-sgp.xiaomimimo.com/v1` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

15 items (PRIVATE fixture, not published), categories: A=5, B=2, C=3, D=2, E=3

discipline: `trace` (split: dev); prompt: `v28`

| metric | v25_r0 | v25_r1 | v25_r2 | v25+ctx_r0 | v25+ctx_r1 | v25+ctx_r2 |
|---|---|---|---|---|---|---|
| condition_field_accuracy | 0.410 | 0.524 | 0.438 | 0.448 | 0.533 | 0.486 |
| parameter_value_accuracy | 0.400 | 0.400 | 0.533 | 0.467 | 0.467 | 0.533 |
| parameter_unit_accuracy | 0.667 | 0.667 | 0.667 | 0.667 | 0.533 | 0.667 |
| value_found_rate | 0.400 | 0.400 | 0.533 | 0.467 | 0.467 | 0.533 |
| invented_condition_rate | 0.067 | 0.067 | 0.200 | 0.467 | 0.067 | 0.267 |
| abstention_rate | 0.067 | 0.000 | 0.067 | 0.000 | 0.067 | 0.067 |
| mean_dropped_conditions | 5.733 | 4.533 | 4.600 | 4.600 | 4.200 | 4.533 |
| quote_in_evidence_rate | 0.976 | 0.833 | 0.905 | 0.889 | 0.738 | 0.905 |
| raw_condition_field_accuracy | 0.543 | 0.552 | 0.514 | 0.543 | 0.600 | 0.590 |
| raw_invented_condition_rate | 0.200 | 0.400 | 0.333 | 0.667 | 0.267 | 0.467 |

Per-field accuracy:

| field | v25_r0 | v25_r1 | v25_r2 | v25+ctx_r0 | v25+ctx_r1 | v25+ctx_r2 |
|---|---|---|---|---|---|---|
| chemistry | 0.357 | 0.600 | 0.500 | 0.400 | 0.571 | 0.429 |
| cell | 0.214 | 0.267 | 0.286 | 0.467 | 0.500 | 0.500 |
| format | 0.357 | 0.600 | 0.429 | 0.533 | 0.643 | 0.643 |
| temperature_k | 0.571 | 0.533 | 0.500 | 0.467 | 0.571 | 0.571 |
| soc | 0.500 | 0.600 | 0.571 | 0.533 | 0.571 | 0.571 |
| method | 0.429 | 0.533 | 0.500 | 0.333 | 0.571 | 0.429 |
| protocol | 0.643 | 0.533 | 0.500 | 0.400 | 0.571 | 0.500 |
