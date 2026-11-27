# V2.5 — private v4 condition benchmark

extractor: `mimo-v2.6-flash` @ `https://token-plan-sgp.xiaomimimo.com/v1` date `2026-11-27` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

15 items (PRIVATE fixture, not published), categories: A=5, B=2, C=3, D=2, E=3

discipline: `association` (split: dev); prompt: `v28`; deterministic post-extraction rules, identical for every arm.

- oracle-located (probe window; NOT a performance upper bound): compact/expanded/v25/v25+ctx locate evidence from the probe; location oracle, not retrieval and not a performance upper bound.
- real retrieval (BM25): query from parameter name/unit only; full-store BM25; no probe, target document or gold condition used.

## Arms (mean +/- std over repeats)

| metric | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|
| condition_field_accuracy | 0.451 +/- 0.045 |
| parameter_value_accuracy | 0.444 +/- 0.063 |
| parameter_unit_accuracy | 0.644 +/- 0.031 |
| value_found_rate | 0.444 +/- 0.063 |
| invented_condition_rate | 0.067 +/- 0.054 |
| abstention_rate | 0.044 +/- 0.031 |
| mean_dropped_conditions | 5.000 +/- 1.273 |
| quote_in_evidence_rate | 0.905 +/- 0.058 |
| raw_condition_field_accuracy | 0.537 +/- 0.016 |
| raw_invented_condition_rate | 0.311 +/- 0.083 |

## Per condition field (mean +/- std over repeats)

| field | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|
| chemistry | 0.486 +/- 0.100 |
| cell | 0.210 +/- 0.007 |
| format | 0.416 +/- 0.083 |
| temperature_k | 0.535 +/- 0.029 |
| soc | 0.581 +/- 0.013 |
| method | 0.463 +/- 0.049 |
| protocol | 0.605 +/- 0.029 |

transport errors excluded from scoring: v25=0


Per-repeat summaries:

| metric | oracle-located (probe window; NOT a performance upper bound): v25 (0) | oracle-located (probe window; NOT a performance upper bound): v25 (1) | oracle-located (probe window; NOT a performance upper bound): v25 (2) |
|---|---|---|---|
| condition_field_accuracy | 0.419 | 0.514 | 0.419 |
| parameter_value_accuracy | 0.400 | 0.400 | 0.533 |
| parameter_unit_accuracy | 0.667 | 0.600 | 0.667 |
| value_found_rate | 0.400 | 0.400 | 0.533 |
| invented_condition_rate | 0.000 | 0.067 | 0.133 |
| abstention_rate | 0.067 | 0.000 | 0.067 |
| mean_dropped_conditions | 6.800 | 4.133 | 4.067 |
| quote_in_evidence_rate | 0.976 | 0.833 | 0.905 |
| raw_condition_field_accuracy | 0.543 | 0.552 | 0.514 |
| raw_invented_condition_rate | 0.200 | 0.400 | 0.333 |

## Association discipline

Fallback rate = share of candidates whose quote could not be located and which therefore fell back to the evidence-wide trace check (lower is better). Rule counts tally unsupported field decisions.

| tag | fallback rate |
|---|---|
| v25_r0 | 0.024 |
| v25_r1 | 0.167 |
| v25_r2 | 0.095 |

rule counts (unsupported field decisions):

- `not_in_local_scope_method`: 65
- `not_in_local_scope_chemistry`: 50
- `not_in_local_scope_format`: 37
- `not_in_local_scope_cell`: 30
- `explicit_abstention`: 20
- `not_in_local_scope_soc`: 18
- `not_in_local_scope_protocol`: 6
- `quote_unavailable_unsupported`: 6
