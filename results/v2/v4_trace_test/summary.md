# V2.5 — private v4 condition benchmark

extractor: `gemini-flash-lite-latest` @ `https://generativelanguage.googleapis.com/v1beta/openai` date `2026-11-19` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

15 items (PRIVATE fixture, not published), categories: A=4, B=3, C=4, D=1, E=3

discipline: `trace` (split: test); deterministic post-extraction rules, identical for every arm.

- oracle-located (probe window; NOT a performance upper bound): compact/expanded/v25 locate evidence from the probe; location oracle, not retrieval and not a performance upper bound.
- real retrieval (BM25): query from parameter name/unit only; full-store BM25; no probe, target document or gold condition used.

## Arms (mean +/- std over repeats)

| metric | oracle-located (probe window; NOT a performance upper bound): compact | oracle-located (probe window; NOT a performance upper bound): expanded | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|---|---|
| condition_field_accuracy | 0.152 +/- 0.021 | 0.311 +/- 0.025 | 0.355 +/- 0.022 |
| parameter_value_accuracy | 0.400 +/- 0.000 | 0.467 +/- 0.054 | 0.667 +/- 0.000 |
| parameter_unit_accuracy | 0.467 +/- 0.000 | 0.444 +/- 0.031 | 0.450 +/- 0.024 |
| value_found_rate | 0.400 +/- 0.000 | 0.467 +/- 0.054 | 0.667 +/- 0.000 |
| invented_condition_rate | 0.067 +/- 0.000 | 0.244 +/- 0.031 | 0.050 +/- 0.036 |
| abstention_rate | 0.378 +/- 0.031 | 0.356 +/- 0.031 | 0.333 +/- 0.000 |
| mean_dropped_conditions | 3.556 +/- 0.251 | 2.911 +/- 1.022 | 15.383 +/- 5.840 |
| quote_in_evidence_rate | 0.983 +/- 0.024 | 1.000 +/- 0.000 | 1.000 +/- 0.000 |
| raw_condition_field_accuracy | 0.178 +/- 0.020 | 0.324 +/- 0.023 | 0.372 +/- 0.017 |
| raw_invented_condition_rate | 0.067 +/- 0.000 | 0.244 +/- 0.031 | 0.050 +/- 0.036 |

## Per condition field (mean +/- std over repeats)

| field | oracle-located (probe window; NOT a performance upper bound): compact | oracle-located (probe window; NOT a performance upper bound): expanded | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|---|---|
| chemistry | 0.000 +/- 0.000 | 0.100 +/- 0.082 | 0.183 +/- 0.062 |
| cell | 0.141 +/- 0.042 | 0.207 +/- 0.010 | 0.108 +/- 0.012 |
| format | 0.141 +/- 0.042 | 1.000 +/- 0.000 | 0.958 +/- 0.059 |
| temperature_k | 0.107 +/- 0.005 | 0.448 +/- 0.041 | 0.633 +/- 0.094 |
| soc | 0.393 +/- 0.046 | 0.381 +/- 0.060 | 0.500 +/- 0.000 |
| method | 0.356 +/- 0.031 | 0.656 +/- 0.042 | 0.542 +/- 0.101 |
| protocol | 0.570 +/- 0.021 | 0.581 +/- 0.105 | 0.800 +/- 0.163 |

transport errors excluded from scoring: compact=0, expanded=0, v25=3


Per-repeat summaries:

| metric | oracle-located (probe window; NOT a performance upper bound): compact (0) | oracle-located (probe window; NOT a performance upper bound): compact (1) | oracle-located (probe window; NOT a performance upper bound): compact (2) | oracle-located (probe window; NOT a performance upper bound): expanded (0) | oracle-located (probe window; NOT a performance upper bound): expanded (1) | oracle-located (probe window; NOT a performance upper bound): expanded (2) | oracle-located (probe window; NOT a performance upper bound): v25 (0) | oracle-located (probe window; NOT a performance upper bound): v25 (1) | oracle-located (probe window; NOT a performance upper bound): v25 (2) |
|---|---|---|---|---|---|---|---|---|---|
| condition_field_accuracy | 0.143 | 0.133 | 0.181 | 0.333 | 0.276 | 0.324 | 0.324 | 0.369 | 0.371 |
| parameter_value_accuracy | 0.400 | 0.400 | 0.400 | 0.400 | 0.533 | 0.467 | 0.667 | 0.667 | 0.667 |
| parameter_unit_accuracy | 0.467 | 0.467 | 0.467 | 0.400 | 0.467 | 0.467 | 0.467 | 0.417 | 0.467 |
| value_found_rate | 0.400 | 0.400 | 0.400 | 0.400 | 0.533 | 0.467 | 0.667 | 0.667 | 0.667 |
| invented_condition_rate | 0.067 | 0.067 | 0.067 | 0.267 | 0.267 | 0.200 | 0.067 | 0.083 | 0.000 |
| abstention_rate | 0.400 | 0.400 | 0.333 | 0.333 | 0.400 | 0.333 | 0.333 | 0.333 | 0.333 |
| mean_dropped_conditions | 3.200 | 3.733 | 3.733 | 1.467 | 3.667 | 3.600 | 8.467 | 22.750 | 14.933 |
| quote_in_evidence_rate | 1.000 | 1.000 | 0.950 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| raw_condition_field_accuracy | 0.181 | 0.152 | 0.200 | 0.352 | 0.295 | 0.324 | 0.352 | 0.393 | 0.371 |
| raw_invented_condition_rate | 0.067 | 0.067 | 0.067 | 0.267 | 0.267 | 0.200 | 0.067 | 0.083 | 0.000 |
