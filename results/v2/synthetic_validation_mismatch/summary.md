# V2.4 — hardened SYNTHETIC validation (mismatch, drawn truths)

**Label:** SYNTHETIC — deliberately mismatched ground truth and synthetic measurements; not experimental validation (scientific rule 8)

## Design (all SYNTHETIC)

- runs: 18 = 3 truths x 2 noise levels x 3 seeds
- generation: casadi-safe solver (rtol=1e-06, atol=1e-08), mesh {'x_n': 12, 'x_s': 12, 'x_p': 12, 'r_n': 10, 'r_p': 10}
- unfitted perturbation: Positive particle diffusivity [m2.s-1] x 1.1; fits use the nominal model

## Held-out mean voltage RMSE [V] (mean / std / min / max)

| arm | mean | std | min | max |
|---|---:|---:|---:|---:|
| baseline | 0.0026 | 0.0004 | 0.0019 | 0.0033 |
| positive_control | 0.0018 | 0.0008 | 0.0009 | 0.0035 |
| negative_control | 0.0026 | 0.0004 | 0.0019 | 0.0033 |

## Controls

- positive beats baseline: 15/18
- negative does not beat baseline: 18/18
- both (prediction reproduced): 15/18
- all fits converged: True

## 95% CI coverage of fitted parameters

- positive: not available — PyBOP 26.10 SciPyMinimize/L-BFGS-B result exposes no covariance or standard errors; no CI was computed
- negative: not available — PyBOP 26.10 SciPyMinimize/L-BFGS-B result exposes no covariance or standard errors; no CI was computed

## Old fixed-truth result (comparison)

- baseline 0.0046 V, positive 0.0010 V, negative 0.0046 V, reproduced True

- SYNTHETIC mismatch validation only: a different generating solver, tolerances and mesh plus an unfitted-parameter perturbation remove the inverse crime. This is NOT experimental validation and does not prove identifiability (scientific rules 7 and 8).
