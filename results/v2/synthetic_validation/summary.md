# V2.4 — synthetic end-to-end validation (multi-seed stability)

**Label:** SYNTHETIC — deliberately mismatched ground truth and synthetic measurements; not experimental validation (scientific rule 8)

## Stability across seeds

- seeds: 20261117, 20261118, 20261119, 20261120, 20261121 (n = 5)
- criterion: prediction (positive improves held-out, negative does not) reproduces on every seed
- **prediction reproduced: 5/5** (all: True)
- all fits converged: True

## Held-out mean voltage RMSE [V] across seeds

| arm | mean | std | min | max |
|---|---:|---:|---:|---:|
| baseline | 0.0044 | 0.0001 | 0.0044 | 0.0046 |
| positive_control | 0.0011 | 0.0001 | 0.0010 | 0.0012 |
| negative_control | 0.0044 | 0.0001 | 0.0044 | 0.0046 |

## Per-seed detail

| seed | baseline | positive | negative | reproduced |
|---|---:|---:|---:|---|
| 20261117 | 0.0046 | 0.0010 | 0.0046 | True |
| 20261118 | 0.0044 | 0.0010 | 0.0044 | True |
| 20261119 | 0.0045 | 0.0012 | 0.0045 | True |
| 20261120 | 0.0044 | 0.0010 | 0.0044 | True |
| 20261121 | 0.0044 | 0.0010 | 0.0044 | True |

- Synthetic recovery validates the workflow under the assumptions of the generating model. It is NOT experimental validation and does not prove identifiability (scientific rules 7 and 8).
