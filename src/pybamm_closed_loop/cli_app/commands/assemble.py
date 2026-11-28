"""Assembly command: dossiers, traceability, gate and reproducibility manifest."""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.text import Text

from ..context import State
from ..errors import InputError, TraceabilityError
from ..inputs import load_doc_texts, load_json, read_target, sha256, tool_version
from ..render import kv, notice, section

ASSEMBLE_HELP = """Assemble per-parameter dossiers for a target cell.

Consumes an existing registry; it never extracts or calibrates values. The
PyBaMM export contains only human-approved parameters. Without --gate the
export is empty by design (scientific rule 10).
"""


def _state(ctx: typer.Context) -> State:
    state = ctx.obj
    if not isinstance(state, State):
        raise InputError("CLI state was not initialised.", action="Report this as a CLI bug.")
    return state


def assemble_command(
    ctx: typer.Context,
    target: Path = typer.Option(..., "--target", help="Target specification YAML."),
    registry: Path = typer.Option(..., "--registry", help="Registry records JSON."),
    out: Path = typer.Option(..., "--out", help="Output directory."),
    documents: Path | None = typer.Option(
        None, "--documents", help="Raw document store for quote verification."
    ),
    gate: Path | None = typer.Option(
        None, "--gate", help="Approval gate JSON (only approved parameters are exported)."
    ),
    p2_results: Path = typer.Option(
        Path("results/p2"), "--p2-results", help="Recorded identifiability artifacts."
    ),
    accuracy_critical: list[str] = typer.Option(
        [], "--accuracy-critical", help="Canonical ids whose accuracy is critical."
    ),
    rubric_version: str = typer.Option("rubric-v3", "--rubric-version"),
) -> int:
    """Assemble provenance-grounded dossiers into a reviewable report."""
    from ...assembly import ApprovalGate, GateValidationError, Rubric, assemble
    from ...assembly.dossier import check_traceability
    from ...assembly.observability import (
        BOOTSTRAP_REL_STD_OBSERVABILITY,
        SENSITIVITY_OBSERVABILITY_THRESHOLD,
        load_observability,
    )
    from ...assembly.report import verify_record_quotes

    state = _state(ctx)
    target_path = target.expanduser().resolve()
    registry_path = registry.expanduser().resolve()
    out_dir = out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    target_spec = read_target(target_path)
    records = load_json(registry_path, description="registry")
    if not isinstance(records, list):
        raise InputError(
            "Registry must be a JSON list of records.",
            why=f"Found {type(records).__name__} in {registry_path}",
            action="Point --registry at a registry JSON file.",
        )

    doc_texts: dict[str, str] = {}
    quote_stats: dict[str, int] = {}
    if documents is not None:
        doc_texts = load_doc_texts(documents.expanduser().resolve())
        records, quote_stats = verify_record_quotes(records, doc_texts)

    rubric = Rubric(rubric_version)
    observability = load_observability(
        p2_results.expanduser().resolve(), records, set(accuracy_critical or ())
    )
    report = assemble(records, target_spec, rubric, observability=observability)

    trace: list[dict] = []
    counts = {"ok": 0, "warn": 0, "fail": 0}
    for dossier in report.dossiers:
        level, messages = check_traceability(dossier)
        counts[level] += 1
        trace.append({"parameter": dossier.get("parameter"), "level": level, "messages": messages})

    gate_path = gate.expanduser().resolve() if gate is not None else None
    approval = ApprovalGate()
    if gate_path is not None:
        payload = load_json(gate_path, description="approval gate")
        try:
            approval = ApprovalGate.from_dict(payload)
        except GateValidationError as exc:
            raise InputError(
                "Approval gate is invalid.",
                why=str(exc),
                action="Provide exactly one well-formed approval record per parameter.",
            ) from exc

    payload = report.to_dict()
    payload["traceability"] = trace
    (out_dir / "report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "report.md").write_text(report.to_markdown(), encoding="utf-8")
    exported = report.pybamm_export(approval)
    export_path = out_dir / "pybamm_export.json"
    export_path.write_text(
        json.dumps(exported, indent=2, sort_keys=True), encoding="utf-8"
    )

    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "command": "parallm assemble",
        "tool": {"parallm_pybamm": tool_version(), "python": platform.python_version()},
        "rubric_version": rubric.version,
        "target": target_spec.to_dict(),
        "target_config": {"path": str(target_path), "sha256": sha256(target_path)},
        "registry": {
            "path": str(registry_path),
            "sha256": sha256(registry_path),
            "n_records": len(records),
        },
        "documents": {
            "path": str(documents) if documents else None,
            "n_documents": len(doc_texts),
            "quote_verification": quote_stats,
        },
        "gate": {
            "path": str(gate_path) if gate_path else None,
            "sha256": sha256(gate_path) if gate_path else None,
            "n_approved": len(approval.approved_parameters()),
        },
        "observability": {
            "p2_results": str(p2_results),
            "assessed_parameters": sorted(observability),
            "accuracy_critical": sorted(accuracy_critical or ()),
            "thresholds": {
                "sensitivity_observability": SENSITIVITY_OBSERVABILITY_THRESHOLD,
                "bootstrap_rel_std_observability": BOOTSTRAP_REL_STD_OBSERVABILITY,
            },
            "action_matrix": report.action_matrix(),
        },
        "traceability": counts,
        "n_exported": len(exported),
        "outputs": ["report.json", "report.md", "pybamm_export.json", "manifest.json"],
        "outputs_sha256": {"pybamm_export.json": sha256(export_path)},
        "note": (
            "Every dossier field traces to a verified quote or carries an "
            "explicit status flag (see report.json 'traceability'). The PyBaMM "
            "export contains only human-approved parameters (decision D6); "
            "with no gate file it is empty by design."
        ),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    summary = report.summary()
    if not state.quiet and not state.json_mode:
        section(state.console, "ASSEMBLY REPORT")
        kv(
            state.console,
            (
                ("Target", target_spec.target_id),
                ("Rubric", rubric.version),
                ("Parameters", summary["n_parameters"]),
                ("Decisions", summary["decisions"]),
                ("Conflicts", summary["n_conflicts"]),
                ("Action matrix", report.action_matrix()),
                (
                    "Traceability",
                    f"ok={counts['ok']} warn={counts['warn']} fail={counts['fail']}",
                ),
                ("Approved export", f"{len(exported)} parameter(s)"),
                ("Gate", str(gate_path) if gate_path else "none provided"),
            ),
        )
        for entry in trace:
            if entry["level"] == "ok":
                continue
            for message in entry["messages"]:
                notice(
                    state.console,
                    f"{entry['parameter']}: {message}",
                    "error" if entry["level"] == "fail" else "warn",
                )
        section(state.console, "OUTPUTS")
        for name in manifest["outputs"]:
            state.console.print(Text(f"  {out_dir / name}", style="app.muted"))
        notice(state.console, "Extracted values are not calibrated; export requires approval.")

    state.emit(
        {
            "target": target_spec.to_dict(),
            "rubric_version": rubric.version,
            "summary": summary,
            "traceability": counts,
            "n_exported": len(exported),
            "outputs": [str(out_dir / name) for name in manifest["outputs"]],
        },
        status="failed" if counts["fail"] else "completed",
    )
    if counts["fail"]:
        raise TraceabilityError(
            "Dossier traceability checks failed.",
            why=f"{counts['fail']} dossier(s) failed; see report.json and the messages above.",
            action="Provide source documents with --documents, or add explicit status flags.",
        )
    return 0
