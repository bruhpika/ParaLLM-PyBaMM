# V2.5 — private v4 condition benchmark

extractor: `gemini-flash-lite-latest` @ `https://generativelanguage.googleapis.com/v1beta/openai` date `2026-11-19` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

30 items (PRIVATE fixture, not published), categories: A=9, B=5, C=7, D=3, E=6

discipline: `association` (split: all); deterministic post-extraction rules, identical for every arm.

- oracle-located (probe window; NOT a performance upper bound): compact/expanded/v25 locate evidence from the probe; location oracle, not retrieval and not a performance upper bound.
- real retrieval (BM25): query from parameter name/unit only; full-store BM25; no probe, target document or gold condition used.

## Arms (mean +/- std over repeats)

| metric | oracle-located (probe window; NOT a performance upper bound): compact | oracle-located (probe window; NOT a performance upper bound): expanded | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|---|---|
| condition_field_accuracy | 0.152 +/- 0.017 | 0.306 +/- 0.020 | 0.304 +/- 0.016 |
| parameter_value_accuracy | 0.389 +/- 0.016 | 0.389 +/- 0.042 | 0.583 +/- 0.014 |
| parameter_unit_accuracy | 0.433 +/- 0.027 | 0.367 +/- 0.027 | 0.403 +/- 0.024 |
| value_found_rate | 0.389 +/- 0.016 | 0.389 +/- 0.042 | 0.583 +/- 0.014 |
| invented_condition_rate | 0.044 +/- 0.016 | 0.067 +/- 0.027 | 0.022 +/- 0.016 |
| abstention_rate | 0.433 +/- 0.047 | 0.444 +/- 0.016 | 0.417 +/- 0.014 |
| mean_dropped_conditions | 1.500 +/- 0.191 | 7.322 +/- 1.662 | 5.528 +/- 1.347 |
| quote_in_evidence_rate | 0.991 +/- 0.013 | 1.000 +/- 0.000 | 1.000 +/- 0.000 |
| raw_condition_field_accuracy | 0.165 +/- 0.015 | 0.300 +/- 0.018 | 0.320 +/- 0.022 |
| raw_invented_condition_rate | 0.067 +/- 0.000 | 0.200 +/- 0.000 | 0.058 +/- 0.012 |

## Per condition field (mean +/- std over repeats)

| field | oracle-located (probe window; NOT a performance upper bound): compact | oracle-located (probe window; NOT a performance upper bound): expanded | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|---|---|
| chemistry | 0.000 +/- 0.000 | 0.137 +/- 0.121 | 0.143 +/- 0.027 |
| cell | 0.196 +/- 0.023 | 0.360 +/- 0.010 | 0.186 +/- 0.021 |
| format | 0.196 +/- 0.023 | 0.980 +/- 0.028 | 0.976 +/- 0.034 |
| temperature_k | 0.059 +/- 0.005 | 0.479 +/- 0.038 | 0.591 +/- 0.040 |
| soc | 0.374 +/- 0.029 | 0.480 +/- 0.014 | 0.539 +/- 0.081 |
| method | 0.452 +/- 0.047 | 0.781 +/- 0.023 | 0.500 +/- 0.102 |
| protocol | 0.607 +/- 0.046 | 0.638 +/- 0.059 | 0.719 +/- 0.050 |

transport errors excluded from scoring: compact=0, expanded=0, v25=6


Per-repeat summaries:

| metric | oracle-located (probe window; NOT a performance upper bound): compact (0) | oracle-located (probe window; NOT a performance upper bound): compact (1) | oracle-located (probe window; NOT a performance upper bound): compact (2) | oracle-located (probe window; NOT a performance upper bound): expanded (0) | oracle-located (probe window; NOT a performance upper bound): expanded (1) | oracle-located (probe window; NOT a performance upper bound): expanded (2) | oracle-located (probe window; NOT a performance upper bound): v25 (0) | oracle-located (probe window; NOT a performance upper bound): v25 (1) | oracle-located (probe window; NOT a performance upper bound): v25 (2) |
|---|---|---|---|---|---|---|---|---|---|
| condition_field_accuracy | 0.138 | 0.143 | 0.176 | 0.329 | 0.281 | 0.310 | 0.290 | 0.327 | 0.295 |
| parameter_value_accuracy | 0.367 | 0.400 | 0.400 | 0.400 | 0.433 | 0.333 | 0.600 | 0.583 | 0.567 |
| parameter_unit_accuracy | 0.400 | 0.467 | 0.433 | 0.367 | 0.400 | 0.333 | 0.433 | 0.375 | 0.400 |
| value_found_rate | 0.367 | 0.400 | 0.400 | 0.400 | 0.433 | 0.333 | 0.600 | 0.583 | 0.567 |
| invented_condition_rate | 0.033 | 0.067 | 0.033 | 0.033 | 0.100 | 0.067 | 0.033 | 0.000 | 0.033 |
| abstention_rate | 0.500 | 0.400 | 0.400 | 0.433 | 0.467 | 0.433 | 0.400 | 0.417 | 0.433 |
| mean_dropped_conditions | 1.267 | 1.733 | 1.500 | 7.000 | 9.500 | 5.467 | 4.800 | 7.417 | 4.367 |
| quote_in_evidence_rate | 1.000 | 1.000 | 0.972 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| raw_condition_field_accuracy | 0.152 | 0.157 | 0.186 | 0.324 | 0.281 | 0.295 | 0.305 | 0.351 | 0.305 |
| raw_invented_condition_rate | 0.067 | 0.067 | 0.067 | 0.200 | 0.200 | 0.200 | 0.067 | 0.042 | 0.067 |

## Association discipline

Fallback rate = share of candidates whose quote could not be located and which therefore fell back to the evidence-wide trace check (lower is better). Rule counts tally unsupported field decisions.

| tag | fallback rate |
|---|---|
| compact_r0 | 0.000 |
| compact_r1 | 0.000 |
| compact_r2 | 0.028 |
| expanded_r0 | 0.000 |
| expanded_r1 | 0.000 |
| expanded_r2 | 0.000 |
| v25_r0 | 0.000 |
| v25_r1 | 0.000 |
| v25_r2 | 0.000 |

rule counts (unsupported field decisions):

- `not_in_local_scope_method`: 567
- `column_label_not_method`: 378
- `not_in_local_scope_chemistry`: 156
- `not_in_local_scope_soc`: 87
- `not_in_local_scope_protocol`: 51
- `not_in_local_scope_format`: 8
- `not_in_local_scope_cell`: 4
