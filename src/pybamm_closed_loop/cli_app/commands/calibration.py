"""Calibration commands: recorded results and synthetic recovery only."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer

from ..context import State
from ..errors import DependencyError, InputError, ParseError
from ..inputs import load_json, sha256
from ..render import format_value, kv, make_progress, notice, section, status_text, table

calibrate_app = typer.Typer(
    name="calibrate",
    help=(
        "Calibration workflows. Real-data fitting is NOT implemented. "
        "Only recorded reports and synthetic recovery are exposed."
    ),
    add_completion=False,
    no_args_is_help=True,
)


def _state(ctx: typer.Context) -> State:
    state = ctx.obj
    if not isinstance(state, State):
        raise InputError("CLI state was not initialised.", action="Report this as a CLI bug.")
    return state


def _results_dir(state: State, explicit: Path | None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_dir():
            raise InputError("Results directory not found.", why=f"Expected: {path}", action="Pass an existing --results path.")
        return path
    configured = None
    if state.config is not None:
        configured = state.config.resolve(state.config.paths.p2_results)
    path = configured or Path.cwd() / "results" / "p2"
    if not path.is_dir():
        raise InputError(
            "No calibration results directory found.",
            why=f"Expected: {path}",
            action="Pass --results PATH or point config paths.p2_results at one.",
        )
    return path


def calibrate_report(
    ctx: typer.Context,
    results: Path | None = typer.Option(None, "--results", help="Directory of recorded fit reports."),
) -> int:
    """Summarise recorded calibration reports without running a fit."""
    state = _state(ctx)
    root = _results_dir(state, results)
    files = sorted(root.rglob("report.json"))
    rows: list[tuple[str, str, str, str, str]] = []
    reports: list[dict[str, Any]] = []
    for file in files:
        payload = load_json(file, description="fit report")
        if not isinstance(payload, dict):
            continue
        runs = (
            [payload]
            if "fit_spec" in payload
            else [
                run for run in payload.get("runs", [])
                if isinstance(run, dict) and "fit_spec" in run
            ]
        )
        for index, fit in enumerate(runs):
            reports.append({"path": str(file), "run_index": index, "report": fit})
            spec = fit["fit_spec"]
            success = fit.get("success")
            status = "CONVERGED" if success is True else "FAILED" if success is False else "UNKNOWN"
            rows.append(
                (
                    f"{file.parent.name}[{index}]" if len(runs) > 1 else file.parent.name,
                    spec.get("model_name", "?"),
                    f"{len(fit.get('parameters', []))}",
                    format_value(fit.get("final_cost")),
                    status,
                )
            )
    if not state.quiet and not state.json_mode:
        section(state.console, "RECORDED CALIBRATION REPORTS")
        kv(state.console, (("Results", str(root)), ("Reports", len(reports))))
        if rows:
            table(
                state.console,
                ("RUN", "MODEL", "FITTED", "FINAL COST", "STATUS"),
                [(r[0], r[1], r[2], r[3], status_text(r[4])) for r in rows],
                status_columns=(4,),
            )
        notice(state.console, "All recorded fits are synthetic unless a source states otherwise.")
    state.emit({"results": str(root), "reports": reports})
    return 0


def calibrate_synthetic(
    ctx: typer.Context,
    config: Path = typer.Option(..., "--config", help="Synthetic recovery config (YAML/JSON)."),
    out: Path = typer.Option(..., "--out", help="Output directory for the fit report."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Allow writing into a non-empty directory."),
) -> int:
    """Run one synthetic recovery fit; never fits experimental data."""
    state = _state(ctx)
    config_file = config.expanduser().resolve()
    if not config_file.is_file():
        raise InputError("Calibration config not found.", why=f"Expected: {config_file}", action="Pass an existing YAML/JSON config.")
    out_dir = out.expanduser().resolve()
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise InputError(
            "Output directory is not empty.",
            why=f"Refusing to write into {out_dir}",
            action="Choose a new --out path or pass --overwrite.",
        )
    raw = _read_config(config_file)
    synth_keys = (
        "parameter_set", "model_name", "true_values", "conditions",
        "noise_sigma_V", "seed", "description", "solver", "var_pts",
    )
    fit_keys = ("parameter_set", "model_name", "fit_parameters", "cost", "sigma", "fixed_values", "description")
    synth_raw = {key: raw[key] for key in synth_keys if key in raw}
    fit_raw = {key: raw[key] for key in fit_keys if key in raw}
    optimizer = raw.get("optimizer") or {}
    fit_raw.setdefault("method", optimizer.get("method", "L-BFGS-B"))
    fit_raw.setdefault("maxiter", optimizer.get("maxiter", 100))
    fit_raw.setdefault("jac", optimizer.get("jac", True))

    try:
        from ...calibration.fitting import FitSpec, build_problem, run_fit
        from ...calibration.synthetic import SyntheticSpec, generate_datasets
    except ImportError as exc:
        raise DependencyError(
            "Synthetic calibration requires the ecosystem extra.",
            why=str(exc),
            action="Install with: pip install 'parallm-pybamm[ecosystem]'.",
        ) from exc

    synthetic_spec = SyntheticSpec.from_dict(synth_raw)
    fit_spec = FitSpec.from_dict(fit_raw)
    progress = make_progress(state.console, "Generating synthetic observations", enabled=not state.quiet)
    with progress:
        task = progress.add_task("Generating synthetic observations", total=2)
        datasets = generate_datasets(synthetic_spec)
        progress.update(task, advance=1)
        progress.update(task, description="Fitting synthetic data", advance=1)
        problem, build_info = build_problem(datasets, fit_spec)
        report = run_fit(problem, fit_spec, truth=synthetic_spec.true_values)
    report["synthetic"] = True
    report["scientific_note"] = (
        "Synthetic parameter recovery only. NOT experimental validation. "
        "A successful optimization does not prove identifiability."
    )
    report["provenance"] = {
        "config": str(config_file),
        "config_sha256": sha256(config_file),
        "generated": datetime.now(timezone.utc).isoformat(),
        "build": build_info,
        "seed": synthetic_spec.seed,
        "noise_sigma_V": synthetic_spec.noise_sigma_V,
        "conditions": [m for _, _, m in datasets],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "fit_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    converged = report.get("success") is True
    if not state.quiet and not state.json_mode:
        section(state.console, "CALIBRATION (SYNTHETIC)")
        kv(
            state.console,
            (
                ("Run", raw.get("run_id", "unspecified")),
                ("Model", fit_spec.model_name),
                ("Parameter set", fit_spec.parameter_set),
                ("Parameters fitted", len(fit_spec.fit_parameters)),
                ("Objective", fit_spec.cost),
                ("Optimizer", fit_spec.method),
                ("Evaluations", report.get("n_evaluations")),
                ("Final cost", report.get("final_cost")),
                ("Status", "CONVERGED" if converged else "NOT CONVERGED"),
            ),
        )
        table(
            state.console,
            ("PARAMETER", "INITIAL", "BOUNDS", "ESTIMATE", "TRUE (SYNTHETIC)"),
            [
                (
                    p["name"],
                    p["initial_value"],
                    f"{p['bounds'][0]:g}..{p['bounds'][1]:g}",
                    p["estimate"],
                    (report.get("recovery") or {}).get(p["name"], {}).get("truth"),
                )
                for p in report["parameters"]
            ],
            numeric_columns=(1, 3, 4),
        )
        notice(state.console, "SYNTHETIC RECOVERY ONLY — not experimental validation; convergence is not identifiability.", "warn")
    state.emit({"output": str(out_dir / "fit_report.json"), "report": report}, status="completed" if converged else "failed")
    return 0 if converged else 1


def _read_config(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            data = json.loads(raw)
        else:
            import yaml

            data = yaml.safe_load(raw)
    except (OSError, ValueError) as exc:
        raise ParseError("Calibration config is invalid.", why=str(exc)) from exc
    if not isinstance(data, dict):
        raise ParseError("Calibration config must be a mapping.", why=str(path))
    return data


calibrate_app.command("report")(calibrate_report)
calibrate_app.command("synthetic")(calibrate_synthetic)
