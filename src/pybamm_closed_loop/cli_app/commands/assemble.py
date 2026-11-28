"""Assembly command: dossiers, traceability, gate and reproducibility manifest."""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from rich.text import Text

from ..context import State
from ..errors import InputError, TraceabilityError
from ..inputs import load_doc_texts, load_json, read_target, sha256, tool_version
from ..render import kv, notice, section, table

ASSEMBLE_HELP = """Assemble per-parameter dossiers for a target cell.

Consumes an existing registry; it never extracts or calibrates values. Every
run writes `gate.pending.json` into --out: a fail-closed template containing
one unapproved, hash-bound entry per exportable decision. Copy that file to a
different name, let a human set approved=true with an approver and a recorded
reason, then re-run assemble with --gate pointing at the edited copy. An
unedited pending gate exports nothing. There is no auto-approve option.
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
    resolution: Path | None = typer.Option(
        None, "--resolution",
        help="Human resolution JSON for REVIEW decisions (from `parallm resolve`).",
    ),
    p2_results: Path = typer.Option(
        Path("results/p2"), "--p2-results", help="Recorded identifiability artifacts."
    ),
    accuracy_critical: list[str] = typer.Option(
        [], "--accuracy-critical", help="Canonical ids whose accuracy is critical."
    ),
    rubric_version: str = typer.Option("rubric-v5", "--rubric-version"),
) -> int:
    """Assemble dossiers; write a fail-closed gate.pending.json template.

    The pending gate has one unapproved, hash-bound entry per exportable
    decision. Copy it, let a human approve only reviewed decisions with a
    recorded reason, then re-run with --gate pointing at the edited copy.
    """
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

    resolution_info: dict[str, Any] = {"path": None, "sha256": None, "n_resolved": 0}
    resolution_summary: list[dict[str, Any]] = []
    if resolution is not None:
        from ...assembly.resolution import ResolutionError, apply_resolutions

        resolution_path = resolution.expanduser().resolve()
        try:
            report.dossiers, applied = apply_resolutions(
                report.dossiers, load_json(resolution_path, description="resolution record")
            )
        except (ResolutionError, OSError, ValueError) as exc:
            raise InputError(
                "Human resolution record is invalid.",
                why=str(exc),
                action="Re-run `parallm resolve` against this assembly and pass the new file.",
            ) from exc
        resolution_summary = [
            {"parameter": a.parameter, "original_decision": a.original_decision,
             "resolved_decision": a.resolved_decision, "reviewer": a.reviewer,
             "binding_sha256": a.binding_sha256}
            for a in applied
        ]
        resolution_info = {
            "path": str(resolution_path),
            "sha256": sha256(resolution_path),
            "n_resolved": len(applied),
        }

    trace: list[dict] = []
    counts = {"ok": 0, "warn": 0, "fail": 0}
    for dossier in report.dossiers:
        level, messages = check_traceability(dossier)
        counts[level] += 1
        trace.append({"parameter": dossier.get("parameter"), "level": level, "messages": messages})

    gate_path = gate.expanduser().resolve() if gate is not None else None
    pending_path = out_dir / "gate.pending.json"
    if gate_path is not None and gate_path == pending_path:
        raise InputError(
            "The pending gate template cannot be used as --gate.",
            why=(
                f"{pending_path} is regenerated by every assemble run; using it "
                "as input would discard human edits on the next run."
            ),
            action="Copy it to a different filename, edit the copy, and pass that copy with --gate.",
        )
    approval = ApprovalGate()
    if gate_path is not None:
        payload = load_json(gate_path, description="approval gate")
        try:
            approval = ApprovalGate.from_dict(payload)
        except GateValidationError as exc:
            raise InputError(
                "Approval gate is invalid.",
                why=str(exc),
                action="Copy the gate.pending.json template, fill in the review, and pass the edited copy.",
            ) from exc

    payload = report.to_dict()
    payload["traceability"] = trace
    (out_dir / "report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "report.md").write_text(report.to_markdown(), encoding="utf-8")
    export_result = report.pybamm_export(approval, with_reasons=True)
    exported = export_result["parameters"]
    blocked = export_result["blocked"]
    export_path = out_dir / "pybamm_export.json"
    export_path.write_text(
        json.dumps(exported, indent=2, sort_keys=True), encoding="utf-8"
    )

    generated = datetime.now(timezone.utc).isoformat()
    from ...assembly.gate import pending_gate_payload

    pending_path.write_text(
        json.dumps(
            pending_gate_payload(
                report.dossiers, target=target_spec.target_id,
                rubric_version=rubric.version, generated=generated,
            ),
            indent=2, sort_keys=True,
        ),
        encoding="utf-8",
    )

    blocked_path = out_dir / "blocked.json"
    blocked_path.write_text(
        json.dumps(blocked, indent=2, sort_keys=True), encoding="utf-8"
    )

    manifest = {
        "generated": generated,
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
        "resolutions": {**resolution_info, "decisions": resolution_summary},
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
        "outputs": ["report.json", "report.md", "pybamm_export.json",
                    "blocked.json", "gate.pending.json", "manifest.json"],
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
        if blocked:
            section(state.console, "BLOCKED FROM EXPORT")
            table(
                state.console, ("PARAMETER", "REASON"),
                [(parameter, reason) for parameter, reason in sorted(blocked.items())],
            )
            notice(
                state.console,
                "Each parameter above was withheld; see the reason before editing the gate.",
                "warn",
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
            "resolutions": resolution_summary,
            "blocked": blocked,
            "n_blocked": len(blocked),
            "pending_gate": str(pending_path),
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
