# V2.5 — private v4 condition benchmark

extractor: `mimo-v2.6-flash` @ `https://token-plan-sgp.xiaomimimo.com/v1` date `2026-11-26` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

15 items (PRIVATE fixture, not published), categories: A=5, B=2, C=3, D=2, E=3

discipline: `entailment` (split: dev); prompt: `v27`; deterministic post-extraction rules, identical for every arm.

- oracle-located (probe window; NOT a performance upper bound): compact/expanded/v25 locate evidence from the probe; location oracle, not retrieval and not a performance upper bound.
- real retrieval (BM25): query from parameter name/unit only; full-store BM25; no probe, target document or gold condition used.

## Arms (mean +/- std over repeats)

| metric | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|
| condition_field_accuracy | 0.441 +/- 0.045 |
| parameter_value_accuracy | 0.489 +/- 0.063 |
| parameter_unit_accuracy | 0.578 +/- 0.063 |
| value_found_rate | 0.489 +/- 0.063 |
| invented_condition_rate | 0.000 +/- 0.000 |
| abstention_rate | 0.111 +/- 0.031 |
| mean_dropped_conditions | 4.356 +/- 0.227 |
| quote_in_evidence_rate | 0.901 +/- 0.037 |
| raw_condition_field_accuracy | 0.492 +/- 0.029 |
| raw_invented_condition_rate | 0.600 +/- 0.054 |

## Per condition field (mean +/- std over repeats)

| field | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|
| chemistry | 0.595 +/- 0.138 |
| cell | 0.200 +/- 0.033 |
| format | 0.397 +/- 0.079 |
| temperature_k | 0.524 +/- 0.046 |
| soc | 0.575 +/- 0.032 |
| method | 0.551 +/- 0.048 |
| protocol | 0.625 +/- 0.013 |

transport errors excluded from scoring: v25=0


Per-repeat summaries:

| metric | oracle-located (probe window; NOT a performance upper bound): v25 (0) | oracle-located (probe window; NOT a performance upper bound): v25 (1) | oracle-located (probe window; NOT a performance upper bound): v25 (2) |
|---|---|---|---|
| condition_field_accuracy | 0.410 | 0.410 | 0.505 |
| parameter_value_accuracy | 0.533 | 0.400 | 0.533 |
| parameter_unit_accuracy | 0.533 | 0.533 | 0.667 |
| value_found_rate | 0.533 | 0.400 | 0.533 |
| invented_condition_rate | 0.000 | 0.000 | 0.000 |
| abstention_rate | 0.133 | 0.133 | 0.067 |
| mean_dropped_conditions | 4.667 | 4.267 | 4.133 |
| quote_in_evidence_rate | 0.949 | 0.897 | 0.857 |
| raw_condition_field_accuracy | 0.476 | 0.467 | 0.533 |
| raw_invented_condition_rate | 0.533 | 0.600 | 0.667 |
