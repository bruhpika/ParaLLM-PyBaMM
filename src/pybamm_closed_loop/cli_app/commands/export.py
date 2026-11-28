"""Approved-only export to machine-readable JSON or PyBaMM-name overlays."""

from __future__ import annotations

import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer

from ..artifact import (
    APPROVED,
    ATTESTED,
    ATTESTED_EMPTY,
    GATE_REJECTED,
    NOT_APPLICABLE,
    NOT_PERFORMED,
    NOT_RECORDED,
    SCHEMA_V1,
    SCHEMA_V2,
    STATUS_COMPLETE,
    STATUS_EMPTY_AFTER_FILTERING,
    STATUS_EMPTY_UNVERIFIED,
    STATUS_INTENTIONALLY_EMPTY,
    STATUS_PARTIAL,
    UNKNOWN,
    UNVERIFIED,
    VALIDATION_NEEDS_REVIEW,
    VALIDATION_REJECTED,
    ArtifactData,
    establish_attestation,
    normalise_validation_state,
    read_artifact,
    write_artifact_payload,
)
from ..context import State
from ..errors import ExportError, InputError, OverwriteError
from ..inputs import load_json, sha256, tool_version
from ..render import kv, notice, section, table

EXPORT_HELP = """Export only human-approved parameters.

Sources: an assembly report directory or an approved-export JSON file.
A raw registry is refused: it has no assembled decisions, so a gate cannot be
verified against a decision, rubric version, value and binding hash. Direct
JSON inputs are reported as UNVERIFIED: approval is never inferred from a file
name, values or user-supplied claims.

For assembly folders, every approval is re-verified against the assembled
decision and the exported value, not just file hashes. This catches stale or
mistaken gate/registry/export files. It cannot catch someone who can rewrite
every file including the manifest; that would need a signature over the chain.
"""


def _state(ctx: typer.Context) -> State:
    state = ctx.obj
    if not isinstance(state, State):
        raise InputError("CLI state was not initialised.", action="Report this as a CLI bug.")
    return state


def _default_source(state: State) -> Path:
    if state.config is not None and state.config.workspace is not None:
        return state.workspace() / "reports" / "assembly"
    return Path.cwd() / "reports" / "assembly"


def _resolve_registry_path(state: State, src: Path, explicit: Path | None) -> Path | None:
    """Find a registry for metadata enrichment (never for trust)."""
    if explicit is not None:
        return explicit.expanduser().resolve()
    if src.is_dir() and (src / "manifest.json").is_file():
        manifest = load_json(src / "manifest.json", description="assembly manifest")
        recorded = (
            manifest.get("registry", {}).get("path")
            if isinstance(manifest, dict) and isinstance(manifest.get("registry"), dict)
            else None
        )
        if isinstance(recorded, str) and recorded:
            path = Path(recorded).expanduser()
            return path.resolve() if path.is_absolute() else (src / path).resolve()
    if state.config is not None:
        return state.config.resolve(state.config.paths.registry)
    return None


def _resolve_gate_path(state: State, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit.expanduser().resolve()
    if state.config is not None:
        return state.config.resolve(state.config.paths.gate)
    return None


def _records_by_id(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.is_file():
        return {}
    raw = load_json(path, description="registry")
    if not isinstance(raw, list):
        return {}
    return {r["canonical_id"]: r for r in raw if isinstance(r, dict) and r.get("canonical_id")}


def _gate_records(path: Path | None) -> dict[str, dict[str, Any]]:
    from ..artifact import _parse_gate_file

    if path is None or not path.is_file():
        return {}
    gate = _parse_gate_file(path)
    return {record.parameter: record.to_dict() for record in gate.records}


def _dossier_metadata(src: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    report_file = src / "report.json"
    if not src.is_dir() or not report_file.is_file():
        return {}, {}
    report = load_json(report_file, description="assembly report")
    if not isinstance(report, dict):
        return {}, {}
    dossiers = {
        d["parameter"]: d for d in report.get("parameters", [])
        if isinstance(d, dict) and d.get("parameter")
    }
    trace = {
        t["parameter"]: t["level"] for t in report.get("traceability", [])
        if isinstance(t, dict) and t.get("parameter")
    }
    return dossiers, trace


def export(
    ctx: typer.Context,
    format: str = typer.Option("json", "--format", help="json or pybamm."),
    source: Path | None = typer.Option(
        None, "--from", help="Assembly report directory, export JSON, or registry JSON."
    ),
    output: Path = typer.Option(..., "--output", help="Destination file."),
    gate: Path | None = typer.Option(
        None, "--gate",
        help="Legacy option; gates are verified from the assembly manifest, not a CLI override.",
    ),
    registry: Path | None = typer.Option(
        None, "--registry", help="Registry JSON supplying scientific metadata and PyBaMM names."
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing output file."),
    parameter_set: str = typer.Option("Chen2020", "--parameter-set"),
    schema_version: int = typer.Option(
        SCHEMA_V1, "--schema-version", min=SCHEMA_V1, max=SCHEMA_V2,
        help="Export artifact schema (1 = legacy default, 2 = metadata-rich).",
    ),
) -> int:
    """Write an approved parameter set to JSON or a PyBaMM-name overlay."""
    from ..artifact import build_metadata

    state = _state(ctx)
    if format not in ("json", "pybamm"):
        raise InputError("Unsupported export format.", why=f"Got {format!r}.", action="Use json or pybamm.")
    src = source.expanduser().resolve() if source is not None else _default_source(state)
    if not src.exists():
        raise InputError("Export source not found.", why=f"Expected: {src}", action="Run `parallm assemble` or pass --from.")
    export_file = src / "pybamm_export.json" if src.is_dir() else src
    if not export_file.is_file():
        raise InputError(
            "Approved export file not found.",
            why=f"Expected: {export_file}",
            action="Run `parallm assemble` to generate it.",
        )

    data: ArtifactData = read_artifact(export_file)
    explicit_gate = gate.expanduser().resolve() if gate is not None else None
    explicit_registry = registry.expanduser().resolve() if registry is not None else None
    # Raw registry sources are refused inside establish_attestation(): without
    # assembled decisions there is no decision/rubric/binding to verify against
    # any gate.  Direct JSON and v2 export artifacts remain UNVERIFIED.

    attestation = establish_attestation(
        src=src, export_file=export_file, data=data,
        claim=data.attestation_claim, explicit_registry=explicit_registry,
    )
    attestation.require_verified()

    registry_path = _resolve_registry_path(state, src, explicit_registry)
    if attestation.registry.get("path"):
        registry_path = Path(attestation.registry["path"])
    if data.source_kind == "registry":
        # A registry-list source is itself the registry; no redundant --registry.
        registry_path = src
    registry_by_id = _records_by_id(registry_path)
    dossier_by_id, trace_by_id = _dossier_metadata(src)
    gate_path = (
        Path(attestation.gate["path"])
        if attestation.gate.get("path") and attestation.level in (ATTESTED, ATTESTED_EMPTY)
        else (explicit_gate if attestation.level == ATTESTED else _resolve_gate_path(state, explicit_gate))
    )
    gate_records = (
        _gate_records(gate_path)
        if attestation.level in (ATTESTED, ATTESTED_EMPTY) else {}
    )

    source_label = str(export_file) if src.is_file() else f"{src} (attested by {attestation.basis})"
    limitations: list[str] = []
    warnings: list[str] = []
    if attestation.level == UNVERIFIED:
        limitations.append("approval status UNVERIFIED: input is not linked to a verified gate record")
        warnings.append("UNVERIFIED export: approval was not established from an ApprovalGate record")
    limitations.extend(
        note for note in attestation.notes if not note.startswith("attestation re-verified")
    )

    skipped: list[dict[str, Any]] = []
    entries: dict[str, dict[str, Any]] = {}
    for name, entry in data.entries.items():
        if entry.problem:
            skipped.append({"parameter": name, "reason": entry.problem,
                            "detail": "value is not numeric"})
            continue
        metadata = build_metadata(
            name, entry, registry_by_id=registry_by_id,
            dossier_by_id=dossier_by_id, trace_by_id=trace_by_id,
            gate_records=gate_records,
        )
        stored = entry.data.get("_stored_metadata")
        if stored:
            for key, value in stored.items():
                if key == "validation" and isinstance(value, dict):
                    merged_validation = dict(metadata["validation"])
                    merged_validation.update(value)
                    metadata["validation"] = merged_validation
                else:
                    metadata[key] = value
            # Normalise after the merge: a raw stored state must never replace
            # a canonical one or bypass the UNKNOWN guard.
            metadata["validation"]["state"] = normalise_validation_state(
                metadata["validation"].get("state")
            )
            if attestation.level in (ATTESTED, ATTESTED_EMPTY) and name in gate_records:
                metadata["approval"] = build_metadata(
                    name, entry, registry_by_id=registry_by_id,
                    dossier_by_id=dossier_by_id, trace_by_id=trace_by_id,
                    gate_records=gate_records,
                )["approval"]
            else:
                preserved = dict(stored.get("approval") or metadata["approval"])
                preserved["verified_on_export"] = False
                metadata["approval"] = preserved
        approval_state = metadata["approval"]["status"]
        validation_state = metadata["validation"]["state"]
        if approval_state == GATE_REJECTED:
            skipped.append({"parameter": name, "reason": "GATE_REJECTED",
                            "detail": "explicit human rejection in the approval gate"})
            continue
        if validation_state == VALIDATION_REJECTED:
            skipped.append({"parameter": name, "reason": "VALIDATION_REJECTED",
                            "detail": "deterministic validation state is REJECTED"})
            continue
        if validation_state == UNKNOWN:
            skipped.append({"parameter": name, "reason": "VALIDATION_UNKNOWN",
                            "detail": "unrecognised validation state; never promoted to ACCEPTED"})
            continue
        if validation_state == VALIDATION_NEEDS_REVIEW:
            if approval_state != APPROVED:
                skipped.append({"parameter": name, "reason": "NEEDS_APPROVAL",
                                "detail": "NEEDS_REVIEW requires explicit human approval"})
                continue
            metadata["validation"]["disposition"] = "approved_with_pending_validation"
            warnings.append(
                f"{name}: validation is NEEDS_REVIEW; exported only because a human approval was recorded"
            )
        if attestation.level in (ATTESTED, ATTESTED_EMPTY) and approval_state != APPROVED:
            skipped.append({"parameter": name, "reason": "NOT_APPROVED",
                            "detail": "no matching ApprovalGate record"})
            continue
        if validation_state in (NOT_RECORDED, NOT_PERFORMED, NOT_APPLICABLE):
            limitations.append(f"{name}: validation state {validation_state}; included with explicit flag")
        if metadata["calibration"]["status"] == "LITERATURE FIT REPORTED":
            limitations.append(f"{name}: origin records a literature fit; no recorded calibration report")
        names = entry.data.get("pybamm_names") or (registry_by_id.get(name) or {}).get("pybamm_names") or []
        # Numeric exports use the canonical (converted SI) value, never the raw
        # literature printing (e.g. 5.86 um -> 5.86e-06 m). Function values
        # keep their existing behaviour.
        value = entry.value
        canonical = metadata["canonical"].get("value")
        canonical_unit = metadata["canonical"].get("unit")
        if not (isinstance(canonical, (int, float)) and not isinstance(canonical, bool)):
            # No recorded canonical field: convert the raw value with its
            # stated unit deterministically. Never export the raw printing.
            from ...registry.units import to_canonical
            raw_unit = metadata.get("unit")
            if isinstance(value, (int, float)) and not isinstance(value, bool) and raw_unit:
                try:
                    canonical_unit, factor = to_canonical(str(raw_unit))
                    canonical = float(value) * factor
                except KeyError:
                    canonical = None
        if isinstance(canonical, (int, float)) and not isinstance(canonical, bool):
            value = canonical
        else:
            canonical_unit = None
        entries[name] = {
            "value": value,
            "unit": metadata["unit"],
            "canonical_unit": canonical_unit,
            "pybamm_names": list(names),
            "metadata": metadata,
        }

    n_requested = len(data.entries)
    exported_pybamm: dict[str, Any] = {}
    if entries and format == "pybamm":
        from ...pybamm_engine import installed_parameter_names

        if registry_path is None or not registry_path.is_file():
            raise ExportError(
                "A parameter registry is required for PyBaMM export.",
                why=f"No readable registry was found at {registry_path or '<not configured>'}.",
                action="Pass --registry PATH, or re-run `parallm assemble` so its manifest records an existing registry.",
            )
        from ...registry.units import pybamm_unit_suffix, to_canonical

        installed = set(installed_parameter_names(parameter_set))
        mapped: dict[str, Any] = {}
        for name, item in entries.items():
            names = item["pybamm_names"]
            if not names:
                skipped.append({"parameter": name, "reason": "NO_PYBAMM_NAME",
                                "detail": "no PyBaMM name recorded; skipped"})
                continue
            if names[0] not in installed:
                skipped.append({"parameter": name, "reason": "PYBAMM_NAME_NOT_INSTALLED",
                                "detail": f"{names[0]!r} not in installed {parameter_set}; skipped"})
                continue
            value = item["value"]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                # The canonical unit must match the unit in the PyBaMM name.
                canonical_unit = item.get("canonical_unit") or item["metadata"]["canonical"].get("unit")
                expected_suffix = pybamm_unit_suffix(names[0])
                if not isinstance(canonical_unit, str) or not canonical_unit.strip():
                    skipped.append({
                        "parameter": name, "reason": "CANONICAL_UNIT_MISSING",
                        "detail": "no canonical unit recorded for a numeric value; not exported",
                    })
                    continue
                if not expected_suffix:
                    skipped.append({
                        "parameter": name, "reason": "PYBAMM_UNIT_MISSING",
                        "detail": f"{names[0]!r} has no unit suffix for a numeric value",
                    })
                    continue
                try:
                    actual, _ = to_canonical(canonical_unit)
                    expected, _ = to_canonical(expected_suffix)
                except KeyError as exc:
                    skipped.append({
                        "parameter": name, "reason": "UNIT_UNKNOWN",
                        "detail": str(exc),
                    })
                    continue
                if actual != expected:
                    skipped.append({
                        "parameter": name, "reason": "UNIT_MISMATCH",
                        "detail": (f"canonical {canonical_unit} ({actual}) does not match "
                                   f"{names[0]} ({expected})"),
                    })
                    continue
            mapped[names[0]] = value
        # Entries stay keyed by canonical id; only the overlay uses PyBaMM names.
        exported_pybamm = mapped

    if not entries:
        if n_requested == 0:
            if src.is_dir() or (
                data.source_kind == "parallm_export" and schema_version == SCHEMA_V2
            ):
                status = STATUS_INTENTIONALLY_EMPTY
            else:
                raise ExportError(
                    "Direct JSON input contains no parameter values.",
                    why=f"Nothing could be exported from {export_file}.",
                    action="Pass a populated assembly export or registry file.",
                )
        else:
            status = STATUS_EMPTY_AFTER_FILTERING
            raise ExportError(
                "Export would be empty after filtering; nothing was written.",
                why=f"All {n_requested} input parameter(s) were skipped: "
                    + "; ".join(s["reason"] for s in skipped),
                action="Fix the validation/approval state or pass a different source; use --format json for canonical ids.",
            )
    else:
        status = STATUS_PARTIAL if (skipped or limitations or warnings) else STATUS_COMPLETE

    if format == "pybamm":
        if not exported_pybamm:
            raise ExportError(
                "PyBaMM export would be empty; nothing was written.",
                why="No approved value mapped to an installed parameter name.",
                action="Pass --registry with the records used by `parallm assemble`.",
            )
        content = "PARAMETERS = " + repr(exported_pybamm) + "\n"
    else:
        content = write_artifact_payload(
            version=schema_version, source_label=source_label, attestation=attestation,
            source_path=str(export_file), source_kind=data.source_kind,
            source_sha256=sha256(export_file),
            status=status, entries=entries, skipped=skipped, warnings=warnings,
            limitations=limitations, migrated_from=data.migrated_from,
            rubric_version=(dossier_by_id or {}).get("rubric_version"),
            validation_policy="reject_rejected|flag_others",
            tool_version=tool_version(), generated=datetime.now(timezone.utc).isoformat(),
            python_version=platform.python_version(),
        )

    n_exported = len(exported_pybamm) if format == "pybamm" else len(entries)
    n_skipped = len(skipped)
    destination = output.expanduser().resolve()
    if destination.exists() and not overwrite:
        raise OverwriteError(
            "Output file already exists.",
            why=f"Refusing to overwrite: {destination}",
            action="Choose a different --output path or pass --overwrite explicitly.",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")

    if not state.quiet and not state.json_mode:
        section(state.console, "EXPORT COMPLETE")
        kv(
            state.console,
            (
                ("Format", format),
                ("Source", source_label),
                ("Trust", attestation.level),
                ("Status", status),
                ("Exported", n_exported),
                ("Skipped", n_skipped),
                ("Completeness", "COMPLETE" if status == STATUS_COMPLETE else "PARTIAL"),
                ("Output", str(destination)),
            ),
        )
        if skipped:
            table(state.console, ("SKIPPED PARAMETER", "REASON"),
                  [(s["parameter"], s["reason"]) for s in skipped])
        if limitations:
            table(state.console, ("LIMITATION",), [(text,) for text in limitations])
        for warning in warnings:
            notice(state.console, warning, "warn")
        if status in (STATUS_INTENTIONALLY_EMPTY, STATUS_EMPTY_UNVERIFIED):
            notice(state.console, "INTENTIONALLY EMPTY: no approval gate; no parameters exported.", "warn")
        notice(state.console, "Only human-approved parameters are exported from attested sources.")
    state.emit(
        {
            "format": format,
            "source": source_label,
            "output": str(destination),
            "parameters": (
                exported_pybamm if format == "pybamm" else
                {name: item["value"] for name, item in entries.items()}
            ),
            "schema_version": schema_version,
            "attestation": attestation.to_dict(),
            "export_status": status,
            "warnings": warnings,
            "n_requested": n_requested,
            "n_exported": n_exported,
            "skipped": n_skipped,
            "skipped_details": skipped,
            "complete": status == STATUS_COMPLETE,
            "limitations": limitations,
        }
    )
    return 0
