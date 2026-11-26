# V2.5 — private v4 condition benchmark

extractor: `mimo-v2.6-flash` @ `https://token-plan-sgp.xiaomimimo.com/v1` date `2026-11-26` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

15 items (PRIVATE fixture, not published), categories: A=5, B=2, C=3, D=2, E=3

discipline: `association` (split: dev); prompt: `v26`; deterministic post-extraction rules, identical for every arm.

- oracle-located (probe window; NOT a performance upper bound): compact/expanded/v25 locate evidence from the probe; location oracle, not retrieval and not a performance upper bound.
- real retrieval (BM25): query from parameter name/unit only; full-store BM25; no probe, target document or gold condition used.

## Arms (mean +/- std over repeats)

| metric | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|
| condition_field_accuracy | 0.216 +/- 0.025 |
| parameter_value_accuracy | 0.489 +/- 0.083 |
| parameter_unit_accuracy | 0.444 +/- 0.063 |
| value_found_rate | 0.489 +/- 0.083 |
| invented_condition_rate | 0.067 +/- 0.054 |
| abstention_rate | 0.400 +/- 0.054 |
| mean_dropped_conditions | 22.622 +/- 6.993 |
| quote_in_evidence_rate | 0.882 +/- 0.063 |
| raw_condition_field_accuracy | 0.330 +/- 0.037 |
| raw_invented_condition_rate | 0.378 +/- 0.166 |

## Per condition field (mean +/- std over repeats)

| field | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|
| chemistry | 0.144 +/- 0.140 |
| cell | 0.070 +/- 0.050 |
| format | 0.141 +/- 0.100 |
| temperature_k | 0.448 +/- 0.041 |
| soc | 0.631 +/- 0.027 |
| method | 0.481 +/- 0.026 |
| protocol | 0.602 +/- 0.107 |

transport errors excluded from scoring: v25=0


Per-repeat summaries:

| metric | oracle-located (probe window; NOT a performance upper bound): v25 (0) | oracle-located (probe window; NOT a performance upper bound): v25 (1) | oracle-located (probe window; NOT a performance upper bound): v25 (2) |
|---|---|---|---|
| condition_field_accuracy | 0.229 | 0.181 | 0.238 |
| parameter_value_accuracy | 0.600 | 0.467 | 0.400 |
| parameter_unit_accuracy | 0.533 | 0.400 | 0.400 |
| value_found_rate | 0.600 | 0.467 | 0.400 |
| invented_condition_rate | 0.133 | 0.000 | 0.067 |
| abstention_rate | 0.333 | 0.467 | 0.400 |
| mean_dropped_conditions | 27.467 | 27.667 | 12.733 |
| quote_in_evidence_rate | 0.798 | 0.902 | 0.947 |
| raw_condition_field_accuracy | 0.381 | 0.295 | 0.314 |
| raw_invented_condition_rate | 0.333 | 0.200 | 0.600 |

## Association discipline

Fallback rate = share of candidates whose quote could not be located and which therefore fell back to the evidence-wide trace check (lower is better). Rule counts tally unsupported field decisions.

| tag | fallback rate |
|---|---|
| v25_r0 | 0.202 |
| v25_r1 | 0.098 |
| v25_r2 | 0.053 |

rule counts (unsupported field decisions):

- `not_in_local_scope_format`: 233
- `not_in_local_scope_cell`: 229
- `not_in_local_scope_chemistry`: 211
- `not_in_local_scope_method`: 191
- `quote_unavailable_unsupported`: 78
- `not_in_local_scope_protocol`: 47
- `not_in_local_scope_soc`: 33
