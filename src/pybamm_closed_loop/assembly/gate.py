"""Human approval gate for assembled parameter decisions (rule 10).

The assembly engine produces *decision support*. A parameter only enters the
approved set after a human approves the decision, and the approval records
which rubric version produced it.

An approval is bound to the exact decision it approves: parameter, decision,
rubric version and a deterministic hash of the selected value, unit and
source. A gate file missing that binding is rejected, never silently upgraded.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


def binding_sha256(dossier: Mapping[str, Any]) -> str:
    """Deterministic hash of the value/unit/source bound to an approval.

    The projection is explicit and minimal so the digest can be recomputed
    from a dossier in any process. ``None`` values are preserved as nulls;
    dictionaries and lists are serialised with sorted keys. Nothing is
    normalised, coerced or guessed.
    """
    selected = dossier.get("selected") or {}
    evidence = dossier.get("evidence") or {}
    projection = {
        "parameter": dossier.get("parameter"),
        "value": selected.get("value"),
        "unit": selected.get("unit"),
        "canonical_value": selected.get("canonical_value"),
        "canonical_unit": selected.get("canonical_unit"),
        "source_id": evidence.get("source_id") or evidence.get("document"),
        "locator": evidence.get("locator"),
        "page": evidence.get("page"),
        "quote": evidence.get("quote"),
    }
    canonical = json.dumps(projection, sort_keys=True, default=str, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class ApprovalRecord:
    """One recorded human approval (or rejection) of a decision."""

    parameter: str
    decision: str
    approved: bool
    approver: str
    rubric_version: str
    binding_sha256: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "decision": self.decision,
            "approved": self.approved,
            "approver": self.approver,
            "rubric_version": self.rubric_version,
            "binding_sha256": self.binding_sha256,
            "timestamp": self.timestamp,
            "note": self.note,
        }


class GateValidationError(ValueError):
    """Raised when a gate payload is malformed, stale or contradictory."""


def validate_gate_records(payload: Any) -> list[ApprovalRecord]:
    """Validate and build gate records with a single, order-independent policy.

    Duplicate parameter ids are rejected for this release, including identical
    decisions: approval history and revision semantics are out of scope, and
    first/last-record-wins would make approval depend on array order.

    Every record must carry the ``binding_sha256`` computed from the decision
    it approves. Legacy records without it are rejected with an explicit
    message; there is no silent upgrade path. A REJECT decision can only be
    recorded as a rejection (``approved=False``).
    """
    if not isinstance(payload, dict):
        raise GateValidationError("gate payload must be a JSON object")
    items = payload.get("approvals")
    if not isinstance(items, list):
        raise GateValidationError("gate payload must contain an 'approvals' list")
    records: list[ApprovalRecord] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise GateValidationError(f"approval #{index} must be an object")
        for key in ("parameter", "decision", "approver", "rubric_version"):
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                raise GateValidationError(f"approval #{index} has missing or invalid '{key}'")
        if not isinstance(item.get("approved"), bool):
            raise GateValidationError(f"approval #{index} has invalid 'approved' value")
        binding = item.get("binding_sha256")
        if not isinstance(binding, str) or len(binding) != 64:
            raise GateValidationError(
                f"approval #{index} for {item['parameter']!r} is missing a valid "
                "'binding_sha256' (64 hex characters); use the 'gate.pending.json' "
                "file written by `parallm assemble` as the template: copy it, fill "
                "in the binding hashes and a human review, then pass the edited "
                "copy with --gate"
            )
        if item["decision"] == "REJECT" and item["approved"]:
            raise GateValidationError(
                f"approval #{index} for {item['parameter']!r} records decision "
                "REJECT as approved; a rejection cannot approve a parameter"
            )
        parameter = str(item["parameter"]).strip()
        if parameter in seen:
            raise GateValidationError(f"duplicate approval record for parameter {parameter!r}")
        seen.add(parameter)
        records.append(ApprovalRecord(
            parameter=parameter,
            decision=item["decision"],
            approved=item["approved"],
            approver=item["approver"],
            rubric_version=item["rubric_version"],
            binding_sha256=binding,
            timestamp=item.get("timestamp", ""),
            note=item.get("note", ""),
        ))
    return records


class ApprovalGate:
    """Collects approvals; exposes which parameters may enter the approved set."""

    def __init__(self) -> None:
        self._records: list[ApprovalRecord] = []

    @property
    def records(self) -> list[ApprovalRecord]:
        return list(self._records)

    def approve(
        self,
        parameter: str,
        decision: str,
        approver: str,
        rubric_version: str,
        binding_sha256: str = "",
        note: str = "",
    ) -> ApprovalRecord:
        if decision == "REJECT":
            raise GateValidationError(
                f"cannot approve {parameter!r}: decision REJECT must be recorded "
                "with reject(), not approve()"
            )
        rec = ApprovalRecord(
            parameter=parameter,
            decision=decision,
            approved=True,
            approver=approver,
            rubric_version=rubric_version,
            binding_sha256=binding_sha256,
            note=note,
        )
        self._records.append(rec)
        return rec

    def reject(
        self,
        parameter: str,
        decision: str,
        approver: str,
        rubric_version: str,
        binding_sha256: str = "",
        note: str = "",
    ) -> ApprovalRecord:
        rec = ApprovalRecord(
            parameter=parameter,
            decision=decision,
            approved=False,
            approver=approver,
            rubric_version=rubric_version,
            binding_sha256=binding_sha256,
            note=note,
        )
        self._records.append(rec)
        return rec

    def record_for(self, parameter: str) -> ApprovalRecord | None:
        """Return the gate record for one parameter, if any."""
        return next((r for r in self._records if r.parameter == parameter), None)

    def approved_parameters(self) -> set[str]:
        return {r.parameter for r in self._records if r.approved}

    def is_approved(self, parameter: str) -> bool:
        return parameter in self.approved_parameters()

    def to_dict(self) -> dict[str, Any]:
        return {"approvals": [r.to_dict() for r in self._records]}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ApprovalGate":
        gate = cls()
        gate._records = validate_gate_records(payload)
        return gate


#: Decisions that may legitimately enter an export (mirrors report.py).
EXPORTABLE_DECISIONS = frozenset({"USE", "FIX"})

#: Placeholder written into a pending gate so an unedited file approves nothing.
PENDING_APPROVER = "NOT_RECORDED"


def pending_gate_payload(
    dossiers: Iterable[Mapping[str, Any]],
    *,
    target: str,
    rubric_version: str,
    generated: str,
) -> dict[str, Any]:
    """Build a fail-closed gate template for exportable assembled decisions.

    Every entry carries the binding hash recomputed from its dossier, but is
    marked ``approved=False`` with a placeholder approver.  An unedited file
    therefore exports nothing.  Non-exportable decisions (REVIEW, REJECT,
    CALIBRATE, MEASURE) are deliberately omitted: they need a scientific
    resolution before a human can approve them for export.
    """
    approvals: list[dict[str, Any]] = []
    for dossier in dossiers:
        decision = str(dossier.get("decision", ""))
        if decision not in EXPORTABLE_DECISIONS:
            continue
        approvals.append({
            "parameter": dossier.get("parameter"),
            "decision": decision,
            "approved": False,
            "approver": PENDING_APPROVER,
            "rubric_version": dossier.get("rubric_version", rubric_version),
            "binding_sha256": binding_sha256(dossier),
            "timestamp": PENDING_APPROVER,
            "note": "",
        })
    return {
        "gate_version": 1,
        "generated": generated,
        "target": target,
        "rubric_version": rubric_version,
        "note": (
            "SYNTHETIC PENDING GATE - no human has approved anything. Copy this "
            "file, set approved=true, approver, timestamp and a review reason "
            "for only the decisions you accept, then re-run `parallm assemble "
            "--gate <edited-file> --out <new-dir>`. Unedited, this file exports "
            "nothing."
        ),
        "approvals": approvals,
    }


@dataclass
class GateVerification:
    """Result of one shared, order-independent gate/dossier verification."""

    approved: set[str] = field(default_factory=set)
    reasons: dict[str, str] = field(default_factory=dict)


def verify_gate_bindings(
    gate: ApprovalGate,
    dossiers: Mapping[str, Mapping[str, Any]],
    *,
    exported_values: Mapping[str, Any] | None = None,
    expected_rubric_version: str | None = None,
) -> GateVerification:
    """Verify every approval against the decision it claims to approve.

    This is the single trust decision used by every export path.  A gate record
    is honoured only when *all* of the following hold for the same parameter:

    * the record exists and is marked approved;
    * the recorded decision is exportable (USE/FIX);
    * the recorded rubric version matches the assembly rubric;
    * the recorded ``binding_sha256`` equals the hash recomputed from the
      dossier's selected value, unit and source; and
    * when ``exported_values`` is supplied, the value being exported equals
      the dossier's selected value.

    Nothing is inferred from parameter names, file names, user claims, or the
    presence of a 64-character string in the gate.  Parameters outside
    ``dossiers`` (or without a gate record) are reported as blocked with a
    reason; they are never silently approved.  This protects against stale or
    mistaken gate/registry/export files.  It cannot protect against an actor
    who can rewrite *every* file including the assembly manifest; only a
    cryptographic signature over the chain could do that.
    """
    result = GateVerification()
    for parameter, dossier in dossiers.items():
        record = gate.record_for(parameter)
        if record is None:
            result.reasons[parameter] = "no gate record for this parameter"
            continue
        if not record.approved:
            result.reasons[parameter] = "gate record is not approved"
            continue
        reasons: list[str] = []
        if record.decision not in EXPORTABLE_DECISIONS:
            reasons.append(
                f"decision {record.decision!r} is not exportable"
            )
        if dossier.get("decision") is not None and record.decision != dossier["decision"]:
            reasons.append(
                f"decision mismatch: gate={record.decision!r}, assembly={dossier['decision']!r}"
            )
        if expected_rubric_version is not None and record.rubric_version != expected_rubric_version:
            reasons.append(
                f"rubric mismatch: gate={record.rubric_version!r}, "
                f"assembly={expected_rubric_version!r}"
            )
        elif dossier.get("rubric_version") is not None and record.rubric_version != dossier["rubric_version"]:
            reasons.append(
                f"rubric mismatch: gate={record.rubric_version!r}, "
                f"assembly={dossier['rubric_version']!r}"
            )
        expected_binding = binding_sha256(dossier)
        if record.binding_sha256 != expected_binding:
            reasons.append(
                f"binding mismatch: gate={record.binding_sha256}, assembly={expected_binding}"
            )
        if exported_values is not None and parameter in exported_values:
            selected = (dossier.get("selected") or {}).get("value")
            exported = exported_values[parameter]
            if isinstance(exported, dict):
                exported = exported.get("value")
            if isinstance(selected, (int, float)) and isinstance(exported, (int, float)):
                if float(selected) != float(exported):
                    reasons.append(
                        f"exported value mismatch: gate bound {selected!r}, export has {exported!r}"
                    )
            elif selected != exported:
                reasons.append(
                    f"exported value mismatch: gate bound {selected!r}, export has {exported!r}"
                )
        if reasons:
            result.reasons[parameter] = "; ".join(reasons)
        else:
            result.approved.add(parameter)
    return result
