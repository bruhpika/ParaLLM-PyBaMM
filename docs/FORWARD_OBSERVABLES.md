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

## Reproduction

```bash
# Fast software tests (unit + integration, benchmark/characterization excluded)
.venv/bin/python -m pytest -q -m "not benchmark and not characterization"

# Scientific benchmark: regenerate results/observables/
.venv/bin/python -o addopts='' -m benchmark \
    benchmarks/observables/run_forward_observables.py

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
