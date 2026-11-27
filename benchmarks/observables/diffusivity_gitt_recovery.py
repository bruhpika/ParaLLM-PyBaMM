#!/usr/bin/env python
"""Synthetic joint parameter recovery + profile likelihood at the §2.7 GITT protocol.

    .venv/bin/python benchmarks/observables/diffusivity_gitt_recovery.py \
        --config configs/v03/diffusivity_recovery.yaml

Purpose (docs/D_NEG_ACTION_DECISION.md gates 2 and 3): dry-run the machinery
that would identify ``Negative particle diffusivity [m2.s-1]`` from an
experimental GITT dataset, on **model-generated** data, at the protocol
specified in ``docs/EXPERIMENTAL_DATA_REQUIREMENTS.md`` §2.7. The point is to
know that the identification procedure works and what it costs *before* real
data exists.

What is fitted: three multiplicative scale factors
(``D_neg``, ``j0_neg``, ``D_e``) against the raw low-SOC GITT voltage series,
by weighted least squares, from several declared starting points. A profile
likelihood over ``D_neg`` (other two re-optimised at every grid point) tests
whether the parameter is bounded rather than merely stationary.

SYNTHETIC and diagnostic only:

* the "data" are model-generated with declared noise and a declared seed;
* the truth scale factors are study devices, not measurements;
* scientific rule 7: a successful recovery here is not identifiability proof
  for real data; rule 8: synthetic recovery is not experimental validation;
* rule 10: no calibration objective, registry record or dossier decision
  changes. The dossier action for this parameter stays ``MEASURE``.

All PyBaMM interaction goes through ``pybamm_engine/observables.py`` and the
parameter scaling device of ``diffusivity_multi_observable_fim.py``; nothing
assumes an API that the pinned PyBaMM does not provide.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pybamm_closed_loop.calibration.identifiability import (  # noqa: E402
    finite_difference_jacobian,
)
from pybamm_closed_loop.pybamm_engine.observables import (  # noqa: E402
    run_gitt_d,
    verified_api_signatures,
)

PINNED_PYBAM_VERSION = "26.8.0.0"
REPO_ROOT = Path(__file__).resolve().parents[2]
OBSERVABLES_BENCH = Path(__file__).resolve().parent / "diffusivity_multi_observable_fim.py"

LIMITATIONS = [
    "SYNTHETIC ONLY: the fitted data are model-generated with declared noise, not measured.",
    "Recovery at one declared truth point; it does not explore the parameter space or prove global identifiability.",
    "Only three parameters are free; function-valued parameters are perturbed by a constant multiplier (their functional form is assumed known).",
    "GITT pulse overpotential mixes transport with ohmic and kinetic contributions; this is not a pure solid-diffusion estimator.",
    "The profile likelihood is coarse (declared grid) and local: it bounds the parameter under this protocol and noise only. Crossings are linearly interpolated between grid points, so a convex profile's interval is slightly underestimated; refine the grid before quoting tight bounds.",
    "No calibration objective, registry record or dossier decision was changed.",
]


# --------------------------------------------------------------------------
# Shared helpers from the observable-augmented study (single source of truth)
# --------------------------------------------------------------------------
def _load_observables_module():
    spec = importlib.util.spec_from_file_location(
        "diffusivity_multi_observable_fim", OBSERVABLES_BENCH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Pure helpers (unit-tested without PyBaMM)
# --------------------------------------------------------------------------
def load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def validate_config(cfg: dict[str, Any]) -> None:
    """Refuse silently incomplete or post-hoc study designs."""
    for key in (
        "run_id",
        "model_name",
        "parameter_set",
        "parameters",
        "truth_scale_factors",
        "gitt_d",
        "noise_sigma_V",
        "seed",
        "optimizer",
        "multi_start",
        "recovery",
        "profile",
        "outputs",
    ):
        if key not in cfg:
            raise KeyError(f"config is missing required key {key!r}")
    labels = [str(p["label"]) for p in cfg["parameters"]]
    if len(set(labels)) != len(labels):
        raise ValueError(f"duplicate parameter labels {labels!r}")
    truth = cfg["truth_scale_factors"]
    if set(truth) != set(labels):
        raise ValueError(
            f"truth_scale_factors keys {sorted(truth)} must match parameter labels {labels}"
        )
    if any(float(v) <= 0 for v in truth.values()):
        raise ValueError("truth scale factors must be positive")
    if float(cfg["noise_sigma_V"]) <= 0:
        raise ValueError("noise_sigma_V must be positive")
    if int(cfg["seed"]) < 0:
        raise ValueError("seed must be non-negative")
    starts = [list(map(float, row)) for row in cfg["multi_start"]]
    if not starts:
        raise ValueError("multi_start must contain at least one starting point")
    for row in starts:
        if len(row) != len(labels):
            raise ValueError(f"multi_start row {row} must have {len(labels)} entries")
    lo, hi = (float(v) for v in cfg["optimizer"]["bounds"])
    if not lo < hi:
        raise ValueError("optimizer.bounds must be [low, high] with low < high")
    for row in starts:
        if any(v < lo or v > hi for v in row):
            raise ValueError(f"multi_start row {row} outside bounds {[lo, hi]}")
    grid = [float(v) for v in cfg["profile"]["grid"]]
    if len(grid) < 3:
        raise ValueError("profile.grid needs at least 3 points")
    if any(b - a <= 0 for a, b in zip(grid, grid[1:], strict=False)):
        raise ValueError("profile.grid must be strictly increasing")
    if str(cfg["profile"]["fixed_parameter"]) not in labels:
        raise ValueError("profile.fixed_parameter must be one of the parameter labels")
    if float(cfg["profile"]["delta_chi2_95"]) <= 0:
        raise ValueError("profile.delta_chi2_95 must be positive")
    if float(cfg["recovery"]["z_score_threshold"]) <= 0:
        raise ValueError("recovery.z_score_threshold must be positive")
    if float(cfg["recovery"]["max_estimate_spread_ratio"]) < 1.0:
        raise ValueError("recovery.max_estimate_spread_ratio must be >= 1")


def chi_square(residuals: np.ndarray) -> float:
    """sum(r^2) for residuals already divided by sigma."""
    r = np.asarray(residuals, dtype=float).reshape(-1)
    return float(r @ r)


def weighted_residual(predict: Callable[[np.ndarray], np.ndarray], data: np.ndarray,
                      sigma: float, x: np.ndarray) -> np.ndarray:
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    return (np.asarray(predict(x), dtype=float).reshape(-1) - data) / float(sigma)


def z_score(estimate: float, truth: float, standard_error: float) -> float:
    """(estimate - truth) / predicted SE in the same units as the estimate."""
    if not np.isfinite(standard_error) or standard_error <= 0:
        return float("inf")
    return float((float(estimate) - float(truth)) / float(standard_error))


def estimate_spread_ratio(estimates: list[float]) -> float:
    """max/min over multi-start estimates (all positive by the declared bounds)."""
    values = np.asarray(estimates, dtype=float)
    if values.size == 0 or np.any(values <= 0):
        raise ValueError("estimates must be non-empty and positive")
    return float(values.max() / values.min())


def recovery_status(z_scores: dict[str, float], spread_ratios: dict[str, float],
                    z_threshold: float, spread_threshold: float) -> dict[str, Any]:
    """Declared recovery rule: |z| <= threshold AND multi-start spread <= ratio."""
    per_parameter = {}
    recovered = True
    for name in sorted(z_scores):
        ok = bool(
            abs(z_scores[name]) <= z_threshold
            and spread_ratios[name] <= spread_threshold
        )
        per_parameter[name] = {
            "z_score": float(z_scores[name]),
            "multi_start_spread_ratio": float(spread_ratios[name]),
            "recovered": ok,
        }
        recovered = recovered and ok
    return {
        "recovered": bool(recovered),
        "per_parameter": per_parameter,
        "rule": (
            f"|z| <= {z_threshold:g} against the predicted SE and multi-start "
            f"estimate spread ratio <= {spread_threshold:g}, for every parameter"
        ),
    }


def _crossing(x_left: float, y_left: float, x_right: float, y_right: float,
              threshold: float) -> float:
    """Linear interpolation of the threshold crossing between two grid points."""
    if y_right == y_left:
        return float(x_left)
    return float(
        x_left
        + (threshold - y_left) * (x_right - x_left) / (y_right - y_left)
    )


def profile_verdict(grid: np.ndarray, delta_costs: np.ndarray,
                    delta_chi2: float) -> dict[str, Any]:
    """Is the profile closed at ``delta_chi2``, and where are the crossings?

    A profile is closed when its minimum is interior and the cost rises above
    ``min + delta_chi2`` on *both* sides within the declared grid. The 95 %
    interval is the pair of linearly interpolated crossings between grid
    points; a side without a crossing is unbounded (reported as ``None``).

    Grid resolution matters: for a convex profile the linearly interpolated
    interval is slightly *narrower* than the continuous one. Refine the grid
    near the crossings before quoting a tight interval.
    """
    grid = np.asarray(grid, dtype=float).reshape(-1)
    delta = np.asarray(delta_costs, dtype=float).reshape(-1)
    if grid.size != delta.size or grid.size < 3:
        raise ValueError("grid and delta_costs must have the same length >= 3")
    if np.any(np.diff(grid) <= 0):
        raise ValueError("grid must be strictly increasing")
    if np.any(delta < -1e-9):
        raise ValueError("delta_costs must be >= 0")
    k = int(np.argmin(delta))
    lo = None
    for i in range(k - 1, -1, -1):
        if delta[i] > delta_chi2:
            lo = _crossing(grid[i], delta[i], grid[i + 1], delta[i + 1], delta_chi2)
            break
    hi = None
    for i in range(k + 1, grid.size):
        if delta[i] > delta_chi2:
            hi = _crossing(grid[i - 1], delta[i - 1], grid[i], delta[i], delta_chi2)
            break
    closed = bool(lo is not None and hi is not None)
    return {
        "closed_at_delta_chi2": closed,
        "ci95": [lo, hi] if closed else None,
        "unbounded_sides": [
            name
            for name, value in (("low", lo), ("high", hi))
            if value is None
        ],
        "minimum_grid_value": float(grid[k]),
        "minimum_delta": float(delta[k]),
        "rule": (
            f"closed iff the minimum is interior and the cost exceeds the minimum "
            f"by {delta_chi2:g} on both sides of the declared grid"
        ),
    }


# --------------------------------------------------------------------------
# PyBaMM-backed predictors and fits
# --------------------------------------------------------------------------
def raw_gitt_voltage(pv: Any, spec: dict[str, Any]) -> np.ndarray:
    """Raw sampled GITT voltage series for the declared protocol."""
    result = run_gitt_d(
        pv,
        current_A=float(spec["current_A"]),
        pulse_duration_s=float(spec["pulse_duration_s"]),
        rest_duration_s=float(spec["rest_duration_s"]),
        n_pulses=int(spec["n_pulses"]),
        period_s=float(spec["period_s"]),
        model_name=str(spec["model_name"]),
        initial_soc=spec.get("initial_soc"),
    )
    return np.asarray(result.voltage_V, dtype=float).reshape(-1)


def make_predictor(cfg: dict[str, Any], obs_module: Any) -> Callable[[np.ndarray], np.ndarray]:
    """scale vector -> raw GITT voltage, on the same scaling device as the FIM study."""
    parameter_set = str(cfg["parameter_set"])
    names = [str(p["name"]) for p in cfg["parameters"]]
    spec = cfg["gitt_d"]

    def predict(scales: np.ndarray) -> np.ndarray:
        pv = obs_module.scaled_parameter_values_multi(
            parameter_set, names, np.asarray(scales, dtype=float)
        )
        return raw_gitt_voltage(pv, spec)

    return predict


def run_fit(predict: Callable[[np.ndarray], np.ndarray], data: np.ndarray,
            sigma: float, x0: np.ndarray, bounds: tuple[float, float],
            method: str, max_nfev: int) -> dict[str, Any]:
    """Weighted least squares over the declared scale factors."""
    from scipy.optimize import least_squares

    lo, hi = float(bounds[0]), float(bounds[1])
    result = least_squares(
        lambda x: weighted_residual(predict, data, sigma, x),
        np.asarray(x0, dtype=float),
        bounds=(lo, hi),
        method=str(method),
        max_nfev=int(max_nfev),
    )
    return {
        "start": np.asarray(x0, dtype=float).tolist(),
        "estimate": result.x.tolist(),
        "chi_square": chi_square(result.fun),
        "nfev": int(result.nfev),
        "success": bool(result.success),
        "status": int(result.status),
        "message": str(result.message),
    }


def parameter_standard_errors(fim: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-parameter Cramér–Rao SEs with explicit unconstrained flags.

    For a rank-deficient FIM the pseudo-inverse minimum-norm variance is
    meaningless for any parameter that touches the null space (it can even be
    zero, i.e. fake infinite precision). Each parameter whose unit vector has a
    non-negligible component in the null space is reported as ``inf`` with an
    ``unconstrained`` flag; the others keep their pseudo-inverse SE. This is
    stricter than reporting a small number and more informative than declaring
    every parameter unconstrained.
    """
    fim = np.asarray(fim, dtype=float)
    if fim.ndim != 2 or fim.shape[0] != fim.shape[1]:
        raise ValueError(f"FIM must be square, got {fim.shape}")
    n = fim.shape[0]
    eigenvalues, eigenvectors = np.linalg.eigh(fim)
    reference = float(np.max(np.abs(eigenvalues))) if n else 0.0
    tolerance = max(reference, 1.0) * 1e-10
    null_vectors = eigenvectors[:, eigenvalues <= tolerance]
    unconstrained = (
        np.abs(null_vectors).max(axis=1) > 1e-8 if null_vectors.size else np.zeros(n, bool)
    )
    covariance = np.linalg.pinv(fim)
    diagonal = np.clip(np.diag(covariance), 0.0, None)
    se = np.full(n, np.inf, dtype=float)
    for index in range(n):
        if not unconstrained[index] and diagonal[index] > 0:
            se[index] = float(np.sqrt(diagonal[index]))
    return se, unconstrained


def predicted_standard_errors(predict: Callable[[np.ndarray], np.ndarray],
                              truth: np.ndarray, sigma: float,
                              rel_step: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cramér–Rao SEs at the data-generating truth, and the FIM correlation.

    SEs are in absolute scale-factor units. Parameters touching a FIM null
    space get ``inf`` and an ``unconstrained`` flag (see
    :func:`parameter_standard_errors`): a parameter the data cannot constrain
    must not be reported with finite precision.
    """
    jacobian = finite_difference_jacobian(predict, truth, rel_step=float(rel_step))
    fim = (jacobian.T @ jacobian) / float(sigma) ** 2
    se, unconstrained = parameter_standard_errors(fim)
    scale = np.sqrt(np.clip(np.diag(np.linalg.pinv(fim)), 0.0, None))
    covariance = np.linalg.pinv(fim)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = covariance / np.outer(scale, scale)
    return se, np.nan_to_num(corr, nan=0.0), unconstrained


def run_recovery(config_path: Path) -> dict[str, Any]:
    """Generate the synthetic dataset, fit it, profile D_neg, write artifacts."""
    import pybamm

    if pybamm.__version__ != PINNED_PYBAM_VERSION:
        raise RuntimeError(
            f"pinned pybamm {PINNED_PYBAM_VERSION} required, found {pybamm.__version__}"
        )
    obs_module = _load_observables_module()

    cfg = load_config(config_path)
    validate_config(cfg)
    labels = [str(p["label"]) for p in cfg["parameters"]]
    truth = np.array([float(cfg["truth_scale_factors"][label]) for label in labels])
    sigma = float(cfg["noise_sigma_V"])
    seed = int(cfg["seed"])
    rel_step = float(cfg.get("rel_perturbation", 0.02))
    bounds = tuple(float(v) for v in cfg["optimizer"]["bounds"])
    method = str(cfg["optimizer"]["method"])
    max_nfev = int(cfg["optimizer"]["max_nfev"])
    starts = [np.array([float(v) for v in row]) for row in cfg["multi_start"]]

    t0 = time.perf_counter()
    predict = make_predictor(cfg, obs_module)

    # ---- synthetic dataset (declared truth + declared noise + declared seed)
    rng = np.random.default_rng(seed)
    truth_signal = predict(truth)
    data = truth_signal + rng.normal(0.0, sigma, size=truth_signal.shape)

    # ---- predicted (truth-FIM) standard errors and correlations -----------
    predicted_se, predicted_corr, unconstrained = predicted_standard_errors(
        predict, truth, sigma, rel_step
    )

    # ---- multi-start joint fit -------------------------------------------
    fits = [
        run_fit(predict, data, sigma, x0, bounds, method, max_nfev) for x0 in starts
    ]
    best = min(fits, key=lambda rep: rep["chi_square"])
    estimates = np.array(best["estimate"], dtype=float)

    z_scores = {
        label: z_score(estimates[index], truth[index], predicted_se[index])
        for index, label in enumerate(labels)
    }
    spread = {
        label: estimate_spread_ratio([rep["estimate"][index] for rep in fits])
        for index, label in enumerate(labels)
    }
    recovery = recovery_status(
        z_scores,
        spread,
        float(cfg["recovery"]["z_score_threshold"]),
        float(cfg["recovery"]["max_estimate_spread_ratio"]),
    )
    recovery["truth_scale_factors"] = {
        label: float(truth[index]) for index, label in enumerate(labels)
    }
    recovery["estimate"] = {
        label: float(estimates[index]) for index, label in enumerate(labels)
    }
    recovery["predicted_standard_error"] = {
        label: float(predicted_se[index]) for index, label in enumerate(labels)
    }
    recovery["unconstrained_parameters"] = [
        label for index, label in enumerate(labels) if unconstrained[index]
    ]
    recovery["unconstrained_note"] = (
        "Parameters touching a null direction of the truth FIM cannot be "
        "constrained by this dataset; their standard error is reported as inf "
        "and they are never counted as recovered."
    )
    recovery["predicted_correlation"] = {
        row: {col: float(predicted_corr[i, j]) for j, col in enumerate(labels)}
        for i, row in enumerate(labels)
    }

    # ---- profile likelihood over the declared parameter -------------------
    profile_cfg = cfg["profile"]
    grid = np.array([float(v) for v in profile_cfg["grid"]])
    fixed_label = str(profile_cfg["fixed_parameter"])
    fixed_index = labels.index(fixed_label)
    free_indices = [i for i in range(len(labels)) if i != fixed_index]
    costs: list[float] = []
    free_estimates: list[list[float]] = []
    for value in grid:
        def predict_pinned(scales_free: np.ndarray,
                           fixed_value: float = float(value)) -> np.ndarray:
            full = np.empty(len(labels), dtype=float)
            full[fixed_index] = fixed_value
            full[free_indices] = np.asarray(scales_free, dtype=float)
            return predict(full)

        # Warm-start the free parameters at the best joint estimate.
        rep = run_fit(
            predict_pinned,
            data,
            sigma,
            estimates[free_indices],
            bounds,
            method,
            max_nfev,
        )
        costs.append(float(rep["chi_square"]))
        free_estimates.append([float(v) for v in rep["estimate"]])
    min_cost = float(min(costs))
    delta = [cost - min_cost for cost in costs]
    profile = profile_verdict(grid, np.asarray(delta), float(profile_cfg["delta_chi2_95"]))
    profile.update(
        {
            "fixed_parameter": fixed_label,
            "free_parameters": [labels[i] for i in free_indices],
            "grid": grid.tolist(),
            "chi_square": costs,
            "delta_chi_square": delta,
            "free_estimates": free_estimates,
            "delta_chi2_95": float(profile_cfg["delta_chi2_95"]),
        }
    )

    out_report = REPO_ROOT / str(cfg["outputs"]["report"])
    out_summary = REPO_ROOT / str(cfg["outputs"]["summary"])
    out_report.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "label": "SYNTHETIC JOINT PARAMETER RECOVERY + PROFILE LIKELIHOOD",
        "run_id": cfg["run_id"],
        "description": cfg.get("description", ""),
        "synthetic_only": True,
        "diagnostic_only": True,
        "decision_changed": False,
        "registry_write": False,
        "parameter_set": str(cfg["parameter_set"]),
        "model_name": str(cfg["model_name"]),
        "parameters": [
            {"label": str(p["label"]), "name": str(p["name"])} for p in cfg["parameters"]
        ],
        "protocol": dict(cfg["gitt_d"]),
        "noise_sigma_V": sigma,
        "seed": seed,
        "rel_perturbation": rel_step,
        "optimizer": {
            "method": method,
            "max_nfev": max_nfev,
            "bounds": list(bounds),
            "multi_start": [row.tolist() for row in starts],
        },
        "n_data_points": int(data.size),
        "recovery": recovery,
        "multi_start_fits": fits,
        "profile_likelihood": profile,
        "environment": {
            "python": platform.python_version(),
            "pybamm": pybamm.__version__,
            "numpy": np.__version__,
        },
        "verified_api_signatures": verified_api_signatures(),
        "config_sha256": _sha256(Path(config_path)),
        "limitations": LIMITATIONS,
        "scientific_note": (
            "Synthetic dry-run of the identification machinery only. A successful "
            "recovery does not prove identifiability on real data (rule 7) and is "
            "not experimental validation (rule 8). The dossier action for this "
            "parameter remains MEASURE; gates 2/3 of docs/D_NEG_ACTION_DECISION.md "
            "must be re-run on a real dataset before any decision change (rule 10)."
        ),
        "runtime_s": time.perf_counter() - t0,
    }
    out_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_summary.write_text(_render_summary(report), encoding="utf-8")
    return report


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Summary rendering
# --------------------------------------------------------------------------
def _fmt(value: float) -> str:
    if value is None:
        return "n/a"
    value = float(value)
    if not np.isfinite(value):
        return "inf"
    return f"{value:.4g}"


def _render_summary(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Synthetic joint parameter recovery + profile likelihood")
    lines.append("")
    lines.append(
        f"**{report['label']}** — synthetic dry-run; no parameter decision changed."
    )
    lines.append("")
    lines.append(
        f"Parameter set `{report['parameter_set']}` · model `{report['model_name']}` "
        f"· seed {report['seed']} · noise σ = {_fmt(report['noise_sigma_V'])} V · "
        f"{report['n_data_points']} data points"
    )
    lines.append("")
    protocol = report["protocol"]
    lines.append("## Protocol (§2.7)")
    lines.append("")
    lines.append(
        f"- start SOC {protocol.get('initial_soc')}, current "
        f"{_fmt(protocol.get('current_A'))} A, {_fmt(protocol.get('pulse_duration_s'))} s "
        f"pulse / {_fmt(protocol.get('rest_duration_s'))} s rest, "
        f"{protocol.get('n_pulses')} pulses"
    )
    lines.append("")
    lines.append("## Joint recovery (3 scale factors free)")
    lines.append("")
    lines.append(
        "| parameter | truth | estimate | predicted SE | z | multi-start spread | recovered |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    recovery = report["recovery"]
    for name, entry in recovery["per_parameter"].items():
        lines.append(
            f"| `{name}` | {_fmt(recovery['truth_scale_factors'][name])} | "
            f"{_fmt(recovery['estimate'][name])} | "
            f"{_fmt(recovery['predicted_standard_error'][name])} | "
            f"{_fmt(entry['z_score'])} | {_fmt(entry['multi_start_spread_ratio'])} | "
            f"**{entry['recovered']}** |"
        )
    lines.append("")
    lines.append(f"Rule: {recovery['rule']}")
    lines.append("")
    lines.append(f"Overall recovery: **{recovery['recovered']}**")
    lines.append("")
    lines.append("### Multi-start fits")
    lines.append("")
    lines.append("| start | estimate | χ² | nfev | converged |")
    lines.append("|---|---|---:|---:|---|")
    for fit in report["multi_start_fits"]:
        estimate = ", ".join(_fmt(v) for v in fit["estimate"])
        lines.append(
            f"| {fit['start']} | [{estimate}] | {_fmt(fit['chi_square'])} | "
            f"{fit['nfev']} | {fit['success']} |"
        )
    lines.append("")
    profile = report["profile_likelihood"]
    lines.append(f"## Profile likelihood over `{profile['fixed_parameter']}`")
    lines.append("")
    lines.append("| grid | χ² | Δχ² | free estimates |")
    lines.append("|---:|---:|---:|---|")
    for value, cost, delta, free in zip(
        profile["grid"],
        profile["chi_square"],
        profile["delta_chi_square"],
        profile["free_estimates"],
        strict=True,
    ):
        lines.append(
            f"| {_fmt(value)} | {_fmt(cost)} | {_fmt(delta)} | "
            f"[{', '.join(_fmt(v) for v in free)}] |"
        )
    lines.append("")
    lines.append(
        f"Δχ² threshold (95 %, 1 dof): {_fmt(profile['delta_chi2_95'])}. "
        f"Minimum at {_fmt(profile['minimum_grid_value'])}."
    )
    lines.append("")
    if profile["closed_at_delta_chi2"]:
        lines.append(
            f"Profile is **closed** at the declared threshold: 95 % interval "
            f"[{_fmt(profile['ci95'][0])}, {_fmt(profile['ci95'][1])}] in scale-factor units."
        )
    else:
        lines.append(
            "Profile is **not closed** at the declared threshold: unbounded on "
            f"{', '.join(profile['unbounded_sides'])} within the declared grid."
        )
    lines.append("")
    lines.append(f"Rule: {profile['rule']}")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    for item in report["limitations"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append(report["scientific_note"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(REPO_ROOT / "configs/v03/diffusivity_recovery.yaml"),
    )
    args = parser.parse_args()
    report = run_recovery(Path(args.config))
    recovery = report["recovery"]
    profile = report["profile_likelihood"]
    print(f"wrote {report['run_id']} synthetic recovery study")
    print(f"  recovery: {recovery['recovered']}")
    for name, entry in recovery["per_parameter"].items():
        print(
            f"    {name:8s} truth {_fmt(recovery['truth_scale_factors'][name])} "
            f"est {_fmt(recovery['estimate'][name])} "
            f"SE {_fmt(recovery['predicted_standard_error'][name])} "
            f"z {_fmt(entry['z_score'])} recovered={entry['recovered']}"
        )
    ci = profile["ci95"]
    print(
        f"  profile closed: {profile['closed_at_delta_chi2']} "
        f"ci95=[{_fmt(ci[0]) if ci else None}, {_fmt(ci[1]) if ci else None}]"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
