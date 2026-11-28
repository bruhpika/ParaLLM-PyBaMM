"""Trust verification and schema handling for ParaLLM JSON export artifacts.

This module owns the artifact-level trust decision and the v1/v2 artifact
schema.  Approval is never inferred from a file's name, shape, values or
user-supplied claims: it is established from an ``ApprovalGate`` record and
verified against the *decision it claims to approve* by one shared verifier
(``assembly.gate.verify_gate_bindings``).  That verifier checks parameter,
decision, rubric version, recomputed binding hash and exported value.

A raw registry has no assembled decisions, so it cannot be verified and is
refused.  For assembly folders, file hashes are checked first and then the
bindings and exported values are re-verified from the registry and dossiers.
This protects against stale or mistaken gate/registry/export files (e.g. a
gate left over from an earlier run, or a value edited after approval).  It
cannot protect against an actor who can rewrite *every* file, including the
assembly manifest and gate; that would require a cryptographic signature over
the whole chain, which this prototype does not implement.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..assembly.gate import ApprovalGate, verify_gate_bindings
from ..registry.model import sha256_text
from .errors import ExportError, InputError
from .inputs import load_json, sha256

SCHEMA_V1 = 1
SCHEMA_V2 = 2
SUPPORTED_SCHEMA_VERSIONS = (SCHEMA_V1, SCHEMA_V2)

NOT_RECORDED = "NOT_RECORDED"
NOT_PERFORMED = "NOT_PERFORMED"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNKNOWN = "UNKNOWN"

ATTESTED = "ATTESTED"
ATTESTED_EMPTY = "ATTESTED_EMPTY"
UNVERIFIED = "UNVERIFIED"
UNKNOWN_ATTESTATION = "UNKNOWN"

STATUS_COMPLETE = "COMPLETE"
STATUS_PARTIAL = "PARTIAL"
STATUS_INTENTIONALLY_EMPTY = "INTENTIONALLY_EMPTY"
STATUS_EMPTY_AFTER_FILTERING = "EMPTY_AFTER_FILTERING"
STATUS_EMPTY_UNVERIFIED = "EMPTY_UNVERIFIED"

VALIDATION_ACCEPTED = "ACCEPTED"
VALIDATION_NEEDS_REVIEW = "NEEDS_REVIEW"
VALIDATION_REJECTED = "REJECTED"

RECOGNISED_VALIDATION_STATES = frozenset({
    VALIDATION_ACCEPTED, VALIDATION_NEEDS_REVIEW, VALIDATION_REJECTED,
    NOT_RECORDED, NOT_PERFORMED, NOT_APPLICABLE, UNKNOWN,
})


def normalise_validation_state(value: Any) -> str:
    """Canonicalise a validation state from any metadata source.

    Null and absent values are NOT_RECORDED. Only explicitly recognised states
    survive; every other string, type or unsupported value becomes UNKNOWN so
    that it cannot be mistaken for an accepted state by export policy.
    """
    if value is None:
        return NOT_RECORDED
    if isinstance(value, str) and value in RECOGNISED_VALIDATION_STATES:
        return value
    return UNKNOWN

APPROVED = "APPROVED"
GATE_REJECTED = "REJECTED"
NOT_APPROVED = "NOT_RECORDED"

STORED_METADATA_KEYS = (
    "origin", "original", "canonical", "source", "evidence", "validation",
    "calibration", "conditions", "notes", "review_required", "approval",
)


@dataclass
class Attestation:
    """Artifact-level trust decision and the evidence supporting it."""

    level: str
    basis: str
    gate: dict[str, Any] = field(default_factory=dict)
    registry: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    manifest_path: str | None = None
    artifact_sha256: str | None = None
    downgraded_from: str | None = None
    reported_claims: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "basis": self.basis,
            "gate": self.gate,
            "registry": self.registry,
            "failures": list(self.failures),
            "notes": list(self.notes),
            "manifest_path": self.manifest_path,
            "artifact_sha256": self.artifact_sha256,
            "downgraded_from": self.downgraded_from,
            "reported_claims": self.reported_claims,
        }

    def require_verified(self) -> None:
        """Fail closed when attestation data is contradictory or corrupted."""
        if self.level == UNKNOWN_ATTESTATION:
            raise ExportError(
                "Export attestation failed; nothing was written.",
                why="; ".join(self.failures) or "contradictory attestation data",
                action=(
                    "Re-run `parallm assemble` to regenerate a consistent manifest and export, "
                    "or pass a direct JSON file to export it as UNVERIFIED."
                ),
            )


@dataclass
class ArtifactEntry:
    """One normalised parameter entry from any supported input shape."""

    data: dict[str, Any]
    problem: str | None = None

    @property
    def value(self) -> Any:
        return self.data.get("value")

    @property
    def unit(self) -> Any:
        return self.data.get("unit", NOT_RECORDED)


@dataclass
class ArtifactData:
    """Normalised input with its declared schema version and source kind."""

    schema_version: int
    entries: dict[str, ArtifactEntry]
    source_kind: str
    raw: Any
    attestation_claim: dict[str, Any] | None = None
    migrated_from: int | None = None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _load_json_strict(path: Path) -> Any:
    """Load JSON, rejecting duplicate object keys instead of last-wins."""
    def _no_duplicates(pairs):
        seen: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                raise InputError(
                    f"Duplicate JSON key {key!r} in {path}.",
                    action="Provide a JSON object with unique keys.",
                )
            seen[key] = value
        return seen

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates)
    except InputError:
        raise
    except (OSError, ValueError) as exc:
        raise InputError(f"Could not parse {path}: {exc}", action="Provide valid JSON.") from exc


def _check_numeric(value: Any, name: str = "parameter") -> None:
    if isinstance(value, bool):
        raise InputError(
            f"Boolean value for {name!r} is not a numeric parameter value.",
            action="Use a finite number.",
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise InputError(
            f"Non-finite value for {name!r} is not a valid parameter value.",
            action="Use a finite number; NaN and Infinity are rejected.",
        )


def _normalise_entry(value: Any) -> ArtifactEntry:
    if isinstance(value, bool) or (
        isinstance(value, float) and not math.isfinite(value)
    ):
        _check_numeric(value)
    if isinstance(value, dict) and "value" in value:
        _check_numeric(value["value"], str(value.get("parameter_name", "parameter")))
    if _is_number(value):
        return ArtifactEntry(
            {"value": value, "unit": NOT_RECORDED, "pybamm_names": []}
        )
    if isinstance(value, dict) and _is_number(value.get("value")):
        data = dict(value)
        data.setdefault("unit", NOT_RECORDED)
        data.setdefault("pybamm_names", [])
        stored = {key: data[key] for key in STORED_METADATA_KEYS if key in data}
        if stored:
            data["_stored_metadata"] = stored
        return ArtifactEntry(data)
    return ArtifactEntry({"raw": value, "unit": NOT_RECORDED, "pybamm_names": []},
                         problem="NON_NUMERIC")


def _check_version(raw: dict[str, Any]) -> int:
    version = raw.get("schema_version", SCHEMA_V1)
    if isinstance(version, bool) or not isinstance(version, int):
        raise InputError(
            f"Unsupported export schema version: {version!r}.",
            why="schema_version must be an integer.",
            action="Use 1 or 2.",
        )
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise InputError(
            f"Unsupported export schema version: {version!r}.",
            why=f"This build supports schema versions {SUPPORTED_SCHEMA_VERSIONS}.",
            action="Export with a supported ParaLLM version or pass a v1/v2 artifact.",
        )
    return int(version)


def read_artifact(path: Path) -> ArtifactData:
    """Read a v1 flat dict, a v1/v2 ParaLLM artifact, or a registry list."""
    raw = _load_json_strict(path)
    if isinstance(raw, list):
        entries: dict[str, ArtifactEntry] = {}
        for record in raw:
            if not isinstance(record, dict):
                continue
            canonical = record.get("canonical_id")
            if not canonical:
                continue
            data = {
                "value": record.get("value"),
                "unit": record.get("value_unit", NOT_RECORDED),
                "pybamm_names": list(record.get("pybamm_names") or []),
                "origin": record.get("status", NOT_RECORDED),
                "validation": {
                    "state": normalise_validation_state(record.get("validation_state")),
                    "results": NOT_PERFORMED,
                    "basis": "registry.validation_state",
                },
                "conditions": record.get("conditions", NOT_RECORDED),
                "_registry_record": record,
            }
            entry = ArtifactEntry(data)
            _check_numeric(entry.value, str(canonical))
            if not _is_number(entry.value):
                entry.problem = "NON_NUMERIC"
            key = str(canonical)
            if key in entries:
                raise InputError(
                    f"Duplicate canonical parameter id {key!r} in registry list.",
                    action="Provide each canonical id exactly once.",
                )
            entries[key] = entry
        return ArtifactData(SCHEMA_V1, entries, "registry", raw)

    if not isinstance(raw, dict):
        raise InputError(
            "Export input must be an object or a list.",
            why=f"Found {type(raw).__name__} in {path}.",
            action="Pass a registry list, a v1 value mapping, or a ParaLLM export artifact.",
        )

    version = _check_version(raw)
    artifact_block = raw.get("artifact") if isinstance(raw.get("artifact"), dict) else {}
    embedded = artifact_block.get("attestation")
    claim = embedded if isinstance(embedded, dict) else None
    migrated = artifact_block.get("migrated_from")
    if migrated is None and version == SCHEMA_V1 and "parameters" in raw:
        migrated = SCHEMA_V1
    if "parameters" in raw and isinstance(raw["parameters"], dict):
        params = raw["parameters"]
    else:
        params = raw
    entries = {str(name): _normalise_entry(value) for name, value in params.items()}
    source_kind = "parallm_export" if ("parameters" in raw and version == SCHEMA_V2) else "direct_json"
    return ArtifactData(version, entries, source_kind, raw, claim, migrated)


def _resolve_path(value: str | Path | None, base: Path) -> Path | None:
    """Resolve a recorded path; refuse relative traversal segments.

    Absolute paths recorded by `parallm assemble` are preserved. Symlinks are
    followed by ``Path.resolve()``; hashes verify content, not file identity.
    """
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute() and ".." in path.parts:
        return None
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()


def _parse_gate_file(path: Path):
    """Parse a gate file, mapping domain errors to a stable CLI error code."""
    from ..assembly import ApprovalGate, GateValidationError

    try:
        return ApprovalGate.from_dict(load_json(path, description="approval gate"))
    except GateValidationError as exc:
        raise InputError(
            "Approval gate is invalid.",
            why=str(exc),
            action="Provide exactly one well-formed approval record per parameter.",
        ) from exc


def _gate_approval(
    manifest_gate: dict[str, Any], base: Path
) -> tuple[ApprovalGate, Path | None, str | None]:
    """Load and hash-check the gate, returning the parsed gate for verification.

    The returned gate is *not* trust by itself; every record must still be
    checked against the assembled decision with ``verify_gate_bindings``.
    """
    path = _resolve_path(manifest_gate.get("path"), base)
    if path is None or not path.is_file():
        raise ExportError(
            "Assembly gate file is missing; attestation cannot be verified.",
            why=f"Expected: {path}",
            action="Restore the gate file recorded in the manifest or re-run `parallm assemble`.",
        )
    recorded_hash = manifest_gate.get("sha256")
    actual_hash = sha256(path)
    if recorded_hash and recorded_hash != actual_hash:
        raise ExportError(
            "Assembly gate file was modified after assembly.",
            why=f"manifest={recorded_hash}, actual={actual_hash} ({path})",
            action="Re-run `parallm assemble` with the current gate; nothing was written.",
        )
    gate = _parse_gate_file(path)
    if not isinstance(gate, ApprovalGate):  # defensive: parser contract
        raise ExportError("Assembly gate file could not be parsed.", action="Provide a valid gate.")
    return gate, path, actual_hash


def _dossiers_from_assembly(src: Path) -> dict[str, dict[str, Any]]:
    """Read the assembly report's dossiers keyed by parameter, if available."""
    report_file = src / "report.json"
    if not report_file.is_file():
        return {}
    try:
        report = load_json(report_file, description="assembly report")
    except (InputError, OSError, ValueError):
        return {}
    if not isinstance(report, dict) or not isinstance(report.get("parameters"), list):
        return {}
    return {
        str(d["parameter"]): d for d in report["parameters"]
        if isinstance(d, dict) and d.get("parameter")
    }


def _verify_exported_bindings(
    *,
    gate: ApprovalGate,
    dossiers: dict[str, dict[str, Any]],
    exported: dict[str, Any],
    rubric_version: str | None,
) -> tuple[set[str], list[str]]:
    """Re-verify bindings and exported values; return (approved, block reasons).

    Dossiers are the authoritative decision records produced by assembly; a
    registry record on its own is never a decision.  Pass only the dossiers
    that have gate records: ungated parameters are simply not exported.  The
    caller separately checks that the assembly report exists and is readable.
    """
    result = verify_gate_bindings(
        gate, dossiers, exported_values=exported,
        expected_rubric_version=rubric_version,
    )
    return result.approved, [f"{name}: {reason}" for name, reason in result.reasons.items()]


def _verify_manifest(
    manifest: dict[str, Any],
    src: Path,
    export_file: Path,
    data: ArtifactData,
    explicit_registry: Path | None,
) -> Attestation:
    failures: list[str] = []
    notes: list[str] = []
    gate_info: dict[str, Any] = {}
    registry_info: dict[str, Any] = {}

    recorded_artifact_hash = (manifest.get("outputs_sha256") or {}).get("pybamm_export.json")
    artifact_hash = sha256(export_file)
    if recorded_artifact_hash and recorded_artifact_hash != artifact_hash:
        failures.append("export artifact SHA-256 does not match the assembly manifest")
    elif not recorded_artifact_hash:
        notes.append("manifest has no export artifact hash (pre-v2); attestation downgraded")

    base = src if src.is_dir() else src.parent
    approved: set[str] = set()
    manifest_gate = manifest.get("gate") or {}
    gate_path: Path | None = None
    gate_hash: str | None = None
    if manifest_gate.get("path"):
        try:
            gate, gate_path, gate_hash = _gate_approval(manifest_gate, base)
        except ExportError as exc:
            failures.append(str(exc.what))
            failures.extend(str(exc.why or ""))
        else:
            dossiers = _dossiers_from_assembly(src)
            rubric_version = manifest.get("rubric_version")
            try:
                raw_export = json.loads(export_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw_export = {}
            exported = raw_export if isinstance(raw_export, dict) else {}
            if not dossiers:
                failures.append(
                    "assembly report is missing or unreadable; decisions cannot be verified"
                )
            # Only parameters with a gate record can be approved; dossiers
            # without one are simply not exported and are not failures.
            gated = {
                name: d for name, d in dossiers.items()
                if name in {r.parameter for r in gate.records}
            }
            approved, reasons = _verify_exported_bindings(
                gate=gate, dossiers=gated,
                exported=exported, rubric_version=rubric_version,
            )
            if manifest_gate.get("n_approved") != len(gate.approved_parameters()):
                failures.append("manifest n_approved disagrees with the gate record")
            if reasons:
                failures.extend(f"binding verification failed: {reason}" for reason in reasons)
            missing = [name for name in data.entries if name not in approved]
            if missing:
                failures.append(f"export contains parameters without verified gate approval: {missing}")
            gate_info = {
                "path": str(gate_path) if gate_path else None,
                "sha256": gate_hash,
                "n_approved": len(gate.approved_parameters()),
                "n_verified": len(approved),
                "n_approved_in_manifest": manifest_gate.get("n_approved"),
            }
    elif data.entries:
        notes.append("manifest records no gate; attestation downgraded to UNVERIFIED")

    manifest_resolution = manifest.get("resolutions") or {}
    resolution_path = _resolve_path(manifest_resolution.get("path"), base)
    if resolution_path is not None:
        if not resolution_path.is_file():
            failures.append("human resolution file recorded in the manifest is missing")
        elif manifest_resolution.get("sha256") and (
            sha256(resolution_path) != manifest_resolution["sha256"]
        ):
            failures.append("human resolution file was modified after assembly")

    manifest_registry = manifest.get("registry") or {}
    registry_path = _resolve_path(manifest_registry.get("path"), base)
    if registry_path is None or not registry_path.is_file():
        notes.append("registry recorded in the manifest is missing; attestation downgraded")
    else:
        actual = sha256(registry_path)
        recorded = manifest_registry.get("sha256")
        if recorded and recorded != actual:
            failures.append("registry SHA-256 does not match the assembly manifest")
        if explicit_registry is not None and explicit_registry.resolve() != registry_path:
            failures.append("--registry disagrees with the registry recorded in the manifest")
        registry_info = {"path": str(registry_path), "sha256": actual}

    def _with(**kwargs):
        kwargs.setdefault("manifest_path", str(src / "manifest.json"))
        kwargs.setdefault("artifact_sha256", artifact_hash)
        return Attestation(**kwargs)

    if failures:
        return _with(level=UNKNOWN_ATTESTATION, basis="manifest+gate+registry",
                     gate=gate_info, registry=registry_info, failures=failures, notes=notes)
    if notes:
        return _with(level=UNVERIFIED, basis="manifest+gate+registry",
                     gate=gate_info, registry=registry_info, notes=notes,
                     downgraded_from=ATTESTED)
    level = ATTESTED_EMPTY if not data.entries else ATTESTED
    return _with(level=level, basis="manifest+gate+registry",
                 gate=gate_info, registry=registry_info)


def derived_content_digest(payload: dict[str, Any]) -> str:
    """Stable digest of the derived v2 artifact, excluding the digest itself.

    Volatile presentation fields and verification notes are excluded so a
    round-trip is stable; scientific values, metadata, export status and the
    verification evidence are included. This is an integrity check, not a
    cryptographic signature or proof of origin.
    """
    block = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    attestation = block.get("attestation") if isinstance(block.get("attestation"), dict) else {}
    stable_attestation = {
        key: value for key, value in attestation.items()
        if key not in ("derived_content_sha256", "notes")
    }
    projection = {
        "schema_version": payload.get("schema_version"),
        "parameters": payload.get("parameters"),
        "export": payload.get("export"),
        "approved_only": payload.get("approved_only"),
        "approval_basis": payload.get("approval_basis"),
        "policy": block.get("policy"),
        "attestation": stable_attestation,
    }
    return sha256_text(json.dumps(projection, sort_keys=True, default=str))


def _reverify_claim(
    claim: dict[str, Any], export_file: Path, raw_payload: dict[str, Any]
) -> Attestation:
    """Re-verify a v2 attestation against its original chain and content."""
    claimed_level = str(claim.get("level", UNVERIFIED))
    gate = dict(claim.get("gate") or {})
    registry = dict(claim.get("registry") or {})
    downgraded = Attestation(
        UNVERIFIED, "unverifiable-reexport", gate, registry,
        downgraded_from=claimed_level,
        reported_claims={"attestation": claim},
    )

    recorded_digest = claim.get("derived_content_sha256")
    if not isinstance(recorded_digest, str) or not recorded_digest:
        downgraded.notes.append("v2 artifact has no derived content digest")
        return downgraded
    if recorded_digest != derived_content_digest(raw_payload):
        downgraded.notes.append("v2 artifact content does not match its recorded digest")
        return downgraded

    manifest_path = _resolve_path(claim.get("manifest_path"), export_file.parent)
    if manifest_path is None or not manifest_path.is_file():
        downgraded.notes.append("manifest for the claimed attestation is not available locally")
        return downgraded
    try:
        manifest = load_json(manifest_path, description="attested manifest")
        original_artifact = manifest_path.parent / "pybamm_export.json"
        current_values = raw_payload.get("parameters") or {}
        entries = {
            str(name): ArtifactEntry(value if isinstance(value, dict) else {"value": value})
            for name, value in current_values.items()
        } if isinstance(current_values, dict) else {}
        verified = _verify_manifest(
            manifest, manifest_path.parent, original_artifact,
            ArtifactData(SCHEMA_V2, entries, "parallm_export", raw_payload), None,
        )
    except (ExportError, InputError, OSError, ValueError) as exc:
        downgraded.notes.append(f"original chain could not be verified: {type(exc).__name__}: {exc}")
        return downgraded
    if verified.level not in (ATTESTED, ATTESTED_EMPTY) or verified.failures:
        downgraded.notes.append(
            "original chain verification failed: " + "; ".join(verified.failures or [verified.level])
        )
        return downgraded

    # The derived artifact must still describe the same approved values.
    try:
        original_values = json.loads(original_artifact.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        downgraded.notes.append("original assembly artifact is unreadable")
        return downgraded
    current = raw_payload.get("parameters") or {}
    if not isinstance(original_values, dict) or not isinstance(current, dict):
        downgraded.notes.append("artifact value mappings are not objects")
        return downgraded

    def _numeric(value: Any) -> bool:
        if isinstance(value, dict):
            value = value.get("value")
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    for name, value in original_values.items():
        if name not in current or not _numeric(current[name]) or not _numeric(value):
            downgraded.notes.append(f"derived artifact no longer matches original parameter {name!r}")
            return downgraded
        derived_value = current[name]["value"] if isinstance(current[name], dict) else current[name]
        if float(derived_value) != float(value):
            downgraded.notes.append(f"derived artifact value changed for parameter {name!r}")
            return downgraded
    if set(current) != set(original_values):
        downgraded.notes.append("derived artifact parameters differ from the original artifact")
        return downgraded

    # Only preserve an attested claim; never upgrade an unverified one.
    if claimed_level not in (ATTESTED, ATTESTED_EMPTY):
        downgraded.notes.append("embedded claim was not attested; no trust upgrade performed")
        return downgraded

    verified.notes = ["attestation re-verified on re-export"]
    return verified


def establish_attestation(
    *,
    src: Path,
    export_file: Path,
    data: ArtifactData,
    claim: dict[str, Any] | None,
    explicit_registry: Path | None,
) -> Attestation:
    """Establish the artifact trust level from verifiable evidence only."""
    if claim is not None:
        result = _reverify_claim(
            claim, export_file, data.raw if isinstance(data.raw, dict) else {}
        )
        if isinstance(data.raw, dict):
            for key in ("approved_only", "attestation", "approval", "trust"):
                if key in data.raw:
                    result.reported_claims[key] = data.raw[key]
        return result

    if src.is_dir():
        manifest_file = src / "manifest.json"
        if manifest_file.is_file():
            manifest = load_json(manifest_file, description="assembly manifest")
            if not isinstance(manifest, dict):
                return Attestation(UNKNOWN_ATTESTATION, "manifest", failures=["manifest is not an object"])
            return _verify_manifest(manifest, src, export_file, data, explicit_registry)
        return Attestation(UNVERIFIED, "none", notes=["no manifest in the source directory"])

    if isinstance(data.raw, list):
        # A raw registry carries values but no assembled decisions, rubric
        # version or binding inputs.  There is nothing deterministically
        # verifiable against a gate, so a direct registry export is refused
        # rather than attested on the strength of a gate file alone.
        raise ExportError(
            "A raw registry cannot be exported: it has no assembled decisions to verify.",
            why=(
                f"Source {src} is a registry list. A gate only records a human's "
                "claim; without assembly dossiers the decision, rubric version "
                "and binding hash cannot be recomputed and checked."
            ),
            action=(
                "Run `parallm assemble --target ... --registry ... --gate ...` and "
                "pass the assembly folder with `--from`. Its manifest binds each "
                "approval to a specific decision and value, which export re-verifies."
            ),
        )

    claims: dict[str, Any] = {}
    if isinstance(data.raw, dict):
        for key in ("approved_only", "attestation", "approval", "trust"):
            if key in data.raw:
                claims[key] = data.raw[key]
    return Attestation(UNVERIFIED, "none", notes=["direct JSON input; approval cannot be established"],
                       reported_claims=claims)


def _sentinel(value: Any, kind: str = NOT_RECORDED) -> Any:
    return kind if value is None else value


def calibration_state(record: dict[str, Any] | None, fit: dict[str, Any] | None = None) -> str:
    """Shared calibration vocabulary (kept in sync with the CLI commands)."""
    if fit is not None:
        return "SYNTHETIC FIT RECORDED"
    if record and record.get("status") == "CALIBRATED":
        return "LITERATURE FIT REPORTED"
    return "NOT CALIBRATED"


def build_metadata(
    name: str,
    entry: ArtifactEntry,
    *,
    registry_by_id: dict[str, dict[str, Any]],
    dossier_by_id: dict[str, dict[str, Any]],
    trace_by_id: dict[str, str],
    gate_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Assemble available scientific metadata without inventing any field."""
    record = dict(entry.data.get("_registry_record") or registry_by_id.get(name) or {})
    dossier = dict(dossier_by_id.get(name) or {})
    evidence = record.get("evidence") or {}
    source = evidence.get("source") or {}
    d_evidence = dossier.get("evidence") or {}
    approval_record = gate_records.get(name) or {}

    # An assembled dossier describes the SELECTED candidate. The registry's
    # operative record may be a different value (a conflict); it must never
    # supply values or provenance for an approved export.
    selected = dossier.get("selected") or {}
    literature = dossier.get("literature_value") or {}
    unit = entry.unit
    if unit == NOT_RECORDED and selected.get("unit") is not None:
        unit = selected["unit"]
    if unit == NOT_RECORDED and record.get("value_unit") is not None:
        unit = record["value_unit"]
    if dossier:
        canonical_value = selected.get("canonical_value", NOT_RECORDED)
        canonical_unit = selected.get("canonical_unit", NOT_RECORDED)
        original_value = literature.get("as_printed", selected.get("value", NOT_RECORDED))
        original_unit = literature.get("as_printed_unit", selected.get("unit", NOT_RECORDED))
        origin_status = literature.get("status", record.get("status", NOT_RECORDED))
    else:
        canonical_value = record.get("normalized_value", NOT_RECORDED)
        canonical_unit = record.get("normalized_value_unit", NOT_RECORDED)
        if record:
            original_value = record.get("value", NOT_RECORDED)
            original_unit = record.get("value_unit", NOT_RECORDED)
            origin_status = record.get("status", NOT_RECORDED)
        else:
            # Direct input: its own value/unit are the only available original.
            original_value = entry.value
            original_unit = entry.unit
            origin_status = NOT_RECORDED

    verification_state = d_evidence.get("quote_verified")
    if verification_state is True:
        quote_verification = "verified"
    elif verification_state is False:
        quote_verification = "failed"
    elif d_evidence.get("quote_present"):
        quote_verification = NOT_PERFORMED
    else:
        quote_verification = NOT_APPLICABLE

    trace_level = trace_by_id.get(name)
    if not trace_level and dossier:
        from ..assembly.dossier import check_traceability

        trace_level = check_traceability(dossier)[0]

    validation_state = normalise_validation_state(record.get("validation_state"))

    if approval_record:
        approval_info = {
            "status": APPROVED if approval_record.get("approved") else GATE_REJECTED,
            "decision": _sentinel(approval_record.get("decision")),
            "approver": _sentinel(approval_record.get("approver")),
            "timestamp": _sentinel(approval_record.get("timestamp")),
            "rubric_version": _sentinel(approval_record.get("rubric_version")),
            "note": _sentinel(approval_record.get("note"), ""),
        }
    else:
        approval_info = {
            "status": NOT_APPROVED,
            "decision": NOT_RECORDED,
            "approver": NOT_RECORDED,
            "timestamp": NOT_RECORDED,
            "rubric_version": NOT_RECORDED,
            "note": "",
        }

    conditions = record.get("conditions") or dossier.get("conditions") or NOT_RECORDED
    return {
        "origin": _sentinel(origin_status, NOT_RECORDED),
        "original": {"value": _sentinel(original_value, NOT_RECORDED),
                     "unit": _sentinel(original_unit, NOT_RECORDED)},
        "canonical": {"value": _sentinel(canonical_value), "unit": _sentinel(canonical_unit)},
        "unit": _sentinel(unit),
        "source": {
            "document_id": _sentinel(source.get("document_id") or d_evidence.get("document")
                                      or d_evidence.get("source_id")),
            "doi_or_url": _sentinel(source.get("doi_or_url")),
            "locator": _sentinel(source.get("locator") or d_evidence.get("locator")),
            "page": _sentinel(source.get("page") or d_evidence.get("page"), NOT_APPLICABLE),
            "quote": _sentinel(source.get("quote") or d_evidence.get("quote"), NOT_APPLICABLE),
            "char_start": _sentinel(source.get("char_start"), NOT_APPLICABLE),
            "char_end": _sentinel(source.get("char_end"), NOT_APPLICABLE),
        },
        "evidence": {
            "traceability": _sentinel(trace_level, NOT_PERFORMED),
            "quote_present": bool(d_evidence.get("quote_present") or source.get("quote")),
            "quote_verification": quote_verification,
            "review_required": dossier.get("review_required", NOT_RECORDED),
        },
        "validation": {
            "state": validation_state,
            "results": NOT_PERFORMED,
            "basis": "registry.validation_state" if "validation_state" in record else NOT_RECORDED,
        },
        "approval": approval_info,
        "calibration": {
            "status": calibration_state(record or None),
            "basis": "origin metadata; no recorded fit report" if record else NOT_RECORDED,
        },
        "conditions": conditions,
        "notes": list(record.get("notes") or []),
    }


def write_artifact_payload(
    *,
    version: int,
    source_label: str,
    source_path: str,
    source_kind: str,
    source_sha256: str,
    attestation: Attestation,
    status: str,
    entries: dict[str, dict[str, Any]],
    skipped: list[dict[str, Any]],
    warnings: list[str],
    limitations: list[str],
    migrated_from: int | None,
    rubric_version: str | None,
    validation_policy: str,
    tool_version: str,
    generated: str,
    python_version: str,
) -> str:
    """Render a v1 (legacy) or v2 (metadata-rich) export artifact."""
    n_requested = len(entries) + len(skipped)
    n_exported = len(entries)
    approved_only = bool(
        entries
        and attestation.level in (ATTESTED, ATTESTED_EMPTY)
        and all(item["metadata"]["approval"]["status"] == APPROVED for item in entries.values())
    )
    if version == SCHEMA_V1:
        payload = {
            "schema_version": SCHEMA_V1,
            "source": source_label,
            "approved_only": approved_only,
            "parameter_set": None,
            "complete": bool(entries) and not limitations,
            "n_requested": n_requested,
            "parameters": {
                name: {
                    "value": item["value"],
                    "unit": item["metadata"]["unit"],
                    "pybamm_names": item["pybamm_names"],
                }
                for name, item in entries.items()
            },
            "limitations": list(limitations),
        }
        return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"

    payload = {
        "schema_version": SCHEMA_V2,
        "artifact": {
            "kind": "parallm.parameter_export",
            "generated": generated,
            "generator": {"name": "parallm-pybamm", "version": tool_version, "python": python_version},
            "migrated_from": migrated_from,
            "source": {"path": source_path, "kind": source_kind, "content_sha256": source_sha256},
            "attestation": attestation.to_dict(),
            "reported_claims": attestation.reported_claims,
            "policy": {
                "approval_source": "gate",
                "validation_policy": validation_policy,
                "missing_metadata": "preserve_sentinel",
            },
            "rubric_version": rubric_version,
        },
        "export": {
            "status": status,
            "n_requested": n_requested,
            "n_exported": n_exported,
            "n_skipped": len(skipped),
            "n_rejected_validation": sum(
                1 for item in skipped if item.get("reason") == "VALIDATION_REJECTED"
            ),
            "skipped": skipped,
            "warnings": warnings,
            "limitations": limitations,
        },
        "approved_only": approved_only,
        "approval_basis": (
            attestation.basis if approved_only else
            ("not_applicable" if not entries else "unverified")
        ),
        "parameter_set": None,
        "parameters": {
            name: {
                "value": item["value"],
                "unit": item["metadata"]["unit"],
                "pybamm_names": item["pybamm_names"],
                **{
                    key: value for key, value in item["metadata"].items()
                    if key not in ("unit",)
                },
            }
            for name, item in entries.items()
        },
    }
    payload["artifact"]["attestation"]["derived_content_sha256"] = derived_content_digest(payload)
    return json.dumps(payload, indent=2, sort_keys=True, default=str, allow_nan=False) + "\n"
