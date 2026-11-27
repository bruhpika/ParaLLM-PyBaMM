# V2.5 — private v4 condition benchmark

extractor: `mimo-v2.6-flash` @ `https://token-plan-sgp.xiaomimimo.com/v1` date `2026-11-27` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

15 items (PRIVATE fixture, not published), categories: A=5, B=2, C=3, D=2, E=3

discipline: `association` (split: dev); prompt: `v28`; deterministic post-extraction rules, identical for every arm.

- oracle-located (probe window; NOT a performance upper bound): compact/expanded/v25/v25+ctx locate evidence from the probe; location oracle, not retrieval and not a performance upper bound.
- real retrieval (BM25): query from parameter name/unit only; full-store BM25; no probe, target document or gold condition used.

## Arms (mean +/- std over repeats)

| metric | oracle-located (probe window; NOT a performance upper bound): v25+ctx |
|---|---|
| condition_field_accuracy | 0.457 +/- 0.016 |
| parameter_value_accuracy | 0.489 +/- 0.031 |
| parameter_unit_accuracy | 0.622 +/- 0.063 |
| value_found_rate | 0.489 +/- 0.031 |
| invented_condition_rate | 0.022 +/- 0.031 |
| abstention_rate | 0.044 +/- 0.031 |
| mean_dropped_conditions | 6.267 +/- 0.435 |
| quote_in_evidence_rate | 0.844 +/- 0.075 |
| raw_condition_field_accuracy | 0.578 +/- 0.025 |
| raw_invented_condition_rate | 0.467 +/- 0.163 |

## Per condition field (mean +/- std over repeats)

| field | oracle-located (probe window; NOT a performance upper bound): v25+ctx |
|---|---|
| chemistry | 0.467 +/- 0.075 |
| cell | 0.256 +/- 0.030 |
| format | 0.325 +/- 0.030 |
| temperature_k | 0.559 +/- 0.018 |
| soc | 0.581 +/- 0.013 |
| method | 0.537 +/- 0.049 |
| protocol | 0.629 +/- 0.020 |

transport errors excluded from scoring: v25+ctx=0


Per-repeat summaries:

| metric | oracle-located (probe window; NOT a performance upper bound): v25+ctx (0) | oracle-located (probe window; NOT a performance upper bound): v25+ctx (1) | oracle-located (probe window; NOT a performance upper bound): v25+ctx (2) |
|---|---|---|---|
| condition_field_accuracy | 0.457 | 0.476 | 0.438 |
| parameter_value_accuracy | 0.467 | 0.467 | 0.533 |
| parameter_unit_accuracy | 0.667 | 0.533 | 0.667 |
| value_found_rate | 0.467 | 0.467 | 0.533 |
| invented_condition_rate | 0.067 | 0.000 | 0.000 |
| abstention_rate | 0.000 | 0.067 | 0.067 |
| mean_dropped_conditions | 6.267 | 5.733 | 6.800 |
| quote_in_evidence_rate | 0.889 | 0.738 | 0.905 |
| raw_condition_field_accuracy | 0.543 | 0.600 | 0.590 |
| raw_invented_condition_rate | 0.667 | 0.267 | 0.467 |

## Association discipline

Fallback rate = share of candidates whose quote could not be located and which therefore fell back to the evidence-wide trace check (lower is better). Rule counts tally unsupported field decisions.

| tag | fallback rate |
|---|---|
| v25+ctx_r0 | 0.111 |
| v25+ctx_r1 | 0.262 |
| v25+ctx_r2 | 0.095 |

rule counts (unsupported field decisions):

- `not_in_local_scope_method`: 65
- `not_in_local_scope_format`: 53
- `not_in_local_scope_cell`: 50
- `not_in_local_scope_chemistry`: 45
- `explicit_abstention`: 38
- `not_in_local_scope_soc`: 16
- `quote_unavailable_unsupported`: 11
- `not_in_local_scope_protocol`: 7
