# V2.5 — private v4 condition benchmark

extractor: `mimo-v2.6-flash` @ `https://token-plan-sgp.xiaomimimo.com/v1` date `2026-11-27` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

15 items (PRIVATE fixture, not published), categories: A=5, B=2, C=3, D=2, E=3

discipline: `association` (split: dev); prompt: `v28`; deterministic post-extraction rules, identical for every arm.

- oracle-located (probe window; NOT a performance upper bound): compact/expanded/v25 locate evidence from the probe; location oracle, not retrieval and not a performance upper bound.
- real retrieval (BM25): query from parameter name/unit only; full-store BM25; no probe, target document or gold condition used.

## Arms (mean +/- std over repeats)

| metric | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|
| condition_field_accuracy | 0.454 +/- 0.035 |
| parameter_value_accuracy | 0.444 +/- 0.031 |
| parameter_unit_accuracy | 0.644 +/- 0.031 |
| value_found_rate | 0.444 +/- 0.031 |
| invented_condition_rate | 0.000 +/- 0.000 |
| abstention_rate | 0.067 +/- 0.054 |
| mean_dropped_conditions | 5.422 +/- 1.064 |
| quote_in_evidence_rate | 0.943 +/- 0.041 |
| raw_condition_field_accuracy | 0.556 +/- 0.024 |
| raw_invented_condition_rate | 0.333 +/- 0.109 |

## Per condition field (mean +/- std over repeats)

| field | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|
| chemistry | 0.522 +/- 0.046 |
| cell | 0.212 +/- 0.046 |
| format | 0.333 +/- 0.084 |
| temperature_k | 0.548 +/- 0.017 |
| soc | 0.596 +/- 0.018 |
| method | 0.548 +/- 0.017 |
| protocol | 0.643 +/- 0.051 |

transport errors excluded from scoring: v25=0


Per-repeat summaries:

| metric | oracle-located (probe window; NOT a performance upper bound): v25 (0) | oracle-located (probe window; NOT a performance upper bound): v25 (1) | oracle-located (probe window; NOT a performance upper bound): v25 (2) |
|---|---|---|---|
| condition_field_accuracy | 0.457 | 0.410 | 0.495 |
| parameter_value_accuracy | 0.467 | 0.400 | 0.467 |
| parameter_unit_accuracy | 0.667 | 0.600 | 0.667 |
| value_found_rate | 0.467 | 0.400 | 0.467 |
| invented_condition_rate | 0.000 | 0.000 | 0.000 |
| abstention_rate | 0.067 | 0.133 | 0.000 |
| mean_dropped_conditions | 5.533 | 4.067 | 6.667 |
| quote_in_evidence_rate | 0.905 | 0.923 | 1.000 |
| raw_condition_field_accuracy | 0.562 | 0.524 | 0.581 |
| raw_invented_condition_rate | 0.333 | 0.200 | 0.467 |

## Association discipline

Fallback rate = share of candidates whose quote could not be located and which therefore fell back to the evidence-wide trace check (lower is better). Rule counts tally unsupported field decisions.

| tag | fallback rate |
|---|---|
| v25_r0 | 0.095 |
| v25_r1 | 0.077 |
| v25_r2 | 0.000 |

rule counts (unsupported field decisions):

- `not_in_local_scope_method`: 64
- `not_in_local_scope_chemistry`: 50
- `not_in_local_scope_format`: 38
- `not_in_local_scope_cell`: 35
- `explicit_abstention`: 23
- `not_in_local_scope_soc`: 22
- `not_in_local_scope_protocol`: 10
- `quote_unavailable_unsupported`: 5
