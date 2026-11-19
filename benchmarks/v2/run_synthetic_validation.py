#!/usr/bin/env python
"""V2.4 synthetic end-to-end validation (SYNTHETIC — never experimental).

Protocol-faithful synthetic experiment with deliberate mismatch:

  1. assemble decisions from the real registry + the V2.3 observability join;
  2. build a deliberately mismatched synthetic ground truth;
  3. generate seeded synthetic data at 0.5C / 1C / 2C;
  4. baseline: validate the assembled parameter set on held-out rates;
  5. positive control: fit the CALIBRATE-action observable pair on 1C and
     re-validate;
  6. negative control: fit the unobservable FIX/MEASURE parameter on 1C
     (violating the assembly decision) and re-validate.

Acceptance: held-out-rate error vs baseline is reported for both controls and
the negative control reproduces the prediction — fitting an unobservable
parameter does not improve held-out validation while the observable pair does.
Every artifact is labelled SYNTHETIC (scientific rule 8): this is not
experimental validation and does not prove identifiability (rule 7).

Run (pybop + pybamm required):
    .venv-ecosystem312/bin/python benchmarks/v2/run_synthetic_validation.py \
        --out results/v2/synthetic_validation

Hardened mismatch mode (SYNTHETIC; removes the inverse crime) writes to a new
directory under results/v2/:
    .venv-ecosystem312/bin/python benchmarks/v2/run_synthetic_validation.py \
        --mismatch
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pybamm_closed_loop.assembly import (  # noqa: E402
    Rubric,
    assemble,
    load_observability,
)
from pybamm_closed_loop.cli import load_target  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = REPO_ROOT / "data/registry/registry.json"
DEFAULT_TARGET = REPO_ROOT / "configs/v2/target_lgm50.yaml"
DEFAULT_P2 = REPO_ROOT / "results/p2"
DEFAULT_OUT = REPO_ROOT / "results/v2/synthetic_validation"
MISMATCH_OUT = REPO_ROOT / "results/v2/synthetic_validation_mismatch"

TRAIN_RATE = "1C"
HELD_OUT_RATES = ("0.5C", "2C")
ALL_RATES = ("0.5C", "1C", "2C")
DEFAULT_STEPS = {
    "0.5C": ["Discharge at 0.5C for 120 s"],
    "1C": ["Discharge at 1C for 60 s"],
    "2C": ["Discharge at 2C for 30 s"],
}

# Deliberately mismatched synthetic ground truth (labelled synthetic):
# the assembled literature set (Chen2020 / registry) differs from the truth by
# these known offsets, which is exactly the mismatch the calibration step
# tries to correct for the observable pair and cannot for the unobservable one.
TRUTH_VALUES = {
    "Negative electrode active material volume fraction": 0.72,
    "Positive electrode active material volume fraction": 0.63,
    "Negative particle diffusivity [m2.s-1]": 5.0e-14,
}

# canonical id -> PyBaMM parameter name for the experiment's three parameters
START_MAP = {
    "neg_electrode_active_material_volume_fraction": (
        "Negative electrode active material volume fraction"
    ),
    "pos_electrode_active_material_volume_fraction": (
        "Positive electrode active material volume fraction"
    ),
    "neg_particle_diffusivity": "Negative particle diffusivity [m2.s-1]",
}
POSITIVE_FIT_CANDS = {
    "neg_electrode_active_material_volume_fraction",
    "pos_electrode_active_material_volume_fraction",
}
NEGATIVE_CONTROL = "neg_particle_diffusivity"

LABEL_SYNTHETIC = (
    "SYNTHETIC — deliberately mismatched ground truth and synthetic "
    "measurements; not experimental validation (scientific rule 8)"
)

# --- Hardened mismatch mode (still SYNTHETIC) -----------------------------
# All perturbation inputs are recorded values or deterministic multiples of
# them; none is a claim about a real cell. The base value of the never-fitted
# perturbation comes from data/registry/registry.json (Chen2020 4e-15 m2.s-1).
UNFITTED_CANONICAL_ID = "pos_particle_diffusivity"
UNFITTED_PARAM = "Positive particle diffusivity [m2.s-1]"
UNFITTED_FACTOR = 1.10
MISMATCH_VAR_PTS = {"x_n": 12, "x_s": 12, "x_p": 12, "r_n": 10, "r_p": 10}
MISMATCH_SOLVER = "casadi-safe"
MISMATCH_RTOL = 1e-6
MISMATCH_ATOL = 1e-8
# 1e-3 V: the recorded V2.4 setting. 2e-3 V: recorded in configs/p2/*.yaml
# and results/p2/recovery_volume_fractions_single_1C/report.json.
NOISE_LEVELS = (1e-3, 2e-3)
TRUTH_SCALES = (0.75, 1.0, 1.25)


def voltage_rmse(
    t_data: np.ndarray, v_data: np.ndarray, t_pred: np.ndarray, v_pred: np.ndarray
) -> float:
    """RMSE [V] of a predicted voltage trace on the measurement time grid."""
    t_data = np.asarray(t_data, dtype=float)
    v_data = np.asarray(v_data, dtype=float)
    t_pred = np.asarray(t_pred, dtype=float)
    v_pred = np.asarray(v_pred, dtype=float)
    if t_pred.size < 2 or t_data.size < 2:
        return float("nan")
    v_interp = np.interp(t_data, t_pred, v_pred)
    return float(np.sqrt(np.mean((v_data - v_interp) ** 2)))


def _mean(errors: dict[str, float]) -> float:
    vals = [v for v in errors.values() if v == v]
    return float(np.mean(vals)) if vals else float("nan")


def simulate_voltage(pv, steps: list[str], model_name: str):
    """Simulate one fixed-duration protocol; returns (t, V)."""
    import pybamm

    model = getattr(pybamm.lithium_ion, model_name)()
    sim = pybamm.Simulation(
        model, parameter_values=pv, experiment=pybamm.Experiment(list(steps))
    )
    solution = sim.solve()
    return (
        np.asarray(solution.t, dtype=float),
        np.asarray(solution["Terminal voltage [V]"](solution.t), dtype=float),
    )


def _pv_with(values: dict[str, float]):
    """Chen2020 parameter set with the given values applied."""
    import pybamm

    pv = pybamm.ParameterValues("Chen2020")
    for name, value in values.items():
        pv.update({name: float(value)})
    return pv


def _dataset_arrays(ds) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.asarray(ds.data["Time [s]"], dtype=float),
        np.asarray(ds.data["Voltage [V]"], dtype=float),
    )


def _versions() -> dict[str, str]:
    out: dict[str, str] = {}
    for pkg in ("pybamm", "pybop", "numpy", "scipy"):
        try:
            mod = __import__(pkg)
            out[pkg] = getattr(mod, "__version__", "unknown")
        except Exception:
            out[pkg] = "unavailable"
    return out


def _mismatch_solver():
    """A different DAE solver with tighter tolerances than the nominal IDAKLU."""
    import pybamm

    return pybamm.CasadiSolver(
        mode="safe", rtol=MISMATCH_RTOL, atol=MISMATCH_ATOL
    )


def scaled_truth(start_values: dict[str, float], scale: float) -> dict[str, float]:
    """Drawn ground truth: scale the recorded offset from the assembled start.

    ``scale=1.0`` reproduces the recorded V2.4 truth exactly; other scales stay
    on the segment between the assembled set and a bounded extrapolation.
    Every input is a recorded value (registry / existing TRUTH_VALUES).
    """
    return {
        name: float(start_values[name] + scale * (base - start_values[name]))
        for name, base in TRUTH_VALUES.items()
    }


def _unfitted_perturbation(records: list[dict]) -> tuple[float, float]:
    """Base value and perturbed value of a parameter neither control fits."""
    matches = [r for r in records if r.get("canonical_id") == UNFITTED_CANONICAL_ID]
    if len(matches) != 1:
        raise SystemExit(f"expected one registry record for {UNFITTED_CANONICAL_ID}")
    base = float(matches[0]["value"])
    import pybamm

    if UNFITTED_PARAM not in pybamm.ParameterValues("Chen2020").keys():
        raise SystemExit(f"{UNFITTED_PARAM} is not a PyBaMM Chen2020 parameter")
    return base, base * UNFITTED_FACTOR


def ci_coverage(fit_report: dict, truth_values: dict[str, float]) -> dict:
    """95% CI coverage when a fit reports uncertainties; explicit N/A otherwise.

    PyBOP 26.10's SciPyMinimize/L-BFGS-B result exposes no covariance or
    standard errors, so the current runs report ``available: false`` rather
    than inventing an uncertainty.
    """
    se = fit_report.get("standard_errors") or (
        fit_report.get("uncertainty") or {}
    ).get("standard_errors")
    if not se:
        return {
            "available": False,
            "reason": (
                "PyBOP 26.10 SciPyMinimize/L-BFGS-B result exposes no "
                "covariance or standard errors; no CI was computed"
            ),
        }
    covered = total = 0
    for i, p in enumerate(fit_report["parameters"]):
        name = p["name"]
        sigma = se.get(name) if isinstance(se, dict) else se[i]
        truth = truth_values.get(name)
        if sigma is None or truth is None:
            continue
        lo, hi = float(p["estimate"]) - 1.96 * sigma, float(p["estimate"]) + 1.96 * sigma
        total += 1
        covered += lo <= float(truth) <= hi
    return {
        "available": True,
        "n_parameters": total,
        "n_covered": int(covered),
        "coverage": (covered / total) if total else None,
    }


def run_experiment(
    registry: Path = DEFAULT_REGISTRY,
    target_path: Path = DEFAULT_TARGET,
    p2_dir: Path = DEFAULT_P2,
    *,
    out_dir: Path | None = None,
    model_name: str = "DFN",
    steps: dict[str, list[str]] | None = None,
    train_rate: str = TRAIN_RATE,
    held_out_rates: tuple[str, ...] = HELD_OUT_RATES,
    noise_sigma_V: float = 1e-3,
    seed: int = 20261117,
    maxiter: int = 40,
    truth_values: dict[str, float] | None = None,
    mismatch: bool = False,
    truth_scale: float = 1.0,
) -> dict:
    """Run the V2.4 synthetic end-to-end validation experiment.

    Returns the report payload; writes report.json / summary.md under
    ``out_dir`` when given. Raises SystemExit when the assembly layer does not
    agree with the experiment's expected role assignment (never silently).
    """
    from pybamm_closed_loop.calibration.fitting import (
        FitParameter,
        FitSpec,
        build_problem,
        run_fit_with_result,
    )
    from pybamm_closed_loop.calibration.synthetic import (
        SyntheticCondition,
        SyntheticSpec,
        generate_datasets,
    )

    steps = steps or DEFAULT_STEPS

    # --- 1. assemble decisions (real registry + V2.3 join) ----------------
    records = json.loads(Path(registry).read_text(encoding="utf-8"))
    target = load_target(Path(target_path))
    observability = load_observability(Path(p2_dir), records)
    asm = assemble(records, target, Rubric("rubric-v2"), observability=observability)
    by_id = {d["parameter"]: d for d in asm.dossiers}
    for cid in POSITIVE_FIT_CANDS | {NEGATIVE_CONTROL}:
        if cid not in by_id:
            raise SystemExit(f"experiment parameter {cid!r} missing from the registry")
    for cid in POSITIVE_FIT_CANDS:
        action = (by_id[cid].get("identifiability") or {}).get("action")
        if action != "CALIBRATE":
            raise SystemExit(
                f"{cid}: expected action CALIBRATE from the observability join, "
                f"got {action!r}"
            )
    control_action = (by_id[NEGATIVE_CONTROL].get("identifiability") or {}).get(
        "action"
    )
    if control_action not in ("FIX", "MEASURE"):
        raise SystemExit(
            f"{NEGATIVE_CONTROL}: expected action FIX/MEASURE from the "
            f"observability join, got {control_action!r}"
        )
    start_values: dict[str, float] = {}
    for cid, pname in START_MAP.items():
        value = by_id[cid]["selected"]["value"]
        if value is None:
            raise SystemExit(f"{cid}: assembly produced no selected value (REVIEW)")
        start_values[pname] = float(value)

    # --- 2. synthetic truth + 3. synthetic data ---------------------------
    # Mismatch mode: several drawn truths (scaled from recorded offsets), a
    # perturbed solver/tolerance/mesh for data generation, and a small change
    # to a parameter that neither control fits. Fits always use the nominal
    # model (default solver/mesh) via build_problem below.
    mismatch_info: dict = {"enabled": False}
    if mismatch:
        unfit_base, unfit_perturbed = _unfitted_perturbation(records)
        truth = scaled_truth(start_values, truth_scale)
        truth = {**truth, UNFITTED_PARAM: unfit_perturbed}
        mismatch_info = {
            "enabled": True,
            "truth_scale": float(truth_scale),
            "generation_solver": MISMATCH_SOLVER,
            "generation_rtol": MISMATCH_RTOL,
            "generation_atol": MISMATCH_ATOL,
            "generation_var_pts": dict(MISMATCH_VAR_PTS),
            "unfitted_parameter": UNFITTED_PARAM,
            "unfitted_base_value": unfit_base,
            "unfitted_perturbed_value": unfit_perturbed,
            "unfitted_factor": UNFITTED_FACTOR,
            "nominal_solver": "pybamm default IDAKLU (rtol=1e-4, atol=1e-6)",
            "fit_uses_nominal_model": True,
        }
    else:
        truth = dict(TRUTH_VALUES if truth_values is None else truth_values)

    truth_spec = SyntheticSpec(
        parameter_set="Chen2020",
        model_name=model_name,
        true_values=truth,
        conditions=[
            SyntheticCondition(name=rate, steps=steps[rate]) for rate in ALL_RATES
        ],
        noise_sigma_V=noise_sigma_V,
        seed=seed,
        description="V2.4 synthetic validation ground truth (deliberately mismatched)",
        solver=_mismatch_solver() if mismatch else None,
        var_pts=dict(MISMATCH_VAR_PTS) if mismatch else None,
    )
    truth_spec.validate()
    data = {name: ds for name, ds, _ in generate_datasets(truth_spec)}

    def held_out_errors(pv) -> dict[str, float]:
        errors: dict[str, float] = {}
        for rate in held_out_rates:
            t_d, v_d = _dataset_arrays(data[rate])
            t_p, v_p = simulate_voltage(pv, steps[rate], model_name)
            errors[rate] = voltage_rmse(t_d, v_d, t_p, v_p)
        return errors

    # --- 4. baseline: assembled set on held-out rates ---------------------
    baseline_errors = held_out_errors(_pv_with(start_values))

    # --- 5. positive control: fit the observable CALIBRATE pair on 1C -----
    pos_names = [START_MAP[cid] for cid in sorted(POSITIVE_FIT_CANDS)]
    fit_pos_spec = FitSpec(
        parameter_set="Chen2020",
        model_name=model_name,
        fit_parameters=[
            FitParameter(
                name=name,
                initial_value=start_values[name],
                bounds=(0.4, 0.95) if name.startswith("Negative") else (0.3, 0.85),
            )
            for name in pos_names
        ],
        maxiter=maxiter,
        description=(
            "V2.4 positive control: observable CALIBRATE-action pair "
            "(electrode volume fractions) fitted on 1C only"
        ),
    )
    pos_problem, _ = build_problem([(train_rate, data[train_rate])], fit_pos_spec)
    fit_pos_report, _ = run_fit_with_result(
        pos_problem, fit_pos_spec, truth=truth
    )
    fitted_pos = {p["name"]: float(p["estimate"]) for p in fit_pos_report["parameters"]}
    positive_errors = held_out_errors(_pv_with({**start_values, **fitted_pos}))

    # --- 6. negative control: fit the unobservable FIX/MEASURE param -----
    neg_name = START_MAP[NEGATIVE_CONTROL]
    fit_neg_spec = FitSpec(
        parameter_set="Chen2020",
        model_name=model_name,
        fit_parameters=[
            FitParameter(
                name=neg_name,
                initial_value=start_values[neg_name],
                bounds=(0.01 * start_values[neg_name], 100.0 * start_values[neg_name]),
            )
        ],
        maxiter=maxiter,
        description=(
            "V2.4 negative control: unobservable parameter (FIX/MEASURE "
            "decision) fitted on 1C anyway, violating the assembly decision"
        ),
    )
    neg_problem, _ = build_problem([(train_rate, data[train_rate])], fit_neg_spec)
    fit_neg_report, _ = run_fit_with_result(
        neg_problem, fit_neg_spec, truth={neg_name: truth[neg_name]}
    )
    fitted_neg = {p["name"]: float(p["estimate"]) for p in fit_neg_report["parameters"]}
    negative_errors = held_out_errors(_pv_with({**start_values, **fitted_neg}))

    # --- 7. report: held-out error vs baseline + predicted pattern --------
    base_mean = _mean(baseline_errors)
    pos_mean = _mean(positive_errors)
    neg_mean = _mean(negative_errors)
    tolerance = 0.99  # 1 % relative, to absorb noise-level differences
    positive_improves = pos_mean < base_mean * tolerance
    negative_improves = neg_mean < base_mean * tolerance
    prediction_reproduced = positive_improves and not negative_improves

    payload: dict = {
        "run_id": "synthetic_validation_v2.4",
        "label": LABEL_SYNTHETIC,
        "generated": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "train_rate": train_rate,
            "held_out_rates": list(held_out_rates),
            "all_rates": list(ALL_RATES),
            "steps": {k: list(v) for k, v in steps.items()},
            "model_name": model_name,
            "noise_sigma_V": noise_sigma_V,
            "seed": seed,
            "maxiter": maxiter,
            "relative_tolerance": 1.0 - tolerance,
        },
        "mismatch": mismatch_info,
        "assembled": {
            "target": target.to_dict(),
            "rubric_version": "rubric-v2",
            "action_matrix": asm.action_matrix(),
            "start_values": start_values,
            "experiment_roles": {
                "positive_fit": sorted(POSITIVE_FIT_CANDS),
                "positive_fit_action": "CALIBRATE",
                "negative_control": NEGATIVE_CONTROL,
                "negative_control_action": control_action,
            },
        },
        "truth": {
            "label": "synthetic deliberately mismatched (see LABEL_SYNTHETIC)",
            "values": truth,
        },
        "baseline": {
            "held_out_errors_V": baseline_errors,
            "mean_held_out_error_V": base_mean,
            "note": "assembled literature set, no calibration",
        },
        "positive_control": {
            "fit": fit_pos_report,
            "fitted_values": fitted_pos,
            "held_out_errors_V": positive_errors,
            "mean_held_out_error_V": pos_mean,
            "ci_coverage": ci_coverage(fit_pos_report, truth),
        },
        "negative_control": {
            "fit": fit_neg_report,
            "fitted_values": fitted_neg,
            "held_out_errors_V": negative_errors,
            "mean_held_out_error_V": neg_mean,
            "violates_decision": control_action,
            "ci_coverage": ci_coverage(fit_neg_report, truth),
        },
        "prediction": {
            "positive_improves_held_out": True,
            "negative_does_not_improve": True,
            "observed_positive_improves": positive_improves,
            "observed_negative_does_not_improve": not negative_improves,
            "reproduced": prediction_reproduced,
        },
        "delta_V": {
            "positive_minus_baseline": pos_mean - base_mean,
            "negative_minus_baseline": neg_mean - base_mean,
        },
        "environment": {"python": platform.python_version(), "packages": _versions()},
        "scientific_note": (
            "Synthetic recovery validates the workflow under the assumptions "
            "of the generating model. It is NOT experimental validation and "
            "does not prove identifiability (scientific rules 7 and 8)."
        ),
    }

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        _write_summary(payload, out_dir / "summary.md")
    return payload


def _write_summary(payload: dict, path: Path) -> None:
    base = payload["baseline"]
    pos = payload["positive_control"]
    neg = payload["negative_control"]
    pred = payload["prediction"]
    asm = payload["assembled"]
    lines = [
        "# V2.4 — synthetic end-to-end validation",
        "",
        f"**Label:** {payload['label']}",
        "",
        "## Setup (synthetic, deliberately mismatched)",
        "",
        f"- train on `{payload['protocol']['train_rate']}`, validate on "
        f"{', '.join(payload['protocol']['held_out_rates'])} "
        f"(held out)",
        f"- assembled start values (real registry + observability join): "
        f"{asm['start_values']}",
        f"- synthetic truth (offset): {payload['truth']['values']}",
        f"- positive fit (CALIBRATE action): "
        f"{', '.join(asm['experiment_roles']['positive_fit'])}",
        f"- negative control (violates `{asm['experiment_roles']['negative_control_action']}`): "
        f"{asm['experiment_roles']['negative_control']}",
        f"- seed {payload['protocol']['seed']}, noise σ = "
        f"{payload['protocol']['noise_sigma_V']} V, maxiter "
        f"{payload['protocol']['maxiter']}",
        "",
        "## Held-out-rate voltage RMSE [V]",
        "",
        "| arm | 0.5C | 2C | mean | vs baseline |",
        "|---|---:|---:|---:|---:|",
        _error_row("baseline (assembled)", base, None),
        _error_row("positive control (fit observable pair)", pos, base),
        _error_row("negative control (fit unobservable param)", neg, base),
        "",
        "## Prediction",
        "",
        f"- expected: positive improves held-out; negative does not "
        f"improve — **reproduced: {pred['reproduced']}**",
        f"- observed: positive improves = {pred['observed_positive_improves']}, "
        f"negative does not improve = {pred['observed_negative_does_not_improve']}",
        f"- fitted values: positive {pos['fitted_values']}, "
        f"negative {neg['fitted_values']} (truth "
        f"{payload['truth']['values'][neg['fit']['parameters'][0]['name']]})",
        "",
        "## Limits",
        "",
        f"- {payload['scientific_note']}",
        "- positive fit scope: the scalar-declarable observable pair only; "
        "function-valued kinetics remain CALIBRATE in the action matrix but "
        "are outside this run's fitting scope.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _error_row(
    label: str, arm: dict, baseline: dict | None
) -> str:
    held = arm["held_out_errors_V"]
    cells = [f"{held[r]:.4f}" for r in HELD_OUT_RATES]
    mean = arm["mean_held_out_error_V"]
    if baseline is None:
        delta = "—"
    else:
        d = mean - baseline["mean_held_out_error_V"]
        delta = f"{d:+.4f}"
    return f"| {label} | " + " | ".join(cells) + f" | {mean:.4f} | {delta} |"


def run_stability(
    seeds: list[int],
    *,
    out_dir: Path | None = None,
    registry: Path = DEFAULT_REGISTRY,
    target_path: Path = DEFAULT_TARGET,
    p2_dir: Path = DEFAULT_P2,
    **kwargs,
) -> dict:
    """Run the experiment once per seed and aggregate (V2.6 gate item).

    Stability criterion: the predicted pattern (positive improves held-out,
    negative does not) must reproduce on **every** seed. Returns the combined
    report payload; writes report.json / summary.md under ``out_dir``.
    """
    payloads = [
        run_experiment(
            registry=registry,
            target_path=target_path,
            p2_dir=p2_dir,
            seed=int(s),
            **kwargs,
        )
        for s in seeds
    ]

    def _stats(values: list[float]) -> dict[str, float]:
        arr = np.asarray(values, dtype=float)
        return {
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
        }

    per_seed = [
        {
            "seed": p["protocol"]["seed"],
            "baseline_mean_V": p["baseline"]["mean_held_out_error_V"],
            "positive_mean_V": p["positive_control"]["mean_held_out_error_V"],
            "negative_mean_V": p["negative_control"]["mean_held_out_error_V"],
            "reproduced": p["prediction"]["reproduced"],
            "positive_fit_success": p["positive_control"]["fit"].get("success"),
            "negative_fit_success": p["negative_control"]["fit"].get("success"),
        }
        for p in payloads
    ]
    reproduced_count = sum(1 for s in per_seed if s["reproduced"])
    stability = {
        "n_seeds": len(seeds),
        "seeds": [int(s) for s in seeds],
        "criterion": (
            "prediction (positive improves held-out, negative does not) "
            "reproduces on every seed"
        ),
        "prediction_reproduced_count": f"{reproduced_count}/{len(seeds)}",
        "prediction_reproduced_all": reproduced_count == len(seeds),
        "all_fits_converged": all(
            s["positive_fit_success"] and s["negative_fit_success"]
            for s in per_seed
        ),
        "mean_held_out_error_V": {
            "baseline": _stats([s["baseline_mean_V"] for s in per_seed]),
            "positive_control": _stats([s["positive_mean_V"] for s in per_seed]),
            "negative_control": _stats([s["negative_mean_V"] for s in per_seed]),
        },
        "per_seed": per_seed,
    }
    payload = {
        "run_id": "synthetic_validation_v2.4",
        "label": LABEL_SYNTHETIC,
        "generated": datetime.now(timezone.utc).isoformat(),
        "stability": stability,
        # full single-seed report of the first seed for drill-down
        "representative_seed": payloads[0],
        "scientific_note": payloads[0]["scientific_note"],
    }
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        _write_stability_summary(payload, out_dir / "summary.md")
    return payload


def _stats4(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def run_hardened_validation(
    *,
    out_dir: Path | None = None,
    registry: Path = DEFAULT_REGISTRY,
    target_path: Path = DEFAULT_TARGET,
    p2_dir: Path = DEFAULT_P2,
    model_name: str = "DFN",
    maxiter: int = 40,
    n_truths: int = len(TRUTH_SCALES),
    noise_levels: tuple[float, ...] = NOISE_LEVELS,
    seeds: tuple[int, ...] = (20261117, 20261118, 20261119),
) -> dict:
    """Hardened SYNTHETIC validation: perturbed generation model, drawn truths.

    Removes the inverse crime: data are generated with a different solver,
    tighter tolerances, a coarser mesh and a small perturbation of a parameter
    neither control fits, then fitted with the nominal model. Reports the old
    fixed-truth result alongside the new aggregate for comparison.
    """
    common = dict(
        registry=Path(registry),
        target_path=Path(target_path),
        p2_dir=Path(p2_dir),
        model_name=model_name,
        maxiter=maxiter,
    )
    truth_scales = TRUTH_SCALES[:n_truths]
    runs: list[dict] = []
    for scale in truth_scales:
        for noise in noise_levels:
            for seed in seeds:
                payload = run_experiment(
                    **common,
                    truth_scale=scale,
                    noise_sigma_V=float(noise),
                    seed=int(seed),
                    mismatch=True,
                )
                runs.append(
                    {
                        "truth_scale": float(scale),
                        "noise_sigma_V": float(noise),
                        "seed": int(seed),
                        "truth": payload["truth"]["values"],
                        "baseline_mean_V": payload["baseline"]["mean_held_out_error_V"],
                        "positive_mean_V": payload["positive_control"]["mean_held_out_error_V"],
                        "negative_mean_V": payload["negative_control"]["mean_held_out_error_V"],
                        "positive_beats_baseline": payload["prediction"]["observed_positive_improves"],
                        "negative_does_not_beat_baseline": payload["prediction"][
                            "observed_negative_does_not_improve"
                        ],
                        "prediction_reproduced": payload["prediction"]["reproduced"],
                        "positive_fit_success": payload["positive_control"]["fit"].get("success"),
                        "negative_fit_success": payload["negative_control"]["fit"].get("success"),
                        "positive_ci_coverage": payload["positive_control"]["ci_coverage"],
                        "negative_ci_coverage": payload["negative_control"]["ci_coverage"],
                    }
                )
                print(
                    f"  scale={scale} sigma={noise} seed={seed}: "
                    f"base={runs[-1]['baseline_mean_V']:.4f} "
                    f"pos={runs[-1]['positive_mean_V']:.4f} "
                    f"neg={runs[-1]['negative_mean_V']:.4f} V "
                    f"reproduced={runs[-1]['prediction_reproduced']}",
                    flush=True,
                )

    # The previously committed fixed-truth configuration, run again here as a
    # like-for-like comparison (SYNTHETIC, never experimental).
    reference = run_experiment(
        **common,
        seed=int(seeds[0]),
        noise_sigma_V=float(noise_levels[0]),
        mismatch=False,
    )

    n = len(runs)
    beats = sum(1 for r in runs if r["positive_beats_baseline"])
    neg_ok = sum(1 for r in runs if r["negative_does_not_beat_baseline"])
    both = sum(1 for r in runs if r["prediction_reproduced"])

    coverage: dict = {}
    for arm in ("positive", "negative"):
        key = f"{arm}_ci_coverage"
        available = [r[key] for r in runs if r[key].get("available")]
        if not available:
            coverage[arm] = {
                "available": False,
                "n_runs": n,
                "reason": runs[0][key].get("reason", "no uncertainty estimate"),
            }
        else:
            vals = [c["coverage"] for c in available if c.get("coverage") is not None]
            coverage[arm] = {
                "available": True,
                "n_runs_with_uncertainty": len(available),
                "coverage": _stats4(vals) if vals else None,
            }

    payload = {
        "run_id": "synthetic_validation_v2.4_hardened_mismatch",
        "label": LABEL_SYNTHETIC,
        "generated": datetime.now(timezone.utc).isoformat(),
        "design": {
            "n_runs": n,
            "truth_scales": truth_scales,
            "noise_levels_V": list(noise_levels),
            "seeds": list(seeds),
            "generation_solver": MISMATCH_SOLVER,
            "generation_rtol": MISMATCH_RTOL,
            "generation_atol": MISMATCH_ATOL,
            "generation_var_pts": dict(MISMATCH_VAR_PTS),
            "unfitted_parameter": UNFITTED_PARAM,
            "unfitted_factor": UNFITTED_FACTOR,
            "fit_uses_nominal_model": True,
            "truth_scaling": "start + scale * (recorded V2.4 truth - start)",
            "noise_sources": [
                "results/v2/synthetic_validation (V2.4, 1e-3 V)",
                "configs/p2/recovery_single_1C.yaml (2e-3 V)",
            ],
        },
        "aggregate": {
            "held_out_rmse_V": {
                "baseline": _stats4([r["baseline_mean_V"] for r in runs]),
                "positive_control": _stats4([r["positive_mean_V"] for r in runs]),
                "negative_control": _stats4([r["negative_mean_V"] for r in runs]),
            },
            "positive_beats_baseline": {
                "count": beats,
                "n": n,
                "rate": beats / n if n else None,
            },
            "negative_does_not_beat_baseline": {
                "count": neg_ok,
                "n": n,
                "rate": neg_ok / n if n else None,
            },
            "prediction_reproduced": {"count": both, "n": n, "rate": both / n if n else None},
            "ci_coverage": coverage,
            "all_fits_converged": all(
                r["positive_fit_success"] and r["negative_fit_success"] for r in runs
            ),
        },
        "per_run": runs,
        "fixed_truth_reference": {
            "note": "old fixed-truth V2.4 configuration (mismatch disabled)",
            "baseline_mean_V": reference["baseline"]["mean_held_out_error_V"],
            "positive_mean_V": reference["positive_control"]["mean_held_out_error_V"],
            "negative_mean_V": reference["negative_control"]["mean_held_out_error_V"],
            "reproduced": reference["prediction"]["reproduced"],
        },
        "environment": {"python": platform.python_version(), "packages": _versions()},
        "scientific_note": (
            "SYNTHETIC mismatch validation only: a different generating solver, "
            "tolerances and mesh plus an unfitted-parameter perturbation remove "
            "the inverse crime. This is NOT experimental validation and does "
            "not prove identifiability (scientific rules 7 and 8)."
        ),
    }
    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        _write_hardened_summary(payload, out_dir / "summary.md")
    return payload


def _write_hardened_summary(payload: dict, path: Path) -> None:
    agg = payload["aggregate"]
    errs = agg["held_out_rmse_V"]
    design = payload["design"]
    lines = [
        "# V2.4 — hardened SYNTHETIC validation (mismatch, drawn truths)",
        "",
        f"**Label:** {payload['label']}",
        "",
        "## Design (all SYNTHETIC)",
        "",
        f"- runs: {design['n_runs']} = {len(design['truth_scales'])} truths x "
        f"{len(design['noise_levels_V'])} noise levels x {len(design['seeds'])} seeds",
        f"- generation: {design['generation_solver']} solver "
        f"(rtol={design['generation_rtol']}, atol={design['generation_atol']}), "
        f"mesh {design['generation_var_pts']}",
        f"- unfitted perturbation: {design['unfitted_parameter']} x "
        f"{design['unfitted_factor']}; fits use the nominal model",
        "",
        "## Held-out mean voltage RMSE [V] (mean / std / min / max)",
        "",
        "| arm | mean | std | min | max |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm in ("baseline", "positive_control", "negative_control"):
        s = errs[arm]
        lines.append(
            f"| {arm} | {s['mean']:.4f} | {s['std']:.4f} | "
            f"{s['min']:.4f} | {s['max']:.4f} |"
        )
    lines += [
        "",
        "## Controls",
        "",
        f"- positive beats baseline: {agg['positive_beats_baseline']['count']}/"
        f"{agg['positive_beats_baseline']['n']}",
        f"- negative does not beat baseline: "
        f"{agg['negative_does_not_beat_baseline']['count']}/"
        f"{agg['negative_does_not_beat_baseline']['n']}",
        f"- both (prediction reproduced): {agg['prediction_reproduced']['count']}/"
        f"{agg['prediction_reproduced']['n']}",
        f"- all fits converged: {agg['all_fits_converged']}",
        "",
        "## 95% CI coverage of fitted parameters",
        "",
    ]
    for arm, cov in agg["ci_coverage"].items():
        if cov["available"]:
            lines.append(
                f"- {arm}: coverage mean {cov['coverage']['mean']:.3f} "
                f"(n={cov['n_runs_with_uncertainty']} runs with uncertainty)"
            )
        else:
            lines.append(f"- {arm}: not available — {cov['reason']}")
    ref = payload["fixed_truth_reference"]
    lines += [
        "",
        "## Old fixed-truth result (comparison)",
        "",
        f"- baseline {ref['baseline_mean_V']:.4f} V, positive "
        f"{ref['positive_mean_V']:.4f} V, negative {ref['negative_mean_V']:.4f} V, "
        f"reproduced {ref['reproduced']}",
        "",
        f"- {payload['scientific_note']}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_stability_summary(payload: dict, path: Path) -> None:
    st = payload["stability"]
    errs = st["mean_held_out_error_V"]
    lines = [
        "# V2.4 — synthetic end-to-end validation (multi-seed stability)",
        "",
        f"**Label:** {payload['label']}",
        "",
        "## Stability across seeds",
        "",
        f"- seeds: {', '.join(str(s) for s in st['seeds'])} "
        f"(n = {st['n_seeds']})",
        f"- criterion: {st['criterion']}",
        f"- **prediction reproduced: {st['prediction_reproduced_count']}** "
        f"(all: {st['prediction_reproduced_all']})",
        f"- all fits converged: {st['all_fits_converged']}",
        "",
        "## Held-out mean voltage RMSE [V] across seeds",
        "",
        "| arm | mean | std | min | max |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm in ("baseline", "positive_control", "negative_control"):
        s = errs[arm]
        lines.append(
            f"| {arm} | {s['mean']:.4f} | {s['std']:.4f} | "
            f"{s['min']:.4f} | {s['max']:.4f} |"
        )
    lines += [
        "",
        "## Per-seed detail",
        "",
        "| seed | baseline | positive | negative | reproduced |",
        "|---|---:|---:|---:|---|",
    ]
    for s in st["per_seed"]:
        lines.append(
            f"| {s['seed']} | {s['baseline_mean_V']:.4f} | "
            f"{s['positive_mean_V']:.4f} | {s['negative_mean_V']:.4f} | "
            f"{s['reproduced']} |"
        )
    lines += [
        "",
        f"- {payload['scientific_note']}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--target", default=str(DEFAULT_TARGET))
    ap.add_argument("--p2-results", default=str(DEFAULT_P2))
    ap.add_argument("--out", default=None)
    ap.add_argument("--model", default="DFN")
    ap.add_argument(
        "--mismatch",
        action="store_true",
        help="hardened SYNTHETIC mode: perturbed generating solver/tolerance/"
        "mesh plus an unfitted-parameter perturbation, drawn truths and two "
        "noise levels; writes to a new results/v2 directory",
    )
    ap.add_argument("--n-truths", type=int, default=len(TRUTH_SCALES))
    ap.add_argument(
        "--noise-levels",
        nargs=2,
        type=float,
        default=list(NOISE_LEVELS),
        metavar=("SIGMA1", "SIGMA2"),
    )
    ap.add_argument(
        "--mismatch-seeds", nargs="+", type=int, default=list((20261117, 20261118, 20261119))
    )
    ap.add_argument("--seed", type=int, default=20261117)
    ap.add_argument(
        "--n-seeds",
        type=int,
        default=5,
        help="run the experiment for this many consecutive seeds and report "
        "stability (1 = single-seed report)",
    )
    ap.add_argument("--maxiter", type=int, default=40)
    ap.add_argument("--noise-sigma-v", type=float, default=1e-3)
    args = ap.parse_args(argv)

    t0 = time.perf_counter()
    out_dir = Path(args.out or (MISMATCH_OUT if args.mismatch else DEFAULT_OUT))
    common = dict(
        registry=Path(args.registry),
        target_path=Path(args.target),
        p2_dir=Path(args.p2_results),
        model_name=args.model,
        maxiter=args.maxiter,
    )
    if args.mismatch:
        payload = run_hardened_validation(
            out_dir=out_dir,
            n_truths=args.n_truths,
            noise_levels=tuple(args.noise_levels),
            seeds=tuple(args.mismatch_seeds),
            **common,
        )
        agg = payload["aggregate"]
        print(f"label        : {payload['label']}")
        print(f"runs         : {payload['design']['n_runs']}")
        for arm, s in agg["held_out_rmse_V"].items():
            print(f"{arm:18s}: {s['mean']:.4f} +/- {s['std']:.4f} V "
                  f"[{s['min']:.4f}, {s['max']:.4f}]")
        print(f"positive beats baseline: "
              f"{agg['positive_beats_baseline']['count']}/{agg['positive_beats_baseline']['n']}")
        print(f"negative does not beat baseline: "
              f"{agg['negative_does_not_beat_baseline']['count']}/"
              f"{agg['negative_does_not_beat_baseline']['n']}")
        print(f"prediction reproduced: "
              f"{agg['prediction_reproduced']['count']}/{agg['prediction_reproduced']['n']}")
        for arm, cov in agg["ci_coverage"].items():
            state = (f"{cov['coverage']['mean']:.3f}" if cov["available"] else "not available")
            print(f"CI coverage {arm:8s}: {state}")
    elif args.n_seeds > 1:
        seeds = [args.seed + i for i in range(args.n_seeds)]
        payload = run_stability(
            seeds, out_dir=out_dir, noise_sigma_V=args.noise_sigma_v, **common
        )
        st = payload["stability"]
        print(f"label        : {payload['label']}")
        print(f"seeds        : {st['seeds']}")
        for arm, s in st["mean_held_out_error_V"].items():
            print(f"{arm:16s}: {s['mean']:.4f} +/- {s['std']:.4f} V")
        print(f"prediction reproduced: {st['prediction_reproduced_count']} "
              f"(all: {st['prediction_reproduced_all']})")
    else:
        payload = run_experiment(
            seed=args.seed, out_dir=out_dir, noise_sigma_V=args.noise_sigma_v, **common
        )
        print(f"label        : {payload['label']}")
        print(f"baseline mean: {payload['baseline']['mean_held_out_error_V']:.4f} V")
        print(
            f"positive mean: {payload['positive_control']['mean_held_out_error_V']:.4f} V "
            f"(fit success: {payload['positive_control']['fit'].get('success')})"
        )
        print(
            f"negative mean: {payload['negative_control']['mean_held_out_error_V']:.4f} V "
            f"(fit success: {payload['negative_control']['fit'].get('success')})"
        )
        print(f"prediction reproduced: {payload['prediction']['reproduced']}")
    runtime = time.perf_counter() - t0
    print(f"wrote {out_dir}/report.json, summary.md ({runtime:.1f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
