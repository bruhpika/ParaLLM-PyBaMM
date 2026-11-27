"""Forward observables: EIS, OCV-vs-SOC, dQ/dV and GITT-D.

This module owns the forward-observable layer. Every direct PyBaMM call lives
here (or in :mod:`pybamm_closed_loop.pybamm_engine.engine`); callers receive
plain numpy arrays plus explicit metadata.

API surface verified by introspection against the pinned PyBaMM 26.8.0.0::

    pybamm.EISSimulation(model, parameter_values=None, geometry=None,
        submesh_types=None, var_pts=None, spatial_methods=None,
        skip_surface_form_check=False)
    pybamm.EISSimulation.solve(self, frequencies, inputs=None, initial_soc=None)
    pybamm.EISSolution(frequencies, impedance)
    pybamm.EISSolution.get_data_dict()  -> {'Frequency [Hz]', 'Z_re [Ohm]',
        'Z_im [Ohm]'}; also exposes `.impedance` (complex) and `.frequencies`
    pybamm.lithium_ion.get_initial_stoichiometries(initial_value,
        parameter_values, direction=None, param=None,
        known_value='cyclable lithium capacity', options=None, tol=1e-06,
        inputs=None, esoh_solver=None) -> (x, y)
    pybamm.lithium_ion.get_min_max_stoichiometries(parameter_values, ...)
        -> (x_0, x_100, y_100, y_0)
    pybamm.Experiment(operating_conditions, period=None, temperature=None,
        termination=None)
    pybamm.Simulation(model, experiment=None, geometry=None,
        parameter_values=None, ..., solver=None, ..., C_rate=None, ...)
    pybamm.Simulation.solve(self, t_eval=None, solver=None, ...,
        initial_soc=None, direction=None, ...)
    pybamm.step.string(step)  -> verified for
        'Discharge at 0.5 A for 20 s', 'Discharge at C/10 for 20 s',
        'Charge at 0.5 A for 20 s'

Verified parameter keys used (present in the installed ``Chen2020`` set):
``"Negative electrode OCP [V]"``, ``"Positive electrode OCP [V]"``,
``"Nominal cell capacity [A.h]"``, ``"Terminal voltage [V]"``,
``"Current [A]"``, ``"Discharge capacity [A.h]"``.

Important scientific caveats (see docs/FORWARD_OBSERVABLES.md):

* PyBaMM 26.8.0.0 has **no dedicated OCV-vs-SOC helper** and **no dedicated
  GITT API**. OCV-vs-SOC is assembled from the eSOH stoichiometry solver and
  the parameter set's own OCP functions; GITT-D is a documented galvanostatic
  intermittent ``Experiment``. No missing API is guessed.
* dQ/dV is pure post-processing of voltage vs capacity and is noise-sensitive.
* A successful fit to any of these curves is *not* proof of parameter
  identifiability, and all data produced here is synthetic/model-generated,
  never experimental validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

_OCP_NEGATIVE_KEY = "Negative electrode OCP [V]"
_OCP_POSITIVE_KEY = "Positive electrode OCP [V]"
_NOMINAL_CAPACITY_KEY = "Nominal cell capacity [A.h]"
_VOLTAGE_KEY = "Terminal voltage [V]"
_CURRENT_KEY = "Current [A]"
_CAPACITY_KEY = "Discharge capacity [A.h]"

_EIS_MODEL_NAMES = ("SPM", "SPMe", "DFN")


@dataclass
class EisResult:
    """Complex impedance spectrum at one operating point."""

    frequencies_Hz: np.ndarray
    impedance_Ohm: np.ndarray  # complex
    z_re_Ohm: np.ndarray
    z_im_Ohm: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OcvSocResult:
    """Equilibrium (open-circuit) voltage as a function of state of charge."""

    soc: np.ndarray
    ocv_V: np.ndarray
    x_negative: np.ndarray
    y_positive: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DqDvResult:
    """Differential capacity dQ/dV from a galvanostatic voltage-capacity curve."""

    capacity_Ah: np.ndarray
    voltage_V: np.ndarray
    dqdv_Ah_per_V: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GittdResult:
    """Galvanostatic intermittent titration (discharge direction) time series."""

    time_s: np.ndarray
    voltage_V: np.ndarray
    current_A: np.ndarray
    capacity_Ah: np.ndarray
    phase: list[str]  # 'pulse' or 'rest' at each sample
    titration_index: np.ndarray  # 0..n_pulses-1; -1 before the first pulse
    metadata: dict[str, Any] = field(default_factory=dict)


def _as_1d(name: str, values: Any) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} must be 1-dimensional, got shape {array.shape}")
    return array


def ocv_from_stoichiometries(
    x: Any, y: Any, negative_ocp: Callable[[float], float], positive_ocp: Callable[[float], float]
) -> np.ndarray:
    """Compute OCV = U_positive(y) - U_negative(x) from electrode stoichiometries.

    Pure function: ``negative_ocp`` / ``positive_ocp`` may be PyBaMM parameter
    functions or simple callables supplied by a test fake. Nothing here
    synthesizes stoichiometry values.
    """
    xs, ys = _as_1d("x", x), _as_1d("y", y)
    if xs.shape != ys.shape:
        raise ValueError(f"x and y must have the same shape, got {xs.shape} and {ys.shape}")
    un = np.array([float(negative_ocp(float(xi))) for xi in xs], dtype=float)
    up = np.array([float(positive_ocp(float(yi))) for yi in ys], dtype=float)
    return up - un


def dqdv_from_capacity_voltage(
    capacity_Ah: Any, voltage_V: Any, *, min_dV_V: float = 1e-9
) -> DqDvResult:
    """Finite-difference dQ/dV of a clean galvanostatic curve (Ah/V).

    The convention is ``dQ/dV = gradient(Q, V)``: for a discharge (Q rising,
    V falling) this is negative. ``metadata['sign_convention']`` records this
    explicitly; negate the array if a positive discharge peak convention is
    wanted. No smoothing or interpolation is applied silently.
    """
    q, v = _as_1d("capacity_Ah", capacity_Ah), _as_1d("voltage_V", voltage_V)
    if q.shape != v.shape:
        raise ValueError(f"capacity and voltage must have the same shape: {q.shape} vs {v.shape}")
    if q.size < 3:
        raise ValueError("at least 3 samples are required for dQ/dV")
    if not np.all(np.isfinite(q)) or not np.all(np.isfinite(v)):
        raise ValueError("non-finite values in capacity or voltage")
    dq = np.diff(q)
    if np.any(dq <= 0):
        raise ValueError("capacity must be strictly increasing along the curve")
    dv = np.diff(v)
    if np.any(np.abs(dv) <= min_dV_V):
        raise ValueError(f"voltage steps must exceed {min_dV_V} V (flat/duplicate voltages)")
    if np.any(dv > 0) and np.any(dv < 0):
        raise ValueError("voltage must be monotonic (a single charge or discharge branch)")
    derivative = np.gradient(q, v)
    direction = "discharge" if dv[0] < 0 else "charge"
    return DqDvResult(
        capacity_Ah=q,
        voltage_V=v,
        dqdv_Ah_per_V=derivative,
        metadata={
            "method": "numpy.gradient(Q, V), no smoothing",
            "sign_convention": "gradient(Q, V): negative on discharge",
            "direction": direction,
            "n_samples": int(q.size),
            "synthetic_only": True,
        },
    )


def extract_eis_arrays(eis_solution: Any) -> EisResult:
    """Extract a plain-array EIS result from an ``EISSolution``-like object.

    Uses only the verified ``get_data_dict()`` keys and the complex
    ``impedance`` attribute (with a deterministic re/im fallback for fakes).
    """
    data = eis_solution.get_data_dict()
    for key in ("Frequency [Hz]", "Z_re [Ohm]", "Z_im [Ohm]"):
        if key not in data:
            raise KeyError(f"EIS solution is missing verified key {key!r}")
    freq = _as_1d("Frequency [Hz]", data["Frequency [Hz]"])
    z_re = _as_1d("Z_re [Ohm]", data["Z_re [Ohm]"])
    z_im = _as_1d("Z_im [Ohm]", data["Z_im [Ohm]"])
    if not (freq.shape == z_re.shape == z_im.shape):
        raise ValueError("EIS frequency and impedance arrays must have the same shape")
    complex_attr = getattr(eis_solution, "impedance", None)
    if complex_attr is None:
        impedance = z_re + 1j * z_im
        source = "reconstructed from get_data_dict() re/im parts"
    else:
        impedance = np.asarray(complex_attr, dtype=complex)
        if impedance.shape != freq.shape:
            raise ValueError("EIS impedance array has an unexpected shape")
        source = "EISSolution.impedance"
    return EisResult(
        frequencies_Hz=freq,
        impedance_Ohm=impedance,
        z_re_Ohm=z_re,
        z_im_Ohm=z_im,
        metadata={"complex_impedance_source": source, "synthetic_only": True},
    )


def gitt_phase_labels(
    current_A: Any, *, tolerance_A: float = 1e-9
) -> tuple[list[str], np.ndarray]:
    """Label each sample as a current 'pulse' or a 'rest' from the current trace.

    titration_index increments at each pulse onset and stays -1 before the
    first pulse; rest samples inherit the index of the preceding pulse.
    """
    current = _as_1d("current_A", current_A)
    if current.size == 0:
        raise ValueError("current trace is empty")
    is_pulse = np.abs(current) > tolerance_A
    phases: list[str] = []
    indices = np.full(current.size, -1, dtype=int)
    titration = -1
    previous_pulse = False
    for i, on in enumerate(is_pulse):
        if on and not previous_pulse:
            titration += 1
        if on:
            phases.append("pulse")
        else:
            phases.append("rest")
        indices[i] = titration
        previous_pulse = bool(on)
    return phases, indices


def gitt_relaxation_summary(result: GittdResult) -> list[dict[str, Any]]:
    """End-of-rest voltage/capacity for each titration (pure post-processing).

    Records the last sample of each rest block, i.e. the quasi-relaxed OCV
    point used in a GITT-D analysis. Does not extrapolate to infinite time.
    """
    summary: list[dict[str, Any]] = []
    for index in sorted({int(i) for i in result.titration_index if int(i) >= 0}):
        mask = result.titration_index == index
        rest_positions = [i for i in np.flatnonzero(mask) if result.phase[i] == "rest"]
        if not rest_positions:
            continue
        last = rest_positions[-1]
        entry: dict[str, Any] = {
            "titration_index": index,
            "time_s": float(result.time_s[last]),
            "voltage_V": float(result.voltage_V[last]),
            "capacity_Ah": float(result.capacity_Ah[last]),
        }
        soc_est = result.metadata.get("soc_estimate_from_capacity")
        if soc_est is not None:
            entry["soc_estimate"] = float(np.asarray(soc_est)[last])
        summary.append(entry)
    return summary


def _pybamm_signature(path: str) -> str:
    """Return the live signature of a verified PyBaMM callable (no guessing)."""
    import inspect

    import pybamm

    target: Any = pybamm
    for part in path.split("."):
        target = getattr(target, part)
    return f"{path}{inspect.signature(target)}"


def verified_api_signatures() -> dict[str, str]:
    """Live API signatures used by this module, for provenance records."""
    return {
        "pybamm.__version__": _version_string(),
        "EISSimulation": _pybamm_signature("EISSimulation"),
        "EISSimulation.solve": _pybamm_signature("EISSimulation.solve"),
        "EISSolution": _pybamm_signature("EISSolution"),
        "EISSolution.get_data_dict": _pybamm_signature("EISSolution.get_data_dict"),
        "get_initial_stoichiometries": _pybamm_signature(
            "lithium_ion.get_initial_stoichiometries"
        ),
        "get_min_max_stoichiometries": _pybamm_signature(
            "lithium_ion.get_min_max_stoichiometries"
        ),
        "Experiment": _pybamm_signature("Experiment"),
        "Simulation": _pybamm_signature("Simulation"),
        "Simulation.solve": _pybamm_signature("Simulation.solve"),
        "step.string": _pybamm_signature("step.string"),
    }


def _version_string() -> str:
    import pybamm

    return str(pybamm.__version__)


def build_eis_model(model_name: str = "SPM") -> Any:
    """Build a model with the EIS-required 'surface form' option verified in 26.8.0.0."""
    import pybamm

    if model_name not in _EIS_MODEL_NAMES:
        raise ValueError(
            f"model_name must be one of {_EIS_MODEL_NAMES}; for other models pass "
            "an explicit model object with 'surface form' in {'differential', 'algebraic'}"
        )
    model_cls = getattr(pybamm.lithium_ion, model_name)
    return model_cls(options={"surface form": "differential"})


def compute_eis(
    model_or_name: Any,
    parameter_values: Any,
    frequencies_Hz: Any,
    *,
    initial_soc: float | None = None,
    inputs: dict[str, float] | None = None,
) -> EisResult:
    """Compute EIS with ``pybamm.EISSimulation`` (verified 26.8.0.0 API).

    ``model_or_name`` is either a PyBaMM model instance or one of the
    verified names in ``_EIS_MODEL_NAMES``. Frequencies are in Hz.
    """
    import pybamm

    frequencies = _as_1d("frequencies_Hz", frequencies_Hz)
    if frequencies.size == 0 or np.any(frequencies <= 0):
        raise ValueError("frequencies_Hz must be non-empty and strictly positive")
    model = build_eis_model(model_or_name) if isinstance(model_or_name, str) else model_or_name
    simulation = pybamm.EISSimulation(model, parameter_values)
    kwargs: dict[str, Any] = {}
    if inputs is not None:
        kwargs["inputs"] = inputs
    if initial_soc is not None:
        kwargs["initial_soc"] = float(initial_soc)
    solution = simulation.solve(frequencies, **kwargs)
    result = extract_eis_arrays(solution)
    result.metadata.update(
        {
            "api": "pybamm.EISSimulation.solve(frequencies, inputs=None, initial_soc=None)",
            "pybamm_version": str(pybamm.__version__),
            "surface_form": "differential",
            "initial_soc": initial_soc,
            "verified_signatures": verified_api_signatures(),
            "synthetic_only": True,
        }
    )
    return result


def compute_ocv_vs_soc(
    parameter_values: Any,
    soc_points: Any,
    *,
    direction: str | None = None,
    known_value: str = "cyclable lithium capacity",
) -> OcvSocResult:
    """Equilibrium OCV vs SOC from the eSOH stoichiometry solver and OCP functions.

    No dedicated OCV-vs-SOC API exists in PyBaMM 26.8.0.0; this composes two
    verified pieces: ``get_initial_stoichiometries`` and the parameter set's
    own electrode OCP functions. SOC is dimensionless in [0, 1].
    """
    import pybamm

    soc = _as_1d("soc_points", soc_points)
    if soc.size == 0 or np.any(soc < 0) or np.any(soc > 1):
        raise ValueError("soc_points must be non-empty and within [0, 1]")
    for key in (_OCP_NEGATIVE_KEY, _OCP_POSITIVE_KEY):
        if key not in parameter_values.keys():
            raise KeyError(f"parameter set is missing required verified key {key!r}")
    negative_ocp = parameter_values[_OCP_NEGATIVE_KEY]
    positive_ocp = parameter_values[_OCP_POSITIVE_KEY]
    x_values: list[float] = []
    y_values: list[float] = []
    for value in soc:
        x, y = pybamm.lithium_ion.get_initial_stoichiometries(
            float(value),
            parameter_values,
            direction=direction,
            known_value=known_value,
        )
        x_values.append(float(x))
        y_values.append(float(y))
    xs, ys = np.asarray(x_values), np.asarray(y_values)
    ocv = ocv_from_stoichiometries(xs, ys, negative_ocp, positive_ocp)
    x0, x100, y100, y0 = pybamm.lithium_ion.get_min_max_stoichiometries(
        parameter_values, direction=direction, known_value=known_value
    )
    return OcvSocResult(
        soc=soc,
        ocv_V=ocv,
        x_negative=xs,
        y_positive=ys,
        metadata={
            "method": "eSOH stoichiometry + parameter-set OCP functions (no dedicated API)",
            "api": "pybamm.lithium_ion.get_initial_stoichiometries",
            "ocp_keys": [_OCP_NEGATIVE_KEY, _OCP_POSITIVE_KEY],
            "direction": direction,
            "known_value": known_value,
            "min_max_stoichiometries": {
                "x_0": float(x0),
                "x_100": float(x100),
                "y_100": float(y100),
                "y_0": float(y0),
            },
            "pybamm_version": str(pybamm.__version__),
            "synthetic_only": True,
        },
    )


def run_gitt_d(
    parameter_values: Any,
    *,
    current_A: float,
    pulse_duration_s: float,
    rest_duration_s: float,
    n_pulses: int,
    period_s: float,
    model_name: str = "SPM",
    initial_soc: float | None = None,
) -> GittdResult:
    """Galvanostatic intermittent titration, discharge direction (GITT-D).

    PyBaMM 26.8.0.0 has no dedicated GITT API. This builds a documented
    intermittent protocol from verified ``pybamm.Experiment`` step strings:
    alternating ``Discharge at <I> A for <t> s`` and ``Rest for <t> s``.
    All values are user-supplied protocol settings, *not* invented chemistry.
    """
    import pybamm

    if current_A <= 0:
        raise ValueError("current_A must be positive (discharge magnitude)")
    if pulse_duration_s <= 0 or rest_duration_s <= 0 or period_s <= 0:
        raise ValueError("durations and period must be positive")
    if n_pulses < 1 or int(n_pulses) != n_pulses:
        raise ValueError("n_pulses must be a positive integer")
    if model_name not in _EIS_MODEL_NAMES:
        raise ValueError(f"model_name must be one of {_EIS_MODEL_NAMES}")
    steps: list[str] = []
    for _ in range(int(n_pulses)):
        steps.append(f"Discharge at {current_A:g} A for {pulse_duration_s:g} s")
        steps.append(f"Rest for {rest_duration_s:g} s")
    experiment = pybamm.Experiment(steps, period=f"{period_s:g} s")
    model_cls = getattr(pybamm.lithium_ion, model_name)
    simulation = pybamm.Simulation(model_cls(), parameter_values=parameter_values, experiment=experiment)
    solve_kwargs: dict[str, Any] = {}
    if initial_soc is not None:
        solve_kwargs["initial_soc"] = float(initial_soc)
    solution = simulation.solve(**solve_kwargs)
    time = _as_1d("solution.t", solution.t)
    voltage = _as_1d(_VOLTAGE_KEY, solution[_VOLTAGE_KEY].entries)
    current = _as_1d(_CURRENT_KEY, solution[_CURRENT_KEY].entries)
    capacity = _as_1d(_CAPACITY_KEY, solution[_CAPACITY_KEY].entries)
    if not (time.size == voltage.size == current.size == capacity.size):
        raise ValueError("GITT solution arrays have inconsistent lengths")
    phases, indices = gitt_phase_labels(current)
    soc_estimate = None
    if _NOMINAL_CAPACITY_KEY in parameter_values.keys():
        nominal = float(parameter_values[_NOMINAL_CAPACITY_KEY])
        start = float(initial_soc) if initial_soc is not None else 1.0
        soc_estimate = start - capacity / nominal
    result = GittdResult(
        time_s=time,
        voltage_V=voltage,
        current_A=current,
        capacity_Ah=capacity,
        phase=phases,
        titration_index=indices,
        metadata={
            "protocol": "galvanostatic intermittent titration, discharge (GITT-D)",
            "steps": steps,
            "period_s": period_s,
            "n_pulses": int(n_pulses),
            "initial_soc": initial_soc,
            "soc_estimate_from_capacity": soc_estimate,
            "soc_estimate_note": (
                "SOC = initial_soc - Q / 'Nominal cell capacity [A.h]' (approximate, "
                "does not account for capacity fade or non-unity coulombic efficiency)"
            ),
            "api": "pybamm.Experiment + pybamm.Simulation.solve (no dedicated GITT API)",
            "pybamm_version": str(pybamm.__version__),
            "synthetic_only": True,
        },
    )
    return result


def dqdv_from_solution(solution: Any, *, min_dV_V: float = 1e-9) -> DqDvResult:
    """Compute dQ/dV directly from a galvanostatic PyBaMM solution."""
    capacity = _as_1d(_CAPACITY_KEY, solution[_CAPACITY_KEY].entries)
    voltage = _as_1d(_VOLTAGE_KEY, solution[_VOLTAGE_KEY].entries)
    result = dqdv_from_capacity_voltage(capacity, voltage, min_dV_V=min_dV_V)
    result.metadata["source"] = "pybamm.Solution via verified 'Discharge capacity [A.h]'"
    return result
