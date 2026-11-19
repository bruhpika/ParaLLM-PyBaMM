# Offline end-to-end side-by-side: oracle vs BM25 vs tuned BM25

All arms use the deterministic offline extractor; no LLM call was made.

## v3 (P5)

Oracle and BM25 baseline are the committed 37-item aggregates; the tuned
arm is the 22 locally available items after the Chen2020 texts were
untracked. These numbers are **not directly comparable**.

### v3 metrics

| metric | oracle-located (upper bound) | BM25 baseline | BM25 tuned (b=0.5) |
|---|---|---|---|
| parameter_identification_accuracy | 0.500 | 0.846 | 0.806 |
| value_extraction_accuracy | 0.500 | 0.386 | 0.200 |
| provenance_accuracy | 1.000 | 0.773 | 0.680 |
| condition_completeness | 0.000 | 0.000 | 0.000 |
| qualifier_classification_accuracy | 0.115 | 0.614 | 0.640 |
| false_extraction_rate | 0.000 | 0.195 | 0.228 |
| abstention_accuracy | 1.000 | 0.167 | 0.000 |

## v4 (private)

All three arms ran on the same 30 private items with the same offline
extractor and the current 8-document full store. The v4 corpus is small
and private; these numbers are not comparable with v3.

### v4 metrics

| metric | oracle-located (upper bound) | BM25 baseline | BM25 tuned (b=0.5) |
|---|---|---|---|
| parameter_value_accuracy | 0.267 | 0.567 | 0.633 |
| value_found_rate | 0.267 | 0.567 | 0.633 |
| condition_field_accuracy | 0.186 | 0.252 | 0.257 |
| invented_condition_rate | 0.133 | 0.000 | 0.000 |
| abstention_rate | 0.333 | 0.000 | 0.000 |
| quote_in_evidence_rate | 1.000 | 1.000 | 1.000 |
