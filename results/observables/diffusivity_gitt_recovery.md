# Synthetic joint parameter recovery + profile likelihood

**SYNTHETIC JOINT PARAMETER RECOVERY + PROFILE LIKELIHOOD** — synthetic dry-run; no parameter decision changed.

Parameter set `Chen2020` · model `DFN` · seed 20261127 · noise σ = 0.001 V · 60 data points

## Protocol (§2.7)

- start SOC 0.2, current 1 A, 120 s pulse / 180 s rest, 5 pulses

## Joint recovery (3 scale factors free)

| parameter | truth | estimate | predicted SE | z | multi-start spread | recovered |
|---|---:|---:|---:|---:|---:|---|
| `D_e` | 1.3 | 1.477 | 0.2064 | 0.856 | 1.116 | **False** |
| `D_neg` | 0.5 | 0.4398 | 0.1169 | -0.5151 | 1.151 | **False** |
| `j0_neg` | 0.7 | 0.7014 | 0.006223 | 0.2265 | 1.003 | **True** |

Rule: |z| <= 3 against the predicted SE and multi-start estimate spread ratio <= 1.05, for every parameter

Overall recovery: **False**

### Multi-start fits

| start | estimate | χ² | nfev | converged |
|---|---|---:|---:|---|
| [1.0, 1.0, 1.0] | [0.5061, 0.7003, 1.323] | 62.85 | 24 | True |
| [0.2, 1.5, 0.5] | [0.4806, 0.7015, 1.354] | 62.7 | 21 | True |
| [2.0, 0.5, 2.0] | [0.5051, 0.6996, 1.35] | 62.84 | 23 | True |
| [0.5, 2.0, 1.5] | [0.4398, 0.7014, 1.477] | 62.51 | 17 | True |

## Profile likelihood over `D_neg`

| grid | χ² | Δχ² | free estimates |
|---:|---:|---:|---|
| 0.2 | 137 | 74.23 | [0.715, 6.473] |
| 0.3 | 69.97 | 7.216 | [0.705, 2.315] |
| 0.4 | 62.76 | 0 | [0.7028, 1.586] |
| 0.5 | 62.8 | 0.0413 | [0.7002, 1.346] |
| 0.6 | 64.34 | 1.583 | [0.6965, 1.258] |
| 0.75 | 65.93 | 3.168 | [0.6961, 1.105] |
| 0.9 | 67.42 | 4.657 | [0.6946, 1.037] |
| 1.1 | 68.93 | 6.169 | [0.693, 0.983] |
| 1.4 | 70.6 | 7.837 | [0.6912, 0.9355] |
| 1.8 | 72.01 | 9.254 | [0.6893, 0.9027] |
| 2.2 | 73.11 | 10.35 | [0.6874, 0.8907] |

Δχ² threshold (95 %, 1 dof): 3.841. Minimum at 0.4.

Profile is **closed** at the declared threshold: 95 % interval [0.3468, 0.8178] in scale-factor units.

Rule: closed iff the minimum is interior and the cost exceeds the minimum by 3.841 on both sides of the declared grid

## Limitations

- SYNTHETIC ONLY: the fitted data are model-generated with declared noise, not measured.
- Recovery at one declared truth point; it does not explore the parameter space or prove global identifiability.
- Only three parameters are free; function-valued parameters are perturbed by a constant multiplier (their functional form is assumed known).
- GITT pulse overpotential mixes transport with ohmic and kinetic contributions; this is not a pure solid-diffusion estimator.
- The profile likelihood is coarse (declared grid) and local: it bounds the parameter under this protocol and noise only. Crossings are linearly interpolated between grid points, so a convex profile's interval is slightly underestimated; refine the grid before quoting tight bounds.
- No calibration objective, registry record or dossier decision was changed.

Synthetic dry-run of the identification machinery only. A successful recovery does not prove identifiability on real data (rule 7) and is not experimental validation (rule 8). The dossier action for this parameter remains MEASURE; gates 2/3 of docs/D_NEG_ACTION_DECISION.md must be re-run on a real dataset before any decision change (rule 10).
