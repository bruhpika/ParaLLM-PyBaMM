# Forward observables: EIS, OCV-vs-SOC, dQ/dV and GITT-D

This page documents the forward-observable layer in
`src/pybamm_closed_loop/pybamm_engine/observables.py`. It was implemented
against the pinned, installed **PyBaMM 26.8.0.0**; every API below was verified
by introspection (not assumed from another version). All PyBaMM calls stay
inside `pybamm_engine/`.

!!! warning "Honest scope"
    Everything produced here is **SYNTHETIC / model-generated**. There are **no
    real-data claims** (D4). A successful fit to any of these curves is **not
    proof of parameter identifiability** (scientific rule 7). Synthetic
    recovery is a method check, not experimental validation (scientific rule 8).

## Verified PyBaMM 26.8.0.0 API signatures

Recorded live via `inspect.signature` and reproduced into benchmark manifests by
`verified_api_signatures()`.

| API | Verified signature |
| --- | --- |
| `pybamm.EISSimulation` | `(model, parameter_values=None, geometry=None, submesh_types=None, var_pts=None, spatial_methods=None, skip_surface_form_check=False)` |
| `EISSimulation.solve` | `(self, frequencies, inputs=None, initial_soc=None)` |
| `pybamm.EISSolution` | `(frequencies, impedance)`; exposes `.frequencies`, `.impedance`, `get_data_dict()` |
| `EISSolution.get_data_dict` | `(self)` → `{'Frequency [Hz]', 'Z_re [Ohm]', 'Z_im [Ohm]'}` |
| `pybamm.lithium_ion.get_initial_stoichiometries` | `(initial_value, parameter_values, direction=None, param=None, known_value='cyclable lithium capacity', options=None, tol=1e-06, inputs=None, esoh_solver=None)` → `(x, y)` |
| `pybamm.lithium_ion.get_min_max_stoichiometries` | `(parameter_values, direction=None, param=None, known_value='cyclable lithium capacity', options=None, inputs=None)` → `(x_0, x_100, y_100, y_0)` |
| `pybamm.Experiment` | `(operating_conditions, period=None, temperature=None, termination=None)` |
| `pybamm.Simulation` | `(model, experiment=None, geometry=None, parameter_values=None, submesh_types=None, var_pts=None, spatial_methods=None, solver=None, output_variables=None, C_rate=None, discretisation_kwargs=None, cache_esoh=True, experiment_model_mode='legacy')` |
| `Simulation.solve` | `(self, t_eval=None, solver=None, save_at_cycles=None, calc_esoh=None, starting_solution=None, initial_soc=None, direction=None, callbacks=None, showprogress=False, inputs=None, t_interp=None, **kwargs)` |
| `pybamm.step.string` | `(text, **kwargs)` — verified for `Discharge at 0.5 A for 20 s`, `Discharge at C/10 for 20 s`, `Charge at 0.5 A for 20 s` |

Parameter keys used (all verified present in the installed `Chen2020` set):
`Negative electrode OCP [V]`, `Positive electrode OCP [V]`,
`Nominal cell capacity [A.h]`, `Terminal voltage [V]`, `Current [A]`,
`Discharge capacity [A.h]`, `Open-circuit voltage at 0% SOC [V]`,
`Open-circuit voltage at 100% SOC [V]`. No parameter value or PyBaMM name is
invented; values always come from the installed parameter set.

## Observables and their provenance

### EIS (`compute_eis`)
Complex impedance `Z(f) = V(f)/I(f)` at a chosen `initial_soc`, using
`pybamm.EISSimulation`. The constructor validates that the model contains
`Voltage [V]` and `Current [A]` and that the model option
`surface form` is `differential` or `algebraic`. `build_eis_model()` builds
`SPM`, `SPMe` or `DFN` with `surface form: differential` (each verified to
solve on `Chen2020`). Outputs: `frequencies_Hz`, complex `impedance_Ohm`,
`z_re_Ohm`, `z_im_Ohm`.

Limitation: a linearised small-signal response about one operating point; it
does not by itself constrain large-signal transport parameters uniquely.

### OCV vs SOC (`compute_ocv_vs_soc`)
PyBaMM 26.8.0.0 has **no dedicated OCV-vs-SOC helper**. The curve is composed
from two verified pieces: `get_initial_stoichiometries(soc, pv)` (eSOH-based
`(x, y)` at each SOC) and the parameter set's own electrode OCP functions,
`OCV = U_positive(y) - U_negative(x)`. Endpoint values were cross-checked
against the parameter set's `Open-circuit voltage at 0%/100% SOC [V]`.

Limitation: equilibrium thermodynamic curve only; hysteresis, temperature and
relaxation-time effects are not represented.

### dQ/dV (`dqdv_from_capacity_voltage`, `dqdv_from_solution`)
Pure post-processing of voltage vs capacity from a galvanostatic branch:
`dQ/dV = numpy.gradient(Q, V)` in Ah/V (negative on discharge under this
explicit sign convention). Inputs must be finite, capacity strictly
increasing, voltage monotonic with sufficiently large steps; invalid data
raises `ValueError` rather than being silently smoothed or interpolated.

Limitation: finite differences amplify measurement noise and solver output
spacing; no smoothing is applied, and peak positions are resolution-dependent.

### GITT-D (`run_gitt_d`)
PyBaMM 26.8.0.0 has **no dedicated GITT API**. A documented galvanostatic
intermittent titration (discharge direction) is built from verified
`Experiment` step strings: alternating `Discharge at <I> A for <t> s` and
`Rest for <t> s`. The result records time, voltage, current, capacity,
per-sample `phase` and `titration_index`; `gitt_relaxation_summary()` reports
the last rest sample per titration. An approximate SOC estimate, when
present, is `initial_soc - Q / 'Nominal cell capacity [A.h]'` and is labelled
as approximate (it ignores fade and coulombic inefficiency).

Limitation: end-of-rest voltage is *not* an extrapolated equilibrium OCP;
actual titration protocols require real experimental timing and validation.

## Identifiability tooling

`calibration/identifiability.py::multi_observable_fim` stacks dimensionless
sensitivities (`S = (x / y_scale) * dY/dx`, weighted by a user-supplied noise
`sigma`) from several observable prediction Jacobians. It is a **local,
linearised sensitivity diagnostic assuming independent Gaussian noise**. It
contains no PyBaMM calls and no data generation. Well-conditioned combined
FIMs do **not** prove global identifiability, and the callers must supply
their own assumed noise scales; fitting workflows and existing V2.x code are
unchanged.

## Observable-augmented observability diagnostic (negative diffusivity)

`benchmarks/observables/diffusivity_multi_observable_fim.py` (config:
`configs/v03/observable_identifiability.yaml`; artifact:
`results/observables/diffusivity_multi_observable_fim.{json,md}`) asks whether
the committed **UNOBSERVABLE** verdict for
`Negative particle diffusivity [m2.s-1]` (voltage-only, ≤2C; mean |S| 0.011 /
0.021 / 0.048 vs threshold 0.05) changes when non-voltage observables are
added.

Everything is model-generated (**SYNTHETIC**) and **diagnostic only**: no
calibration objective, registry record or dossier decision changes.

**Protocol correction (2026-11-27).** The first committed run started GITT from
the PyBaMM default 100% SOC, where the graphite OCP is flat. Its "no flip"
conclusion was a protocol artefact, not a transport result. The committed
protocol now starts at **20% SOC and 0.2C**; a validity grid over SOC
0.15–0.30 and 0.1–0.2C showed every low-SOC point clears the recorded
sensitivity bar (0.15 SOC at 0.5C was rejected: V_min = 3.03 V approaches the
3.0 V cutoff). `gitt_protocol_warnings()` now flags full-charge GITT runs, and
an integration test pins the corrected protocol.

Results (PyBaMM 26.8.0.0, Chen2020, DFN, `rel_perturbation = 0.02`):

| observable | n | mean \|S\| | implied rel. SE | verdict |
|---|---:|---:|---:|---|
| voltage 0.5C | 24 | 0.01068 | 0.0171 | UNOBSERVABLE |
| voltage 1C | 24 | 0.02131 | 0.00872 | UNOBSERVABLE |
| voltage 2C | 24 | 0.04757 | 0.00368 | UNOBSERVABLE |
| GITT-D end-of-rest voltage | 5 | 0.00870 | 0.0483 | UNOBSERVABLE |
| GITT-D pulse voltage drop | 5 | **0.0818** | 0.00533 | **OBSERVABLE** |
| GITT-D sqrt(t) relaxation slope | 5 | **0.100** | 0.00433 | **OBSERVABLE** |
| EIS Re(Z) | 28 | 8.7e-4 | 0.0504 | UNOBSERVABLE |
| EIS −Im(Z) | 28 | 2.1e-4 | 0.231 | UNOBSERVABLE |
| OCV-vs-SOC (negative control) | 21 | 0 | ∞ | UNOBSERVABLE |

- Combined FIM: 9.029e4 (voltage only) → **1.796e5** (voltage + low-SOC GITT-D
  + EIS); standard-error reduction factor **1.41**.
- **Verdict flips** from `UNOBSERVABLE` to `OBSERVABLE` under the declared
  conjunction rule (combined relative SE ≤ 5 % **and** at least one block
  clearing mean-|S| ≥ 0.05). The flip is carried by the two transport-bearing
  GITT features, not by EIS.
- The **dossier action is unchanged** (`MEASURE`): a local single-parameter FIM
  is not an identifiability proof (rule 7), and changing the action needs owner
  approval (rule 10).
- The committed voltage-only baseline is reproduced **exactly** (Δ = 0.0 at
  0.5C/1C/2C), validating the study device and the comparison.

Limits of the flip:

1. **Single-parameter sensitivity in this section.** Every other parameter is
   held fixed here; the joint section below frees `D_neg`, `j0_neg` and `D_e`
   together and finds a variance inflation factor of 1.25 with |correlation| ≤
   0.44. Other parameters (porosities, conductivities, positive-electrode
   parameters, further kinetics) remain fixed. The pulse drop and relaxation
   slope contain ohmic and kinetic overpotential, not pure solid diffusion.
2. **GITT protocol dependence.** At 100% SOC the same features are numerically
   weak (pulse drop 0.005, slope ~1e-5). The result is a statement about a
   low-SOC protocol, not about GITT in general.
3. **EIS remains blind in this stack.** A 100× change in
   `Negative particle diffusivity [m2.s-1]` changes Re(Z) by ~8e-5 relative,
   while a 10× change in the negative exchange-current density changes it by
   ~0.37 relative. The positive control proves parameter propagation works, so
   this is a PyBaMM 26.8.0.0 formulation limitation, not a physical conclusion
   about real cells. The integration test pins this contrast.

Interpretation guard: the a-priori diffusion scale (τ = R²/D ≈ 1041 s,
f ≈ 1.5e-4 Hz) was computed from the installed parameter set and the EIS band
(1e-4–10 Hz) covers it, so the EIS null is not an artefact of a mis-placed
frequency window. The GITT sqrt(t) window (first 5 rest samples = 150 s) is
short against τ, so the semi-infinite approximation used by the slope feature
is appropriate.

### Joint multi-parameter FIM: does the GITT signal survive collinearity?

Artifact: `results/observables/joint_diffusivity_fim.{json,md}`. The same
protocols, noise and 2 % central difference are used, but `D_neg`, `j0_neg`
and `D_e` are free together (each at baseline scale factor 1.0). Function-valued
parameters are perturbed by a constant multiplicative factor; their functional
form is assumed known.

| observable set (3 parameters free) | `D_neg` marginal rel. SE | classification | cond(FIM) |
|---|---:|---|---:|
| voltage only | 0.00471 | UNOBSERVABLE | 1.50e3 |
| GITT-D only | 0.0142 | OBSERVABLE | 5.97e2 |
| voltage + GITT-D | 0.00303 | OBSERVABLE | 6.28e2 |
| EIS only | 0.274 | UNOBSERVABLE | 5.87e7 |
| all configured | **0.00263** | **OBSERVABLE** | 5.67e3 |

| parameter | joint marginal rel. SE | single-parameter ref. | variance inflation | strongest mean \|S\| |
|---|---:|---:|---:|---:|
| `D_neg` | 0.00263 | 0.00236 | 1.25 | 0.100 |
| `j0_neg` | 3.84e-5 | 3.52e-5 | 1.19 | 1.89 |
| `D_e` | 1.47e-4 | 1.22e-4 | 1.45 | 1.25 |

Joint correlations: `D_neg`–`j0_neg` **0.153**, `D_neg`–`D_e` **−0.444**,
`j0_neg`–`D_e` **−0.398** — all below the declared 0.9 collinearity warning.
Freeing the other two parameters inflates the `D_neg` variance by only 25 %
(SE by ~12 %), and the all-observable joint fit improves the `D_neg` SE by
**1.79×** relative to the voltage-only joint fit. A finite-difference step sweep
(0.5 %, 1 %, 5 %) leaves the classification unchanged; the largest SE deviation
is 0.59 % and the largest correlation deviation is 0.006.

Honest reading:

- The single-parameter flip is **not** an artefact of freezing kinetics and
  electrolyte transport: this three-parameter joint fit retains a 0.26 %
  marginal SE and no severe collinearity.
- The **voltage-only joint fit already meets the relative-SE limb** (0.47 %).
  Its `UNOBSERVABLE` label comes from the declared conjunction's second limb:
  no individual voltage block reaches mean |S| ≥ 0.05 (strongest 0.0476). The
  flip is therefore a **conservative classification flip**, not a claim that
  voltage data are uninformative. The joint FIM says the opposite: voltage data
  carry real local information about `D_neg` under the declared noise.
- This is still a **local** three-parameter FIM on **synthetic** curves with
  i.i.d. noise. It is not global identifiability (rule 7), not experimental
  validation (rule 8), and not a calibration recommendation. The dossier action
  remains `MEASURE` pending owner review (rule 10).

## Reproduction

```bash
# Fast software tests (unit + integration, benchmark/characterization excluded)
.venv/bin/python -m pytest -q -m "not benchmark and not characterization"

# Scientific benchmark: regenerate results/observables/
.venv/bin/python -o addopts='' -m benchmark \
    benchmarks/observables/run_forward_observables.py

# Observable-augmented observability diagnostic (writes the main and joint
# artifacts: diffusivity_multi_observable_fim.{json,md} and
# joint_diffusivity_fim.{json,md})
.venv/bin/python benchmarks/observables/diffusivity_multi_observable_fim.py \
    --config configs/v03/observable_identifiability.yaml

# Equivalent script entry point
.venv/bin/python benchmarks/observables/run_forward_observables.py --out results/observables

# Ecosystem-gated test (needs PyBOP) — runs under the CPython 3.12 ecosystem env
.venv-ecosystem312/bin/python -m pytest -q tests/integration/test_observables_ecosystem.py
```

Benchmark artifacts are deterministic (no seeds needed): arrays in
`results/observables/observables_arrays.npz` and provenance, protocol settings,
shapes, live API signatures and limitations in
`results/observables/run_manifest.json`.

## Unresolved issues / hard blockers

* **No dedicated OCV-vs-SOC API** in PyBaMM 26.8.0.0 — implemented from the
  eSOH stoichiometry solver plus parameter-set OCP functions, not guessed.
* **No dedicated GITT API** in PyBaMM 26.8.0.0 — implemented as an
  `Experiment`; protocol numbers are user-supplied settings, not chemistry.
* **dQ/dV has no PyBaMM helper** — pure post-processing; noise robustness for
  real experimental data is untested and out of scope here.
* The existing voltage-only synthetic fitting path
  (`calibration/synthetic.py`, `benchmarks/identifiability/*` and V2.x code) is
  **intentionally unchanged** in this milestone; connecting these observables
  to calibration objectives would change scientific scope and needs separate
  approval.
* **PyBaMM 26.8.0.0 EIS ignores solid particle diffusivity** (verified by a
  positive control; see the diagnostic section). The EIS result is therefore
  conditional on this tool behaviour. Testing whether real-cell EIS informs
  diffusivity would require an impedance formulation that includes solid
  diffusion — unavailable in the pinned stack and not approximated here.
