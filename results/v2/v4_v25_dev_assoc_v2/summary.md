# V2.5 — private v4 condition benchmark

extractor: `mimo-v2.6-flash` @ `https://token-plan-sgp.xiaomimimo.com/v1` date `2026-11-26` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

15 items (PRIVATE fixture, not published), categories: A=5, B=2, C=3, D=2, E=3

discipline: `association` (split: dev); prompt: `v25`; deterministic post-extraction rules, identical for every arm.

- oracle-located (probe window; NOT a performance upper bound): compact/expanded/v25 locate evidence from the probe; location oracle, not retrieval and not a performance upper bound.
- real retrieval (BM25): query from parameter name/unit only; full-store BM25; no probe, target document or gold condition used.

## Arms (mean +/- std over repeats)

| metric | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|
| condition_field_accuracy | 0.271 +/- 0.019 |
| parameter_value_accuracy | 0.500 +/- 0.027 |
| parameter_unit_accuracy | 0.356 +/- 0.031 |
| value_found_rate | 0.500 +/- 0.027 |
| invented_condition_rate | 0.000 +/- 0.000 |
| abstention_rate | 0.500 +/- 0.027 |
| mean_dropped_conditions | 5.439 +/- 1.991 |
| quote_in_evidence_rate | 1.000 +/- 0.000 |
| raw_condition_field_accuracy | 0.268 +/- 0.030 |
| raw_invented_condition_rate | 0.067 +/- 0.054 |

## Per condition field (mean +/- std over repeats)

| field | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|
| chemistry | 0.089 +/- 0.064 |
| cell | 0.290 +/- 0.034 |
| format | 1.000 +/- 0.000 |
| temperature_k | 0.538 +/- 0.121 |
| soc | 0.538 +/- 0.121 |
| method | 0.635 +/- 0.143 |
| protocol | 0.710 +/- 0.034 |

transport errors excluded from scoring: v25=3


Per-repeat summaries:

| metric | oracle-located (probe window; NOT a performance upper bound): v25 (0) | oracle-located (probe window; NOT a performance upper bound): v25 (1) | oracle-located (probe window; NOT a performance upper bound): v25 (2) |
|---|---|---|---|
| condition_field_accuracy | 0.257 | 0.298 | 0.257 |
| parameter_value_accuracy | 0.533 | 0.500 | 0.467 |
| parameter_unit_accuracy | 0.400 | 0.333 | 0.333 |
| value_found_rate | 0.533 | 0.500 | 0.467 |
| invented_condition_rate | 0.000 | 0.000 | 0.000 |
| abstention_rate | 0.467 | 0.500 | 0.533 |
| mean_dropped_conditions | 2.667 | 7.250 | 6.400 |
| quote_in_evidence_rate | 1.000 | 1.000 | 1.000 |
| raw_condition_field_accuracy | 0.257 | 0.310 | 0.238 |
| raw_invented_condition_rate | 0.067 | 0.000 | 0.133 |

## Association discipline

Fallback rate = share of candidates whose quote could not be located and which therefore fell back to the evidence-wide trace check (lower is better). Rule counts tally unsupported field decisions.

| tag | fallback rate |
|---|---|
| v25_r0 | 0.000 |
| v25_r1 | 0.000 |
| v25_r2 | 0.000 |

rule counts (unsupported field decisions):

- `not_in_local_scope_method`: 128
- `explicit_abstention`: 42
- `column_label_not_method`: 28
- `not_in_local_scope_soc`: 25
