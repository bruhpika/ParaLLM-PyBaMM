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
    truth = dict(TRUTH_VALUES if truth_values is None else truth_values)

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
        },
        "negative_control": {
            "fit": fit_neg_report,
            "fitted_values": fitted_neg,
            "held_out_errors_V": negative_errors,
            "mean_held_out_error_V": neg_mean,
            "violates_decision": control_action,
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--target", default=str(DEFAULT_TARGET))
    ap.add_argument("--p2-results", default=str(DEFAULT_P2))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--model", default="DFN")
    ap.add_argument("--seed", type=int, default=20261117)
    ap.add_argument("--maxiter", type=int, default=40)
    ap.add_argument("--noise-sigma-v", type=float, default=1e-3)
    args = ap.parse_args(argv)

    t0 = time.perf_counter()
    payload = run_experiment(
        registry=Path(args.registry),
        target_path=Path(args.target),
        p2_dir=Path(args.p2_results),
        out_dir=Path(args.out),
        model_name=args.model,
        noise_sigma_V=args.noise_sigma_v,
        seed=args.seed,
        maxiter=args.maxiter,
    )
    runtime = time.perf_counter() - t0
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
    print(f"wrote {args.out}/report.json, summary.md ({runtime:.1f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
