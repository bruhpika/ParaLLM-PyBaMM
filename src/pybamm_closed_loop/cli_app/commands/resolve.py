"""Record a human resolution of one REVIEW decision from an assembly report."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from ..context import State
from ..errors import InputError, OverwriteError
from ..inputs import load_json
from ..render import kv, notice, section


def _state(ctx: typer.Context) -> State:
    state = ctx.obj
    if not isinstance(state, State):
        raise InputError("CLI state was not initialised.", action="Report this as a CLI bug.")
    return state


def resolve(
    ctx: typer.Context,
    assembly: Path = typer.Option(..., "--assembly", help="Assembly folder containing report.json."),
    parameter: str = typer.Option(..., "--parameter", help="Canonical id with a REVIEW decision."),
    decision: str = typer.Option(..., "--decision", help="Resolved decision: USE or FIX."),
    reason: str = typer.Option(..., "--reason", help="Human's recorded scientific reason."),
    evidence: str = typer.Option(..., "--evidence", help="Locator or quote supporting the resolution."),
    reviewer: str = typer.Option(..., "--reviewer", help="Name of the human reviewer."),
    out: Path = typer.Option(..., "--out", help="NEW resolution JSON file (never overwrites)."),
) -> int:
    """Write a human-authored resolution for a REVIEW decision."""
    from ...assembly.resolution import RESOLUTION_VERSION, ResolutionError, make_resolution_record

    state = _state(ctx)
    assembly_dir = assembly.expanduser().resolve()
    report_file = assembly_dir / "report.json"
    if not report_file.is_file():
        raise InputError(
            "Assembly report not found.",
            why=f"Expected: {report_file}",
            action="Run `parallm assemble` first and pass its output folder with --assembly.",
        )
    report = load_json(report_file, description="assembly report")
    dossiers = report.get("parameters") if isinstance(report, dict) else None
    if not isinstance(dossiers, list):
        raise InputError("Assembly report has no parameter dossiers.", action="Re-run assemble.")
    dossier = next((d for d in dossiers
                    if isinstance(d, dict) and d.get("parameter") == parameter), None)
    if dossier is None:
        raise InputError(
            f"Unknown parameter {parameter!r} in the assembly report.",
            action="Use a canonical_id from report.json.",
        )

    try:
        record = make_resolution_record(
            dossier, decision=decision, reason=reason,
            evidence=evidence, reviewer=reviewer,
        )
    except ResolutionError as exc:
        raise InputError("Resolution was refused.", why=str(exc),
                         action="Only a REVIEW decision can be resolved to USE or FIX.") from exc

    record["target"] = report.get("summary", {}).get("target", {}).get("target_id")
    payload = {
        "resolution_version": RESOLUTION_VERSION,
        "generated": record["timestamp"],
        "target": record["target"],
        "rubric_version": dossier.get("rubric_version"),
        "decisions": [record],
    }
    out_path = out.expanduser().resolve()
    if out_path.exists():
        raise OverwriteError(
            "Resolution output already exists.",
            why=f"Refusing to overwrite: {out_path}",
            action="Choose a new --out path.",
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not state.quiet and not state.json_mode:
        section(state.console, "HUMAN RESOLUTION RECORDED")
        kv(state.console, (
            ("Parameter", parameter),
            ("Original", record["original_decision"]),
            ("Resolved", record["resolved_decision"]),
            ("Reviewer", reviewer),
            ("Binding", record["binding_sha256"]),
            ("Output", str(out_path)),
        ))
        notice(state.console, "Recorded human reason and evidence; no decision was inferred.", "warn")
    state.emit({
        "output": str(out_path),
        "parameter": parameter,
        "original_decision": record["original_decision"],
        "resolved_decision": record["resolved_decision"],
        "binding_sha256": record["binding_sha256"],
        "reviewer": reviewer,
    })
    return 0
