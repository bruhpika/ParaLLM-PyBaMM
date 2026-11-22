# V2.5 — private v4 condition benchmark

extractor: `gemini-flash-lite-latest` @ `https://generativelanguage.googleapis.com/v1beta/openai` date `2026-11-19` (identical across arms; not comparable with the v0.1/v3 numbers, which used a different model)

15 items (PRIVATE fixture, not published), categories: A=5, B=2, C=3, D=2, E=3

discipline: `trace` (split: dev); deterministic post-extraction rules, identical for every arm.

- oracle-located (probe window; NOT a performance upper bound): compact/expanded/v25 locate evidence from the probe; location oracle, not retrieval and not a performance upper bound.
- real retrieval (BM25): query from parameter name/unit only; full-store BM25; no probe, target document or gold condition used.

## Arms (mean +/- std over repeats)

| metric | oracle-located (probe window; NOT a performance upper bound): compact | oracle-located (probe window; NOT a performance upper bound): expanded | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|---|---|
| condition_field_accuracy | 0.137 +/- 0.016 | 0.276 +/- 0.013 | 0.265 +/- 0.032 |
| parameter_value_accuracy | 0.378 +/- 0.031 | 0.311 +/- 0.083 | 0.500 +/- 0.027 |
| parameter_unit_accuracy | 0.400 +/- 0.054 | 0.289 +/- 0.063 | 0.356 +/- 0.031 |
| value_found_rate | 0.378 +/- 0.031 | 0.311 +/- 0.083 | 0.500 +/- 0.027 |
| invented_condition_rate | 0.067 +/- 0.000 | 0.156 +/- 0.031 | 0.067 +/- 0.054 |
| abstention_rate | 0.489 +/- 0.083 | 0.533 +/- 0.000 | 0.500 +/- 0.027 |
| mean_dropped_conditions | 3.756 +/- 0.612 | 4.044 +/- 2.333 | 14.422 +/- 3.958 |
| quote_in_evidence_rate | 1.000 +/- 0.000 | 1.000 +/- 0.000 | 1.000 +/- 0.000 |
| raw_condition_field_accuracy | 0.152 +/- 0.021 | 0.276 +/- 0.013 | 0.268 +/- 0.030 |
| raw_invented_condition_rate | 0.067 +/- 0.000 | 0.156 +/- 0.031 | 0.067 +/- 0.054 |

## Per condition field (mean +/- std over repeats)

| field | oracle-located (probe window; NOT a performance upper bound): compact | oracle-located (probe window; NOT a performance upper bound): expanded | oracle-located (probe window; NOT a performance upper bound): v25 |
|---|---|---|---|
| chemistry | 0.000 +/- 0.000 | 0.286 +/- 0.202 | 0.089 +/- 0.064 |
| cell | 0.269 +/- 0.047 | 0.571 +/- 0.000 | 0.290 +/- 0.034 |
| format | 0.269 +/- 0.047 | 0.952 +/- 0.067 | 1.000 +/- 0.000 |
| temperature_k | 0.000 +/- 0.000 | 0.524 +/- 0.067 | 0.538 +/- 0.121 |
| soc | 0.347 +/- 0.020 | 0.571 +/- 0.000 | 0.538 +/- 0.121 |
| method | 0.347 +/- 0.020 | 0.571 +/- 0.000 | 0.601 +/- 0.283 |
| protocol | 0.657 +/- 0.080 | 0.667 +/- 0.067 | 0.663 +/- 0.073 |

transport errors excluded from scoring: compact=0, expanded=0, v25=3


Per-repeat summaries:

| metric | oracle-located (probe window; NOT a performance upper bound): compact (0) | oracle-located (probe window; NOT a performance upper bound): compact (1) | oracle-located (probe window; NOT a performance upper bound): compact (2) | oracle-located (probe window; NOT a performance upper bound): expanded (0) | oracle-located (probe window; NOT a performance upper bound): expanded (1) | oracle-located (probe window; NOT a performance upper bound): expanded (2) | oracle-located (probe window; NOT a performance upper bound): v25 (0) | oracle-located (probe window; NOT a performance upper bound): v25 (1) | oracle-located (probe window; NOT a performance upper bound): v25 (2) |
|---|---|---|---|---|---|---|---|---|---|
| condition_field_accuracy | 0.114 | 0.143 | 0.152 | 0.295 | 0.267 | 0.267 | 0.248 | 0.310 | 0.238 |
| parameter_value_accuracy | 0.333 | 0.400 | 0.400 | 0.400 | 0.333 | 0.200 | 0.533 | 0.500 | 0.467 |
| parameter_unit_accuracy | 0.333 | 0.467 | 0.400 | 0.333 | 0.333 | 0.200 | 0.400 | 0.333 | 0.333 |
| value_found_rate | 0.333 | 0.400 | 0.400 | 0.400 | 0.333 | 0.200 | 0.533 | 0.500 | 0.467 |
| invented_condition_rate | 0.067 | 0.067 | 0.067 | 0.133 | 0.133 | 0.200 | 0.067 | 0.000 | 0.133 |
| abstention_rate | 0.600 | 0.400 | 0.467 | 0.533 | 0.533 | 0.533 | 0.467 | 0.500 | 0.533 |
| mean_dropped_conditions | 2.933 | 3.933 | 4.400 | 6.667 | 4.467 | 1.000 | 19.467 | 14.000 | 9.800 |
| quote_in_evidence_rate | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| raw_condition_field_accuracy | 0.124 | 0.162 | 0.171 | 0.295 | 0.267 | 0.267 | 0.257 | 0.310 | 0.238 |
| raw_invented_condition_rate | 0.067 | 0.067 | 0.067 | 0.133 | 0.133 | 0.200 | 0.067 | 0.000 | 0.133 |
