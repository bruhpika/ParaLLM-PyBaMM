"""Human resolution of REVIEW decisions (Phase 3).

A REVIEW decision means the deterministic pipeline could not decide. Only a
human may resolve it, and the resolution must record a reason, evidence and
reviewer. This module validates such records and applies them to assembled
dossiers without ever choosing a decision on the human's behalf.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from .gate import EXPORTABLE_DECISIONS, binding_sha256

RESOLUTION_VERSION = 1


class ResolutionError(ValueError):
    """Raised when a resolution record is malformed, stale or contradictory."""


@dataclass
class AppliedResolution:
    """One applied human resolution, with its provenance for the manifest."""

    parameter: str
    original_decision: str
    resolved_decision: str
    reviewer: str
    binding_sha256: str


def _require_text(value: Any, field: str, index: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ResolutionError(f"resolution #{index} has an empty '{field}'")
    return text


def make_resolution_record(
    dossier: Mapping[str, Any],
    *,
    decision: str,
    reason: str,
    evidence: str,
    reviewer: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build one human resolution record bound to the exact dossier."""
    if dossier.get("decision") != "REVIEW":
        raise ResolutionError(
            f"{dossier.get('parameter')!r}: only a REVIEW decision can be resolved; "
            f"found {dossier.get('decision')!r}"
        )
    if decision not in EXPORTABLE_DECISIONS:
        raise ResolutionError(
            f"resolved decision must be one of {sorted(EXPORTABLE_DECISIONS)}, got {decision!r}"
        )
    return {
        "parameter": str(dossier.get("parameter")),
        "original_decision": "REVIEW",
        "resolved_decision": decision,
        "reason": _require_text(reason, "reason", dossier.get("parameter")),
        "evidence": _require_text(evidence, "evidence", dossier.get("parameter")),
        "reviewer": _require_text(reviewer, "reviewer", dossier.get("parameter")),
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "rubric_version": dossier.get("rubric_version"),
        "target": None,
        "binding_sha256": binding_sha256(dossier),
    }


def apply_resolutions(
    dossiers: list[dict[str, Any]],
    payload: Any,
) -> tuple[list[dict[str, Any]], list[AppliedResolution]]:
    """Validate and apply human resolutions to a list of assembled dossiers.

    Nothing is mutated in place: the input dossiers are copied. Every record is
    checked against the current dossier before it can change a decision.
    """
    if not isinstance(payload, dict):
        raise ResolutionError("resolution payload must be a JSON object")
    if payload.get("resolution_version") != RESOLUTION_VERSION:
        raise ResolutionError(
            f"unsupported resolution_version {payload.get('resolution_version')!r}"
        )
    items = payload.get("decisions")
    if not isinstance(items, list) or not items:
        raise ResolutionError("resolution payload must contain a non-empty 'decisions' list")
    by_id = {
        str(d["parameter"]): d for d in dossiers
        if isinstance(d, dict) and d.get("parameter")
    }
    applied: list[AppliedResolution] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ResolutionError(f"resolution #{index} must be an object")
        parameter = _require_text(item.get("parameter"), "parameter", index)
        if parameter in seen:
            raise ResolutionError(f"duplicate resolution for {parameter!r}")
        seen.add(parameter)
        dossier = by_id.get(parameter)
        if dossier is None:
            raise ResolutionError(f"resolution #{index}: unknown parameter {parameter!r}")
        if dossier.get("decision") != "REVIEW":
            raise ResolutionError(
                f"{parameter}: only a REVIEW decision can be resolved; "
                f"found {dossier.get('decision')!r}"
            )
        if item.get("original_decision") != "REVIEW":
            raise ResolutionError(
                f"{parameter}: original_decision must be REVIEW, "
                f"got {item.get('original_decision')!r}"
            )
        decision = item.get("resolved_decision")
        if decision not in EXPORTABLE_DECISIONS:
            raise ResolutionError(
                f"{parameter}: resolved decision must be one of "
                f"{sorted(EXPORTABLE_DECISIONS)}, got {decision!r}"
            )
        _require_text(item.get("reason"), "reason", parameter)
        _require_text(item.get("evidence"), "evidence", parameter)
        reviewer = _require_text(item.get("reviewer"), "reviewer", parameter)
        expected = binding_sha256(dossier)
        if item.get("binding_sha256") != expected:
            raise ResolutionError(
                f"{parameter}: resolution binding is stale: "
                f"recorded {item.get('binding_sha256')!r}, assembly {expected!r}"
            )
        if item.get("rubric_version") is not None and item["rubric_version"] != dossier.get("rubric_version"):
            raise ResolutionError(
                f"{parameter}: resolution rubric {item['rubric_version']!r} "
                f"does not match assembly {dossier.get('rubric_version')!r}"
            )
        applied.append(AppliedResolution(
            parameter=parameter, original_decision="REVIEW",
            resolved_decision=decision, reviewer=reviewer,
            binding_sha256=expected,
        ))

    copies = copy.deepcopy(dossiers)
    copy_by_id = {str(d["parameter"]): d for d in copies if isinstance(d, dict)}
    for resolution in applied:
        d = copy_by_id[resolution.parameter]
        record = next(r for r in items if str(r.get("parameter")) == resolution.parameter)
        d["decision"] = resolution.resolved_decision
        d["recommendation"]["decision"] = resolution.resolved_decision
        d["recommendation"]["rationale"] = list(d["recommendation"].get("rationale") or []) + [
            f"human resolution by {resolution.reviewer}: {record['reason']}",
            f"human evidence: {record['evidence']}",
        ]
        d["resolution"] = {
            "original_decision": "REVIEW",
            "resolved_decision": resolution.resolved_decision,
            "reason": record["reason"],
            "evidence": record["evidence"],
            "reviewer": resolution.reviewer,
            "timestamp": record.get("timestamp"),
            "rubric_version": record.get("rubric_version"),
        }
    return copies, applied
