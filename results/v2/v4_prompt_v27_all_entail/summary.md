# V2.5 — private v4 condition benchmark

extractor: `mimo-v2.6-flash` @ `https://token-plan-sgp.xiaomimimo.com/v1` date `2026-11-26` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

30 items (PRIVATE fixture, not published), categories: A=9, B=5, C=7, D=3, E=6

discipline: `entailment` (split: all); prompt: `v27`; deterministic post-extraction rules, identical for every arm.

- oracle-located (probe window; NOT a performance upper bound): compact/expanded/v25 locate evidence from the probe; location oracle, not retrieval and not a performance upper bound.
- real retrieval (BM25): query from parameter name/unit only; full-store BM25; no probe, target document or gold condition used.

## Arms (mean +/- std over repeats)

| metric | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|
| condition_field_accuracy | 0.398 +/- 0.016 |
| parameter_value_accuracy | 0.456 +/- 0.057 |
| parameter_unit_accuracy | 0.544 +/- 0.031 |
| value_found_rate | 0.456 +/- 0.057 |
| invented_condition_rate | 0.067 +/- 0.027 |
| abstention_rate | 0.167 +/- 0.027 |
| mean_dropped_conditions | 4.600 +/- 0.492 |
| quote_in_evidence_rate | 0.912 +/- 0.050 |
| raw_condition_field_accuracy | 0.460 +/- 0.020 |
| raw_invented_condition_rate | 0.589 +/- 0.087 |

## Per condition field (mean +/- std over repeats)

| field | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|
| chemistry | 0.455 +/- 0.094 |
| cell | 0.190 +/- 0.102 |
| format | 0.296 +/- 0.077 |
| temperature_k | 0.640 +/- 0.012 |
| soc | 0.573 +/- 0.040 |
| method | 0.560 +/- 0.014 |
| protocol | 0.639 +/- 0.045 |

transport errors excluded from scoring: v25=0


Per-repeat summaries:

| metric | oracle-located (probe window; NOT a performance upper bound): v25 (0) | oracle-located (probe window; NOT a performance upper bound): v25 (1) | oracle-located (probe window; NOT a performance upper bound): v25 (2) |
|---|---|---|---|
| condition_field_accuracy | 0.414 | 0.405 | 0.376 |
| parameter_value_accuracy | 0.533 | 0.433 | 0.400 |
| parameter_unit_accuracy | 0.500 | 0.567 | 0.567 |
| value_found_rate | 0.533 | 0.433 | 0.400 |
| invented_condition_rate | 0.067 | 0.033 | 0.100 |
| abstention_rate | 0.200 | 0.133 | 0.167 |
| mean_dropped_conditions | 3.967 | 5.167 | 4.667 |
| quote_in_evidence_rate | 0.847 | 0.968 | 0.920 |
| raw_condition_field_accuracy | 0.467 | 0.481 | 0.433 |
| raw_invented_condition_rate | 0.467 | 0.633 | 0.667 |
