"""Applicability cases: expert-agreement evaluation for the assembly layer.

The v0.2 headline scientific metric is **agreement between the applicability
rubric and expert decisions** on conflict/applicability situations
(`docs/ROADMAP_V0.2.md` §3.1).

This module provides the case schema, the deterministic comparison and the
aggregation. The *cases themselves* (with their expert labels) are kept
private until the project owner has reviewed them — the same hygiene as the
private v4 benchmark.

A case states:

* the target cell + protocol the parameter is being assembled for;
* two or more candidate values, each with its own source, conditions and
  method (all drawn from real registry/corpus records — never invented);
* the expert decision (USE / FIX / CALIBRATE / MEASURE / REJECT / REVIEW),
  optionally with the expected chosen candidate;
* the expert rationale, and whether the case is *ambiguous* (i.e. the expert
  answer is REVIEW).

Agreement is computed on the **decision**; when the case names an expected
chosen candidate, the chosen candidate must match as well.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..assembly.resolve import Resolution
from ..assembly.rubric import Rubric
from ..assembly.schema import TargetSpecification


@dataclass
class ApplicabilityCase:
    """One labelled applicability/conflict situation."""

    case_id: str
    target_id: str
    parameter: str
    candidates: list[dict[str, Any]]
    expert_decision: str
    expert_choice: int | None = None
    expert_rationale: str = ""
    ambiguous: bool = False
    case_class: str = "conflict"  # conflict | applicability | ambiguous
    reviewed_by: str | None = None
    reviewed_on: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "target_id": self.target_id,
            "parameter": self.parameter,
            "candidates": self.candidates,
            "expert_decision": self.expert_decision,
            "expert_choice": self.expert_choice,
            "expert_rationale": self.expert_rationale,
            "ambiguous": self.ambiguous,
            "case_class": self.case_class,
            "reviewed_by": self.reviewed_by,
            "reviewed_on": self.reviewed_on,
            "notes": self.notes,
        }


def load_cases(path: str | Path) -> list[ApplicabilityCase]:
    cases: list[ApplicabilityCase] = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        cases.append(
            ApplicabilityCase(
                case_id=d["case_id"],
                target_id=d["target_id"],
                parameter=d["parameter"],
                candidates=d["candidates"],
                expert_decision=d["expert_decision"],
                expert_choice=d.get("expert_choice"),
                expert_rationale=d.get("expert_rationale", ""),
                ambiguous=bool(d.get("ambiguous", False)),
                case_class=d.get("case_class", "conflict"),
                reviewed_by=d.get("reviewed_by"),
                reviewed_on=d.get("reviewed_on"),
                notes=d.get("notes", ""),
            )
        )
    return cases


def candidate_from_dict(d: Mapping[str, Any], canonical_id: str) -> Any:
    """Build an assembly candidate from a case record."""
    from ..assembly.schema import CandidateValue, ConditionFacts, MethodClass

    method = str(d.get("method_class", "unknown")).lower()
    try:
        method_class = MethodClass(method)
    except ValueError:
        method_class = MethodClass.UNKNOWN
    return CandidateValue(
        canonical_id=canonical_id,
        value=d.get("value"),
        unit=d.get("unit"),
        canonical_value=d.get("canonical_value"),
        canonical_unit=d.get("canonical_unit"),
        method_class=method_class,
        method=d.get("method"),
        status=d.get("status"),
        conditions=ConditionFacts.from_mapping(d.get("conditions") or {}),
        source_id=d.get("source_id"),
        source_document=d.get("source_document") or d.get("source_id"),
        source_locator=d.get("source_locator"),
        page=d.get("page"),
        quote=d.get("quote"),
        quote_present=bool(d.get("quote")),
        quote_verified=d.get("quote_verified"),
        is_operative=bool(d.get("is_operative", False)),
        model_applicable=d.get("model_applicable", True),
        model_note=d.get("model_note"),
    )


def score_case(
    case: ApplicabilityCase, rubric: Rubric, target: TargetSpecification
) -> dict[str, Any]:
    """Run the rubric over one case and compare with the expert decision."""
    from ..assembly.resolve import resolve_parameter

    candidates = [candidate_from_dict(c, case.parameter) for c in case.candidates]
    resolution: Resolution = resolve_parameter(case.parameter, candidates, target, rubric)

    decision = resolution.decision.value
    chosen_ok = True
    if case.expert_choice is not None:
        expected = case.candidates[case.expert_choice]
        chosen = resolution.chosen
        if chosen is None:
            chosen_ok = False
        else:
            chosen_ok = (
                _same_value(chosen.value, expected.get("value"))
                and _same_source(chosen, expected)
            )
    decision_ok = decision == case.expert_decision
    source_keys = {
        (c.get("source_document") or c.get("source_id")) for c in case.candidates
    }
    return {
        "case_id": case.case_id,
        "case_class": case.case_class,
        "ambiguous": case.ambiguous,
        "parameter": case.parameter,
        "expert_decision": case.expert_decision,
        "rubric_decision": decision,
        "decision_match": decision_ok,
        "chosen_match": chosen_ok,
        "match": decision_ok and chosen_ok,
        "n_candidates": len(candidates),
        "n_distinct_sources": len(source_keys),
        "cross_source": len(source_keys) > 1,
        "rationale": resolution.rationale,
        "scores": [
            {
                "value": o.candidate.value,
                "unit": o.candidate.unit,
                "source": o.candidate.source_id,
                "total": round(o.total, 6),
                "dimension_scores": {k: round(v, 4) for k, v in o.dimension_scores.items()},
                "blockers": o.blockers,
            }
            for o in resolution.outcomes
        ],
        "reviewed_by": case.reviewed_by,
        "reviewed_on": case.reviewed_on,
    }


def _same_value(a: Any, b: Any) -> bool:
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)
    if fa == fb:
        return True
    if fa == 0 or fb == 0:
        return False
    ratio = abs(fa / fb)
    if ratio < 1:
        ratio = 1 / ratio
    import math

    exponent = round(math.log10(ratio))
    return abs(ratio - 10**exponent) / (10**exponent) <= 1e-2


def _same_source(chosen: Any, expected: Mapping[str, Any]) -> bool:
    exp_doc = expected.get("source_document") or expected.get("source_id")
    return (chosen.source_document or chosen.source_id) == exp_doc


def agreement(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate expert-agreement statistics."""
    rows = list(rows)
    if not rows:
        return {}

    def block(subset: list[Mapping[str, Any]]) -> dict[str, Any]:
        if not subset:
            return {}
        n = len(subset)
        return {
            "n_cases": n,
            "decision_agreement": sum(1 for r in subset if r["decision_match"]) / n,
            "full_agreement": sum(1 for r in subset if r["match"]) / n,
            "n_ambiguous": sum(1 for r in subset if r["ambiguous"]),
            "n_mismatched_decision": sum(1 for r in subset if not r["decision_match"]),
            "n_mismatched_choice": sum(
                1 for r in subset if r["decision_match"] and not r["chosen_match"]
            ),
        }

    out: dict[str, Any] = {"all": block(rows)}
    for cls in sorted({r["case_class"] for r in rows}):
        out[f"class:{cls}"] = block([r for r in rows if r["case_class"] == cls])
    out["label_status"] = {
        "reviewed": sum(1 for r in rows if r.get("reviewed_by")),
        "drafted": sum(1 for r in rows if not r.get("reviewed_by")),
    }
    return out
