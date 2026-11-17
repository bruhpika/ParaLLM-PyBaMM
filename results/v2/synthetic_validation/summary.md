# V2.4 — synthetic end-to-end validation

**Label:** SYNTHETIC — deliberately mismatched ground truth and synthetic measurements; not experimental validation (scientific rule 8)

## Setup (synthetic, deliberately mismatched)

- train on `1C`, validate on 0.5C, 2C (held out)
- assembled start values (real registry + observability join): {'Negative electrode active material volume fraction': 0.75, 'Positive electrode active material volume fraction': 0.665, 'Negative particle diffusivity [m2.s-1]': 3.3e-14}
- synthetic truth (offset): {'Negative electrode active material volume fraction': 0.72, 'Positive electrode active material volume fraction': 0.63, 'Negative particle diffusivity [m2.s-1]': 5e-14}
- positive fit (CALIBRATE action): neg_electrode_active_material_volume_fraction, pos_electrode_active_material_volume_fraction
- negative control (violates `FIX`): neg_particle_diffusivity
- seed 20261117, noise σ = 0.001 V, maxiter 40

## Held-out-rate voltage RMSE [V]

| arm | 0.5C | 2C | mean | vs baseline |
|---|---:|---:|---:|---:|
| baseline (assembled) | 0.0037 | 0.0054 | 0.0046 | — |
| positive control (fit observable pair) | 0.0010 | 0.0009 | 0.0010 | -0.0036 |
| negative control (fit unobservable param) | 0.0037 | 0.0054 | 0.0046 | +0.0000 |

## Prediction

- expected: positive improves held-out; negative does not improve — **reproduced: True**
- observed: positive improves = True, negative does not improve = True
- fitted values: positive {'Negative electrode active material volume fraction': 0.7171724871993611, 'Positive electrode active material volume fraction': 0.6236380810145133}, negative {'Negative particle diffusivity [m2.s-1]': 3.3e-14} (truth 5e-14)

## Limits

- Synthetic recovery validates the workflow under the assumptions of the generating model. It is NOT experimental validation and does not prove identifiability (scientific rules 7 and 8).
- positive fit scope: the scalar-declarable observable pair only; function-valued kinetics remain CALIBRATE in the action matrix but are outside this run's fitting scope.
