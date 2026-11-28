"""Assembly report: turn the parameter registry into decisions for a target.

``assemble`` is the entry point of the assembly layer: it takes the registry
records (each with an operative value and preserved conflicts), a target cell
specification and a rubric, and returns per-parameter dossiers plus a
set-level summary.

Nothing here writes to the registry: the assembly layer proposes, the human
approval gate disposes.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .dossier import dossier, to_markdown
from .gate import ApprovalGate
from .observability import (
    ACTION_CALIBRATE,
    ACTION_FIX,
    ACTION_MEASURE,
    ObservabilityAssessment,
)
from .resolve import Resolution, resolve_parameter
from .rubric import Rubric
from .schema import (
    STATUS_TO_METHOD,
    CandidateValue,
    ConditionFacts,
    Decision,
    MethodClass,
    TargetSpecification,
)
from ..literature.evidence import verify_quote_in_evidence

_METHOD_KEYWORDS: tuple[tuple[MethodClass, tuple[str, ...]], ...] = (
    (MethodClass.MEASURED, ("measured", "measurement", "instrument", "vernier", "sem ", "fib", "tga", "eis")),
    (MethodClass.FITTED, ("fit", "regression", "least squares", "inverse")),
    (MethodClass.CALCULATED, ("calculated", "computed", "derived from", "equation")),
    (MethodClass.ASSUMED, ("assumed", "default", "theoretical", "typical")),
)


def infer_method_class(status: str | None, method: str | None) -> MethodClass:
    """Map (registry status, method text) to a method class.

    The registry status is authoritative when it carries the meaning
    (ASSUMED/CALCULATED/CALIBRATED); LITERATURE_DERIVED values are classified
    from the method text, and stay UNKNOWN when the text is not decisive.
    """
    if status:
        mapped = STATUS_TO_METHOD.get(status)
        if mapped is not None and mapped is not MethodClass.UNKNOWN:
            return mapped
    text = (method or "").lower()
    for cls, keys in _METHOD_KEYWORDS:
        if any(k in text for k in keys):
            return cls
    return MethodClass.UNKNOWN


def _callable_value(record: Mapping[str, Any]) -> bool:
    value = record.get("value")
    return callable(value) or (isinstance(value, str) and "<function" in value)


def candidates_from_record(record: Mapping[str, Any]) -> list[CandidateValue]:
    """Build the candidate list for one registry record (operative + conflicts)."""
    canonical_id = record.get("canonical_id", "")
    conditions = record.get("conditions") or {}
    evidence = record.get("evidence") or {}
    source = evidence.get("source") or {}
    mapping = record.get("pybop_mapping") or {}

    operative = CandidateValue(
        canonical_id=canonical_id,
        value=record.get("value"),
        unit=record.get("value_unit"),
        canonical_value=record.get("normalized_value"),
        canonical_unit=record.get("normalized_value_unit"),
        method_class=infer_method_class(record.get("status"), record.get("method")),
        method=record.get("method"),
        status=record.get("status"),
        conditions=ConditionFacts.from_mapping(conditions),
        source_id=record.get("source_id"),
        source_document=source.get("document_id") or record.get("source_id"),
        source_locator=source.get("locator"),
        page=source.get("page") if isinstance(source.get("page"), int) else None,
        quote=source.get("quote"),
        quote_present=bool(source.get("quote")),
        quote_verified=source.get("quote_verified"),
        is_operative=True,
        model_applicable=mapping.get("applicable"),
        model_note=mapping.get("notes"),
    )
    if _callable_value(record):
        operative.model_applicable = False
        operative.model_note = "function-valued parameter; not declarable as a scalar"

    out = [operative]
    for conflict in record.get("conflicts") or []:
        csource = conflict.get("source") or {}
        out.append(
            CandidateValue(
                canonical_id=canonical_id,
                value=conflict.get("value"),
                unit=conflict.get("unit"),
                canonical_value=conflict.get("normalized_value"),
                canonical_unit=conflict.get("normalized_value_unit"),
                method_class=infer_method_class(conflict.get("kind"), conflict.get("method")),
                method=conflict.get("method"),
                status=conflict.get("kind"),
                conditions=ConditionFacts.from_mapping(conflict.get("conditions") or {}),
                source_id=csource.get("document_id") or record.get("source_id"),
                source_document=csource.get("document_id") or record.get("source_id"),
                source_locator=csource.get("locator"),
                page=csource.get("page") if isinstance(csource.get("page"), int) else None,
                quote=csource.get("quote"),
                quote_present=bool(csource.get("quote")),
                quote_verified=csource.get("quote_verified"),
                is_operative=False,
                model_applicable=mapping.get("applicable"),
            )
        )
    return out


@dataclass
class AssemblyReport:
    """Set-level result of an assembly run."""

    target: TargetSpecification
    rubric_version: str
    dossiers: list[dict[str, Any]] = field(default_factory=list)
    resolutions: list[Resolution] = field(default_factory=list)

    # -- summary ---------------------------------------------------------
    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for d in self.dossiers:
            counts[d["decision"]] = counts.get(d["decision"], 0) + 1
        conflicts = [d for d in self.dossiers if d["conflict"]]
        return {
            "target": self.target.to_dict(),
            "rubric_version": self.rubric_version,
            "n_parameters": len(self.dossiers),
            "decisions": dict(sorted(counts.items())),
            "n_conflicts": len(conflicts),
            "same_source_conflicts": sum(
                1 for d in conflicts if d["conflict_class"] == "same_source"
            ),
            "cross_source_conflicts": sum(
                1 for d in conflicts if d["conflict_class"] == "cross_source"
            ),
            "n_review_required": sum(1 for d in self.dossiers if d["review_required"]),
            "n_preserved_alternatives": sum(len(d["alternatives"]) for d in self.dossiers),
            "n_rejected_candidates": sum(len(d["rejected"]) for d in self.dossiers),
            "action_matrix": self.action_matrix(),
        }

    def action_matrix(self) -> dict[str, int]:
        """Fit/fix/measure action counts from the observability join (V2.3).

        Parameters without a recorded identifiability artifact are counted as
        ``not_assessed`` — explicit, never silently fitted.
        """
        counts = {ACTION_CALIBRATE: 0, ACTION_FIX: 0, ACTION_MEASURE: 0,
                  "not_assessed": 0}
        for d in self.dossiers:
            action = (d.get("identifiability") or {}).get("action")
            counts[action if action in counts else "not_assessed"] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "parameters": self.dossiers,
        }

    def to_markdown(self) -> str:
        return to_markdown(self.dossiers, title=f"PARALLM parameter assembly — {self.target.target_id}")

    # -- export ----------------------------------------------------------
    def pybamm_export(
        self, gate: ApprovalGate | None = None, with_reasons: bool = False
    ) -> dict[str, Any] | dict[str, dict[str, str]]:
        """Approved parameters as a PyBaMM-style {name: value} mapping.

        Only parameters with a recorded human approval are exported; the
        approval record is the audit trail (rule 10). With no gate, nothing is
        exported. Each approval must match the dossier's parameter, decision,
        rubric version and deterministic value/unit/source hash; any mismatch
        blocks that parameter.

        When ``with_reasons=True``, returns ``{"parameters": ..., "blocked":
        {parameter: reason}}`` so callers can report why a value was withheld.
        """
        from .gate import binding_sha256

        out: dict[str, Any] = {}
        blocked: dict[str, str] = {}
        for d in self.dossiers:
            parameter = d["parameter"]
            if gate is None:
                blocked[parameter] = f"{parameter}: no approval gate provided"
                continue
            record = gate.record_for(parameter)
            if record is None or not record.approved:
                blocked[parameter] = (
                    f"{parameter}: no approved gate record for this parameter"
                )
                continue
            reasons: list[str] = []
            if record.decision != d["decision"]:
                reasons.append(
                    f"decision mismatch: approved {record.decision!r}, "
                    f"assembly produced {d['decision']!r}"
                )
            if record.rubric_version != d["rubric_version"]:
                reasons.append(
                    f"rubric mismatch: approved {record.rubric_version!r}, "
                    f"assembly produced {d['rubric_version']!r}"
                )
            expected = binding_sha256(d)
            if record.binding_sha256 != expected:
                reasons.append(
                    f"binding mismatch: approved {record.binding_sha256}, "
                    f"assembly produced {expected}"
                )
            if reasons:
                blocked[parameter] = f"{parameter}: " + "; ".join(reasons)
                continue
            if d["decision"] not in (Decision.USE.value, Decision.FIX.value):
                blocked[parameter] = (
                    f"{parameter}: decision {d['decision']} is not exportable"
                )
                continue
            value = (d.get("selected") or {}).get("value")
            if value is None:
                blocked[parameter] = f"{parameter}: no selected value to export"
                continue
            out[parameter] = value
        if with_reasons:
            return {"parameters": out, "blocked": blocked}
        return out


def verify_record_quotes(
    records: Iterable[Mapping[str, Any]],
    doc_texts: Mapping[str, str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Stamp a deterministic quote-verification result onto record copies.

    For every quoted source (operative and conflicts) whose document text is
    available, ``quote_verified`` is set from the verbatim checker
    (``verify_quote_in_evidence``). Quotes whose document is not in
    ``doc_texts`` stay unchecked (``quote_verified`` remains None) and carry
    ``quote_verification_state = "source text not present locally"`` — never
    silently treated as verified. Inputs are not mutated (raw data is
    preserved); returns (stamped copies, statistics).
    """
    stamped = copy.deepcopy(list(records))
    stats = {"n_quotes": 0, "n_checked": 0, "n_verified": 0, "n_failed": 0,
             "n_no_text": 0,
             "no_text_state": "source text not present locally"}

    def _stamp(source: Mapping[str, Any] | None) -> None:
        if not isinstance(source, dict):
            return
        quote = source.get("quote")
        if not quote:
            return
        stats["n_quotes"] += 1
        doc_id = source.get("document_id")
        text = doc_texts.get(doc_id) if doc_id else None
        if not text:
            stats["n_no_text"] += 1
            source["quote_verified"] = None
            source["quote_verification_state"] = "source text not present locally"
            return
        verified = verify_quote_in_evidence(quote, text)
        source["quote_verified"] = bool(verified)
        source["quote_verification_state"] = "verified" if verified else "failed verbatim check"
        stats["n_checked"] += 1
        stats["n_verified" if verified else "n_failed"] += 1

    for rec in stamped:
        _stamp((rec.get("evidence") or {}).get("source"))
        for conflict in rec.get("conflicts") or []:
            _stamp(conflict.get("source"))
    return stamped, stats


def _apply_observability_upgrade(
    d: dict[str, Any], resolution: Resolution, assess: ObservabilityAssessment | None
) -> dict[str, Any]:
    """Upgrade USE/FIX decisions using the observability action (V2.3).

    Deterministic (rule-firing recorded in the recommendation rationale):
    observable -> CALIBRATE (free for estimation); unobservable -> FIX (hold
    the literature value) or MEASURE when the parameter is marked
    accuracy-critical. REJECT/REVIEW are never upgraded.
    """
    if assess is None or not assess.action:
        return d
    base = resolution.decision
    if base not in (Decision.USE, Decision.FIX):
        return d
    if assess.action == ACTION_CALIBRATE:
        new = Decision.CALIBRATE
    elif assess.action == ACTION_MEASURE:
        new = Decision.MEASURE
    else:
        new = Decision.FIX
    protocols = "/".join(assess.protocols) or "recorded protocols"
    rules = ", ".join(r["rule"] for r in assess.rules_fired)
    if new != base:
        d["decision"] = new.value
        d["recommendation"]["decision"] = new.value
        d["recommendation"]["rationale"].append(
            f"decision upgraded {base.value} -> {new.value} by the observability "
            f"join: {assess.status} under {protocols} (rule: {rules})"
        )
    else:
        d["recommendation"]["rationale"].append(
            f"decision {base.value} confirmed by the observability join: "
            f"{assess.status} under {protocols} (rule: {rules})"
        )
    if new == Decision.CALIBRATE:
        d["recommendation"]["next_step"] = (
            "free this parameter for estimation under the stated protocol "
            "(observability supports identification)"
        )
    elif new == Decision.MEASURE:
        d["recommendation"]["next_step"] = (
            "not identifiable under the stated protocol: specify the experiment "
            "that would identify it (MEASURE) before relying on the value's "
            "accuracy"
        )
    else:
        d["recommendation"]["next_step"] = (
            "adopt and hold the literature value (FIX): unobservable under the "
            "stated protocol; if accuracy is required, specify an identifying "
            "experiment (MEASURE)"
        )
    return d


def assemble(
    records: Iterable[Mapping[str, Any]],
    target: TargetSpecification,
    rubric: Rubric,
    observability: Mapping[str, ObservabilityAssessment] | None = None,
) -> AssemblyReport:
    """Assemble decisions for every parameter in ``records``.

    ``observability`` (optional, V2.3) maps canonical ids to recorded
    identifiability assessments; it populates dossier field 7 and upgrades
    USE/FIX decisions to CALIBRATE/MEASURE/FIX deterministically.
    """
    report = AssemblyReport(target=target, rubric_version=rubric.version)
    for record in records:
        canonical_id = record.get("canonical_id", "")
        candidates = candidates_from_record(record)
        resolution = resolve_parameter(canonical_id, candidates, target, rubric)
        report.resolutions.append(resolution)
        assess = (observability or {}).get(canonical_id)
        if (
            assess is not None
            and assess.parameter_set is not None
            and target.parameter_set
            and assess.parameter_set != target.parameter_set
        ):
            # A result recorded for one cell cannot be applied to another.
            assess = None
        d = dossier(
            resolution,
            identifiability=assess.to_dossier_field() if assess else None,
        )
        report.dossiers.append(_apply_observability_upgrade(d, resolution, assess))
    return report
