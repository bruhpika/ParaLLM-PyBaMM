"""PyBaMM simulation engine: build, validate, solve, extract.

This module owns all direct interaction with the PyBaMM API. The API surface
used here was verified against the pinned version (26.8.0.0); no parameter
names, model options or solver classes are assumed from other versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from pybamm_closed_loop.pybamm_engine.config import BaselineRunConfig
from pybamm_closed_loop.pybamm_engine.outputs import ExtractionResult, extract_all
from pybamm_closed_loop.reporting.manifest import build_manifest, parameter_snapshot

_SOLVER_CLASS_NAMES = {
    "idaklu": "IDAKLUSolver",
    "casadi": "CasadiSolver",
    "scipy": "ScipySolver",
}

_MODEL_CLASS_NAMES = {
    "DFN": "DFN",
    "SPMe": "SPMe",
    "SPM": "SPM",
}


class UnknownParameterSetError(KeyError):
    """Raised when a parameter set name is not available in the installed PyBaMM."""


@dataclass
class BaselineRunResult:
    """Complete output of one baseline run."""

    config: BaselineRunConfig
    solution: Any
    extraction: ExtractionResult
    manifest: dict[str, Any]
    parameter_snapshot: dict[str, Any]


def build_parameter_values(config: BaselineRunConfig):
    """Load the configured parameter set from the installed PyBaMM library."""
    import pybamm

    name = config.pybamm.parameter_set
    available = list(pybamm.parameter_sets)
    if name not in available:
        raise UnknownParameterSetError(
            f"parameter set '{name}' not in installed pybamm; available: {available}"
        )
    parameter_values = pybamm.ParameterValues(name)
    return parameter_values


def installed_parameter_sets() -> list[str]:
    """List parameter-set names available in the installed PyBaMM library."""
    import pybamm

    return sorted(pybamm.parameter_sets)


def installed_parameter_names(parameter_set: str = "Chen2020") -> list[str]:
    """List parameter names from an installed PyBaMM parameter set.

    Used by validation to check PyBaMM mappings against the installed version
    without inventing names.
    """
    import pybamm

    if parameter_set not in pybamm.parameter_sets:
        raise UnknownParameterSetError(
            f"parameter set '{parameter_set}' not in installed pybamm; "
            f"available: {list(pybamm.parameter_sets)}"
        )
    return sorted(pybamm.ParameterValues(parameter_set).keys())


def _build_model(model_name: str, options: dict[str, str] | None):
    """Construct a lithium-ion model by verified name (single PyBaMM touchpoint)."""
    import pybamm

    model_cls = getattr(pybamm.lithium_ion, _MODEL_CLASS_NAMES[model_name])
    return model_cls(options=options or None)


def build_model(config: BaselineRunConfig):
    """Build the configured lithium-ion model with explicit options."""
    return _build_model(config.pybamm.model.name, dict(config.pybamm.model.options))


def parameter_set_chemistry(parameter_set: str) -> str | None:
    """Return the installed PyBaMM ``chemistry`` field of a parameter set.

    Introspection only: the value comes from the pinned library, never from a
    hard-coded mapping in this project.
    """
    import pybamm

    if parameter_set not in pybamm.parameter_sets:
        raise UnknownParameterSetError(
            f"parameter set '{parameter_set}' not in installed pybamm; "
            f"available: {list(pybamm.parameter_sets)}"
        )
    raw = pybamm.parameter_sets[parameter_set]
    if not isinstance(raw, dict):
        return None
    chemistry = raw.get("chemistry")
    return str(chemistry) if chemistry is not None else None


def parameter_set_ocp_names(parameter_set: str) -> dict[str, str]:
    """Return the installed OCP identifiers for the positive/negative electrode.

    Function-valued OCPs report their function name; numeric OCPs (e.g. the
    0.0 V lithium-metal counter electrode) report their value as text.
    """
    import pybamm

    if parameter_set not in pybamm.parameter_sets:
        raise UnknownParameterSetError(
            f"parameter set '{parameter_set}' not in installed pybamm; "
            f"available: {list(pybamm.parameter_sets)}"
        )
    pv = pybamm.ParameterValues(parameter_set)
    out: dict[str, str] = {}
    for side, key in (
        ("positive", "Positive electrode OCP [V]"),
        ("negative", "Negative electrode OCP [V]"),
    ):
        value = pv.get(key)
        out[side] = getattr(value, "__name__", str(value))
    return out


def validate_model_options(model_name: str, options: dict[str, str]) -> list[str]:
    """Return PyBaMM's objections to ``options`` (empty list means accepted).

    PyBaMM itself validates option names/values at model construction; this
    helper reports that verdict without embedding a second option vocabulary.
    """
    try:
        _build_model(model_name, dict(options))
    except Exception as exc:  # PyBaMM raises several exception types at build time
        return [f"{type(exc).__name__}: {exc}"]
    return []


def build_solver(config: BaselineRunConfig):
    """Build the configured solver. ``idaklu`` is the recommended solver in PyBaMM 26.8."""
    import pybamm

    cls_name = _SOLVER_CLASS_NAMES[config.pybamm.solver.name]
    solver_cls = getattr(pybamm, cls_name)
    return solver_cls(rtol=config.pybamm.solver.rtol, atol=config.pybamm.solver.atol)


def build_simulation(config: BaselineRunConfig):
    """Assemble model, parameters, solver and experiment into a Simulation."""
    import pybamm

    config.check_pybamm_version()
    model = build_model(config)
    parameter_values = build_parameter_values(config)
    solver = build_solver(config)
    experiment = pybamm.Experiment(list(config.experiment.steps))
    simulation = pybamm.Simulation(
        model,
        experiment=experiment,
        parameter_values=parameter_values,
        solver=solver,
    )
    return simulation


def parameter_set_metadata(config: BaselineRunConfig) -> dict[str, Any]:
    """Record chemistry/citation metadata of the parameter set when available."""
    import pybamm

    raw = pybamm.parameter_sets[config.pybamm.parameter_set]
    meta: dict[str, Any] = {}
    if isinstance(raw, dict):
        for key in ("chemistry", "citation"):
            if key in raw:
                meta[key] = raw[key]
    return meta


def run(config: BaselineRunConfig) -> BaselineRunResult:
    """Run the full baseline: build, solve, extract, and assemble the manifest."""
    simulation = build_simulation(config)
    solution = simulation.solve()
    extraction = extract_all(
        solution,
        series_names=list(config.outputs.series),
        profile_names=list(config.outputs.profile_variables),
        fractions=list(config.outputs.profile_time_fractions),
    )
    manifest = build_manifest(
        config,
        parameter_values=simulation.parameter_values,
        model=simulation.model,
        solution=solution,
        extraction_availability=extraction.availability_report,
        parameter_set_metadata=parameter_set_metadata(config),
    )
    snapshot = parameter_snapshot(simulation.parameter_values)
    return BaselineRunResult(
        config=config,
        solution=solution,
        extraction=extraction,
        manifest=manifest,
        parameter_snapshot=snapshot,
    )


def save_result(result: BaselineRunResult, out_dir) -> dict[str, str]:
    """Write solution arrays, snapshot and manifest to disk. Returns written paths."""
    import json
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    arrays: dict[str, np.ndarray] = {}
    for name, arr in result.extraction.series.items():
        arrays[f"series__{name}"] = arr
    for name, prof in result.extraction.profiles.items():
        arrays[f"profile__{name}__coords"] = prof.coordinates
        arrays[f"profile__{name}__times"] = np.asarray(prof.times_s, dtype=float)
        arrays[f"profile__{name}__values"] = prof.values
    npz_path = out / "solution_arrays.npz"
    np.savez_compressed(npz_path, **arrays)

    manifest_path = out / "run_manifest.json"
    manifest_path.write_text(json.dumps(result.manifest, indent=2), encoding="utf-8")

    snapshot_path = out / "parameter_snapshot.json"
    snapshot_path.write_text(json.dumps(result.parameter_snapshot, indent=2), encoding="utf-8")

    profiles_meta = {
        name: {
            "coordinate_name": prof.coordinate_name,
            "times_s": prof.times_s,
            "note": prof.note,
            "metadata": prof.metadata,
        }
        for name, prof in result.extraction.profiles.items()
    }
    meta_path = out / "extraction_metadata.json"
    meta_path.write_text(
        json.dumps(
            {"availability": result.extraction.availability_report, "profiles": profiles_meta},
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "arrays": str(npz_path),
        "manifest": str(manifest_path),
        "parameter_snapshot": str(snapshot_path),
        "extraction_metadata": str(meta_path),
    }
