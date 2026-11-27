# Joint multi-parameter FIM diagnostic

**SYNTHETIC JOINT MULTI-PARAMETER FIM DIAGNOSTIC** — diagnostic only; no parameter decision changed.

Parameter set `Chen2020` · model `DFN` · rel_perturbation 0.02

## Parameters free together

| label | PyBaMM parameter | kind | baseline |
|---|---|---|---:|
| `D_neg` | `Negative particle diffusivity [m2.s-1]` | scalar | 3.3e-14 |
| `j0_neg` | `Negative electrode exchange-current density [A.m-2]` | function-valued | function-valued |
| `D_e` | `Electrolyte diffusivity [m2.s-1]` | function-valued | function-valued |

Observables: `voltage_0.5C`, `voltage_1C`, `voltage_2C`, `gitt_d_rest_voltage`, `gitt_d_pulse_drop`, `gitt_d_relaxation_slope`, `eis_re_impedance`, `eis_neg_im_impedance`

## Marginal information by observable set

Marginal relative SE for `D_neg` with all declared parameters free:

| set | marginal rel. SE | classification | rank | condition number |
|---|---:|---|---:|---:|
| voltage_only | 0.004709 | UNOBSERVABLE | 3/3 | 1500 |
| gitt_only | 0.01419 | OBSERVABLE | 3/3 | 596.6 |
| voltage_plus_gitt | 0.003027 | OBSERVABLE | 3/3 | 627.6 |
| eis_only | 0.274 | UNOBSERVABLE | 3/3 | 5.87e+07 |
| all_configured | 0.002635 | OBSERVABLE | 3/3 | 5667 |

Marginal standard errors are local Cramér–Rao bounds conditional on the declared i.i.d. noise. The OBSERVABLE/UNOBSERVABLE label is the declared conjunction: marginal relative SE <= 0.05 AND at least one contributing observable has mean |S| >= 0.05. The voltage-only set meets the SE limb but not the |S| limb (strongest 0.04757), so it stays UNOBSERVABLE even though its implied SE is small. The flip is therefore a conservative classification flip, not a claim that voltage data are uninformative.

## Marginal standard errors and variance inflation

The single-parameter reference is computed from the same joint Jacobians with only that column active; VIF = (SE_joint / SE_single)^2.

| parameter | joint marginal rel. SE | single-parameter rel. SE | VIF | strongest mean \|S\| | classification |
|---|---:|---:|---:|---:|---|
| `D_neg` | 0.002635 | 0.00236 | 1.246 | 0.1 | OBSERVABLE |
| `j0_neg` | 3.84e-05 | 3.522e-05 | 1.189 | 1.888 | OBSERVABLE |
| `D_e` | 0.0001469 | 0.0001222 | 1.446 | 1.245 | OBSERVABLE |

## Parameter correlation (joint, all configured observables)

| | `D_neg` | `j0_neg` | `D_e` |
|---|---:|---:|---:|
| `D_neg` | 1 | 0.1534 | -0.444 |
| `j0_neg` | 0.1534 | 1 | -0.3976 |
| `D_e` | -0.444 | -0.3976 | 1 |

## Finite-difference step robustness

The joint FIM is re-scored at the declared alternative finite-difference steps. This checks that the classification and correlation structure are not artefacts of one step size.

| rel_perturbation | `D_neg` marginal rel. SE | classification | correlation with `D_neg` (other parameters) | condition number |
|---|---:|---|---:|---:|
| 0.02 (nominal) | 0.002635 | OBSERVABLE | `j0_neg` 0.1534, `D_e` -0.444 | 5667 |
| 0.005 | 0.00264 | OBSERVABLE | `j0_neg` 0.151, `D_e` -0.4377 | 5688 |
| 0.01 | 0.002639 | OBSERVABLE | `j0_neg` 0.1535, `D_e` -0.4434 | 5682 |
| 0.05 | 0.002646 | OBSERVABLE | `j0_neg` 0.1539, `D_e` -0.4471 | 5736 |

Classification stable across steps: **True**; max relative-SE deviation 0.005933; max |correlation| deviation 0.006268.

## Verdict

- `D_neg` joint classification: **OBSERVABLE**
- variance inflation factor: **1.246**
- no free parameter exceeds |rho| = 0.9
- survives the collinearity check: **True**
- D_neg remains marginally observable in the joint 3-parameter fit and no free parameter is correlated above |rho| = 0.9.
- parameter decision: **unchanged**

## Single-parameter cross-check

The primary-parameter column of the joint Jacobian is compared with the single-parameter block on the same observable; identity confirms both studies use the same protocol and normalization.

- `voltage_0.5C`: single 0.01068, joint column 0.01068, |Δ| 0 (within tolerance: **True**)
- `voltage_1C`: single 0.02131, joint column 0.02131, |Δ| 0 (within tolerance: **True**)
- `voltage_2C`: single 0.04757, joint column 0.04757, |Δ| 0 (within tolerance: **True**)
- `gitt_d_rest_voltage`: single 0.008699, joint column 0.008699, |Δ| 0 (within tolerance: **True**)
- `gitt_d_pulse_drop`: single 0.08177, joint column 0.08177, |Δ| 0 (within tolerance: **True**)
- `gitt_d_relaxation_slope`: single 0.1, joint column 0.1, |Δ| 0 (within tolerance: **True**)
- `eis_re_impedance`: single 0.0008651, joint column 0.0008651, |Δ| 0 (within tolerance: **True**)
- `eis_neg_im_impedance`: single 0.0002081, joint column 0.0002081, |Δ| 0 (within tolerance: **True**)

## Limitations

- SYNTHETIC ONLY: every curve is model-generated, not measured experimentally.
- Local finite-difference FIM at scale factor 1.0; it is not a global identifiability proof.
- Only the three declared parameters are free; every other parameter (porosities, conductivities, other kinetics, electrolyte transport details) remains fixed.
- Function-valued parameters (j0_neg, D_e) are perturbed by a constant multiplicative scale factor, not as arbitrary functions of concentration or temperature; their functional form is assumed known.
- A high parameter correlation means this observable set cannot separate the parameters locally; it does not prove they are physically indistinguishable under a different protocol.
- Marginal standard errors are conditional on the other free parameters and on the declared i.i.d. Gaussian noise.
- GITT pulse drops and sqrt-time slopes include ohmic and kinetic overpotential; they are not pure solid-diffusion estimators.
- No calibration objective, registry record or dossier decision was changed.

A local joint FIM is **not** proof of identifiability (scientific rule 7), and synthetic curves are **not** experimental validation (rule 8).
