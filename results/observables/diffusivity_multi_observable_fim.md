# Observable-augmented observability diagnostic

**SYNTHETIC OBSERVABLE-AUGMENTED IDENTIFIABILITY DIAGNOSTIC** — diagnostic only; no parameter decision changed.

Parameter: `Negative particle diffusivity [m2.s-1]` · parameter set `Chen2020` · model `DFN` · scale factor 1.0

## A-priori diffusion scales (choose the EIS band before scoring)

- D = 3.3e-14 m²/s, R = 5.86e-06 m
- τ = R²/D = 1041 s → f_diff = 0.0001529 Hz
- EIS band 0.0001–10 Hz covers f_diff: **True**

## GITT-D protocol

- start SOC 0.2, current 1 A (0.2C), 120 s pulse / 180 s rest, 5 pulses
- sqrt(t) fit window: first 5 rest samples

## Per observable

| observable | n | norm | sigma | mean \|S\| | implied rel. SE | classification |
|---|---:|---|---:|---:|---:|---|
| voltage_0.5C | 24 | std | 0.001 | 0.01068 | 0.01711 | UNOBSERVABLE |
| voltage_1C | 24 | std | 0.001 | 0.02131 | 0.008718 | UNOBSERVABLE |
| voltage_2C | 24 | std | 0.001 | 0.04757 | 0.003683 | UNOBSERVABLE |
| gitt_d_rest_voltage | 5 | std | 0.001 | 0.008699 | 0.04826 | UNOBSERVABLE |
| gitt_d_pulse_drop | 5 | mean_magnitude | 0.001 | 0.08177 | 0.005334 | OBSERVABLE |
| gitt_d_relaxation_slope | 5 | mean_magnitude | 0.001 | 0.1 | 0.004331 | OBSERVABLE |
| eis_re_impedance | 28 | std | 0.0003726 | 0.0008651 | 0.05043 | UNOBSERVABLE |
| eis_neg_im_impedance | 28 | std | 0.0003726 | 0.0002081 | 0.2312 | UNOBSERVABLE |
| ocv_soc_control | 21 | std | 0.001 | 0 | inf | UNOBSERVABLE |

## Observable sets

| set | FIM | implied rel. SE | strongest block mean \|S\| | classification |
|---|---:|---:|---:|---|
| voltage only | 9.029e+04 | 0.003328 | 0.04757 | UNOBSERVABLE |
| voltage + GITT-D + EIS | 1.796e+05 | 0.00236 | 0.1 | OBSERVABLE |

Combined-set rule (declared before scoring): conjunction: combined implied rel. SE <= 0.05 AND strongest block mean |S| >= 0.05. Stacking observables can therefore only make a flip harder, never manufacture one.

Information gain (sqrt FIM ratio = standard-error reduction factor): **1.41**

## Verdict

- voltage only: **UNOBSERVABLE**
- voltage + GITT-D + EIS: **OBSERVABLE**
- verdict flip: **True** — The added observables flip the recorded UNOBSERVABLE verdict for this parameter under the declared aggregation rule.
- parameter decision: **unchanged**

## EIS propagation positive control

Scaling `Negative electrode exchange-current density [A.m-2]` by 10 changes the z_re spectrum by **0.3678** (relative). A non-zero relative change proves the EIS simulation applies supplied parameter values. A near-zero change for the study parameter is therefore a property of the installed EIS formulation, not a harness bug.

## Reproduction of the committed voltage-only baseline

| condition | reproduced | committed | |Δ| | within tolerance |
|---|---:|---:|---:|---|
| 0.5C | 0.01068 | 0.01068 | 0 | yes |
| 1C | 0.02131 | 0.02131 | 0 | yes |
| 2C | 0.04757 | 0.04757 | 0 | yes |

## Limitations

- SYNTHETIC ONLY: every curve is model-generated, not measured experimentally.
- Local finite-difference sensitivity at scale factor 1.0; it is not a global identifiability proof.
- Single-parameter sensitivity: every other parameter is held fixed, so joint D-kinetics collinearity is not assessed.
- The result is conditional on the declared noise assumptions in the config.
- No calibration objective, registry record or dossier decision was changed.
- GITT end-of-rest voltages approximate quasi-relaxed OCV; the pulse drop and sqrt-time slope include ohmic and kinetic overpotential, so they are not pure solid-diffusion estimators.
- The GITT protocol must start away from full charge: at 100% SOC the graphite OCP is flat and a low signal is a protocol artefact, not evidence about transport observability (2026-11-27 correction).
- PyBaMM 26.8.0.0 EIS does not respond to the solid particle diffusivity, although it does respond to kinetic and geometric parameters (positive control recorded); this is a verified tool limitation, not a physical conclusion about real cells.
- OCV-vs-SOC is a negative control: equilibrium thermodynamics is insensitive to a transport parameter.

A successful local FIM is **not** proof of parameter identifiability (scientific rule 7), and synthetic curves are **not** experimental validation (rule 8).
