"""Conflict resolution and decision making for the assembly layer.

Two conflict classes are handled differently, and the difference is recorded in
the rationale:

**same-source** — every surviving candidate comes from the same source (the
paper's own set value vs a value measured in the same paper). We adopt the
source's *operative* value, because what we parameterise is that paper's model;
the alternative is preserved as a conflict with its method. The literature
tells us *why* the source chose its value (e.g. Chen2020's Bruggeman 1.5).

**cross-source** — candidates come from different publications. They are ranked
by the rubric; if the top two are within ``review_margin`` the conflict is
genuinely ambiguous and is escalated (``REVIEW``) to the human approval gate
with the ranked alternatives shown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .rubric import Rubric, RubricOutcome
from .schema import CandidateValue, Decision, MethodClass, TargetSpecification


@dataclass
class Resolution:
    """Outcome of resolving one parameter."""

    canonical_id: str
    decision: Decision
    chosen: CandidateValue | None
    alternatives: list[CandidateValue] = field(default_factory=list)
    rejected: list[CandidateValue] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)
    outcomes: list[RubricOutcome] = field(default_factory=list)
    conflict: bool = False
    conflict_class: str | None = None
    review_required: bool = False
    rubric_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "decision": self.decision.value,
            "chosen": self.chosen.to_dict() if self.chosen else None,
            "alternatives": [c.to_dict() for c in self.alternatives],
            "rejected": [c.to_dict() for c in self.rejected],
            "rationale": list(self.rationale),
            "conflict": self.conflict,
            "conflict_class": self.conflict_class,
            "review_required": self.review_required,
            "rubric_version": self.rubric_version,
            "candidate_scores": [
                {
                    "value": o.candidate.value,
                    "unit": o.candidate.unit,
                    "source": o.candidate.source_id,
                    "operative": o.candidate.is_operative,
                    "total": round(o.total, 6),
                    "dimension_scores": {k: round(v, 4) for k, v in o.dimension_scores.items()},
                    "fired": o.fired,
                    "blockers": o.blockers,
                }
                for o in self.outcomes
            ],
        }


def _source_key(candidate: CandidateValue) -> str | None:
    """Identity of the *source* of a candidate (document id preferred).

    The registry mixes id spaces (a DOI for the operative value, a document id
    for its conflicts), so same-source detection must use one consistent key.
    """
    return candidate.source_document or candidate.source_id


def _distinct_values(candidates: Sequence[CandidateValue]) -> bool:
    """True when the candidates disagree numerically (or one is non-numeric)."""
    if len(candidates) < 2:
        return False
    numeric = [c.canonical_value for c in candidates if c.canonical_value is not None]
    if len(candidates) != len(numeric):
        return True
    if len(numeric) < 2:
        return False
    return any(abs(v - numeric[0]) > 1e-12 * max(1.0, abs(numeric[0])) for v in numeric[1:])


def _decision_for_method(candidate: CandidateValue) -> Decision:
    """Decision implied by the method class when there is no conflict.

    A selected UNRESOLVED value is never silently fixed: the registry records
    that no source resolved it, so a human must decide (scientific rule 5).
    """
    if str(candidate.status or "").upper() == "UNRESOLVED":
        return Decision.REVIEW
    if candidate.method_class in (MethodClass.MEASURED, MethodClass.CALCULATED, MethodClass.FITTED):
        return Decision.USE
    if candidate.method_class in (MethodClass.ASSUMED, MethodClass.CALIBRATED):
        return Decision.FIX
    return Decision.REVIEW


def _final_decision(
    decision: Decision,
    candidate: CandidateValue,
    target: TargetSpecification,
    rubric: Rubric,
    rationale: list[str],
) -> Decision:
    """rubric v4: withhold USE/FIX when a specific value has no stated match.

    An unstated cell product or chemistry family is not evidence of transfer.
    Escalate to REVIEW rather than adopting a value from another cell/chemistry.
    """
    if (
        rubric.require_stated_transfer_match
        and decision in (Decision.USE, Decision.FIX)
        and not rubric.stated_transfer_matches(candidate, target)
    ):
        rationale.append(
            f"REVIEW (rubric {rubric.version}): {candidate.canonical_id} is "
            "cell/chemistry-specific and the selected candidate has no stated, "
            "matching condition for this target; a specific value cannot be "
            "transferred on unstated conditions - a human must decide."
        )
        return Decision.REVIEW
    return decision


def _resolve_parameter_core(
    canonical_id: str,
    candidates: Sequence[CandidateValue],
    target: TargetSpecification,
    rubric: Rubric,
) -> Resolution:
    """Resolve one parameter's candidates into a decision with rationale."""
    if not candidates:
        return Resolution(
            canonical_id=canonical_id,
            decision=Decision.REVIEW,
            chosen=None,
            rationale=["no candidate values available for this parameter"],
            rubric_version=rubric.version,
            review_required=True,
        )

    siblings = [(c.source_id, c.canonical_value) for c in candidates]
    outcomes = [rubric.evaluate(c, target, siblings) for c in candidates]

    surviving = [o for o in outcomes if not o.blocked]
    rejected = [o for o in outcomes if o.blocked]

    rationale: list[str] = []
    for o in rejected:
        reasons = "; ".join(b["reason"] for b in o.blockers)
        rationale.append(
            f"REJECT {o.candidate.value} {o.candidate.unit or ''} "
            f"(source={o.candidate.source_id or 'unknown'}): {reasons}".strip()
        )

    # A candidate that is not declarable in the model (e.g. a function-valued
    # parameter) versus a scalar candidate for the same parameter is a *form*
    # mismatch: adopting the scalar would change the model's structure, which
    # is a modelling decision, not an applicability question.
    form_mismatch = any(
        any("not declarable" in b["reason"] for b in o.blockers) for o in rejected
    )
    if form_mismatch and surviving:
        return Resolution(
            canonical_id=canonical_id,
            decision=Decision.REVIEW,
            chosen=None,
            alternatives=[o.candidate for o in surviving],
            rejected=[o.candidate for o in rejected],
            rationale=rationale
            + [
                "REVIEW: the candidates differ in FORM (one is not declarable in the "
                "target model, the other is a scalar) - choosing between them changes "
                "the model, so a scientific decision is required."
            ],
            outcomes=outcomes,
            rubric_version=rubric.version,
            review_required=True,
        )

    if not surviving:
        # Distinguish "this candidate does not apply to the target" (REJECT:
        # the parameter simply stays unresolved for this cell) from "this
        # candidate cannot be trusted" (REVIEW: a human must look, e.g. a
        # quote that does not verify). Trust issues alone escalate; any
        # applicability blocker means the parameter stays unresolved.
        trust_blocks = {"evidence"}
        only_trust_issues = all(
            all(b["dimension"] in trust_blocks for b in o.blockers)
            for o in rejected
        )
        decision = Decision.REVIEW if only_trust_issues else Decision.REJECT
        return Resolution(
            canonical_id=canonical_id,
            decision=decision,
            chosen=None,
            rejected=[o.candidate for o in rejected],
            rationale=rationale
            + [
                "no candidate survives the applicability rubric for this target"
                + (
                    "; the parameter stays unresolved for this cell"
                    if decision is Decision.REJECT
                    else "; the surviving evidence cannot be verified, so a human must decide"
                )
            ],
            outcomes=outcomes,
            rubric_version=rubric.version,
            review_required=decision is Decision.REVIEW,
        )

    conflicting = _distinct_values([o.candidate for o in surviving])
    source_keys = {_source_key(o.candidate) for o in surviving}
    same_source = conflicting and len(source_keys) == 1

    if not conflicting:
        best = max(surviving, key=lambda o: o.total)
        decision = _final_decision(
            _decision_for_method(best.candidate), best.candidate, target, rubric, rationale
        )
        if rejected:
            # other candidates existed but failed the rubric: the survivor is
            # adopted, and the rejection is recorded as a preserved conflict
            rationale.append(
                f"adopted {best.candidate.value} {best.candidate.unit or ''} "
                f"(source={best.candidate.source_id}, rubric score {best.total:.3f}); "
                f"the competing candidate did not pass the applicability rubric "
                f"for this target"
            )
            return Resolution(
                canonical_id=canonical_id,
                decision=decision,
                chosen=best.candidate,
                alternatives=[],
                rejected=[o.candidate for o in rejected],
                rationale=rationale,
                outcomes=outcomes,
                conflict=True,
                conflict_class="cross_source" if len(source_keys) > 1 else "same_source",
                rubric_version=rubric.version,
            )
        rationale.append(
            f"{decision.value}: single applicable candidate {best.candidate.value} "
            f"{best.candidate.unit or ''} (rubric score {best.total:.3f}, "
            f"method class {best.candidate.method_class.value})"
        )
        return Resolution(
            canonical_id=canonical_id,
            decision=decision,
            chosen=best.candidate,
            alternatives=[],
            rejected=[o.candidate for o in rejected],
            rationale=rationale,
            outcomes=outcomes,
            conflict=False,
            rubric_version=rubric.version,
        )

    ranked = sorted(surviving, key=lambda o: (-o.total, not o.candidate.is_operative))
    top = ranked[0]
    if len(ranked) < 2:
        # defensive: conflicting was true but ranking collapsed (should not
        # happen once _distinct_values requires >= 2 candidates)
        decision = _final_decision(
            _decision_for_method(top.candidate), top.candidate, target, rubric, rationale
        )
        rationale.append(
            f"adopted {top.candidate.value} {top.candidate.unit or ''} "
            f"(source={top.candidate.source_id}, rubric score {top.total:.3f}); "
            f"no competing surviving candidate"
        )
        return Resolution(
            canonical_id=canonical_id,
            decision=decision,
            chosen=top.candidate,
            alternatives=[],
            rejected=[o.candidate for o in rejected],
            rationale=rationale,
            outcomes=outcomes,
            conflict=False,
            rubric_version=rubric.version,
        )
    second = ranked[1]

    if same_source:
        operative = next((o for o in surviving if o.candidate.is_operative), None)
        chosen = operative if operative is not None else top
        conflict_class = "same_source"
        rationale.append(
            "CONFLICT (same source): the source's operative value is adopted because what "
            "is being parameterised is that source's model; the alternative value is "
            "preserved as a conflict with its method."
        )
        rationale.append(
            f"adopted {chosen.candidate.value} {chosen.candidate.unit or ''} "
            f"(source={chosen.candidate.source_id}, method class "
            f"{chosen.candidate.method_class.value}, rubric score {chosen.total:.3f})"
        )
        decision = _final_decision(
            _decision_for_method(chosen.candidate), chosen.candidate, target, rubric, rationale
        )
        alternatives = [o.candidate for o in surviving if o.candidate is not chosen.candidate]
        return Resolution(
            canonical_id=canonical_id,
            decision=decision,
            chosen=chosen.candidate,
            alternatives=alternatives,
            rejected=[o.candidate for o in rejected],
            rationale=rationale,
            outcomes=outcomes,
            conflict=True,
            conflict_class=conflict_class,
            rubric_version=rubric.version,
        )

    conflict_class = "cross_source"
    margin = top.total - second.total
    rationale.append(
        "CONFLICT (cross-source): candidates ranked by the applicability rubric"
    )
    if margin < rubric.review_margin:
        decision = Decision.REVIEW
        rationale.append(
            f"REVIEW: top two candidates are within the review margin "
            f"({margin:.3f} < {rubric.review_margin:.3f}); the conflict is ambiguous and "
            f"is escalated to the human approval gate with the ranked alternatives."
        )
        return Resolution(
            canonical_id=canonical_id,
            decision=decision,
            chosen=None,
            alternatives=[o.candidate for o in surviving],
            rejected=[o.candidate for o in rejected],
            rationale=rationale,
            outcomes=outcomes,
            conflict=True,
            conflict_class=conflict_class,
            review_required=True,
            rubric_version=rubric.version,
        )

    # A disagreement between candidates obtained by *different kinds* of method
    # (e.g. a fitted value vs a measured one) is a scientific disagreement, not
    # an applicability question: escalate unless the applicability evidence
    # clearly favours one of them.
    divergent = top.candidate.method_class != second.candidate.method_class
    if divergent and margin <= rubric.method_divergence_margin:
        rationale.append(
            f"REVIEW: the candidates differ in method class "
            f"({top.candidate.method_class.value} vs {second.candidate.method_class.value}) "
            f"and the applicability margin ({margin:.3f}) does not clearly favour "
            f"either - a scientific decision is required."
        )
        return Resolution(
            canonical_id=canonical_id,
            decision=Decision.REVIEW,
            chosen=None,
            alternatives=[o.candidate for o in surviving],
            rejected=[o.candidate for o in rejected],
            rationale=rationale,
            outcomes=outcomes,
            conflict=True,
            conflict_class=conflict_class,
            review_required=True,
            rubric_version=rubric.version,
        )

    decision = _final_decision(
        _decision_for_method(top.candidate), top.candidate, target, rubric, rationale
    )
    rationale.append(
        f"adopted {top.candidate.value} {top.candidate.unit or ''} "
        f"(source={top.candidate.source_id}, rubric score {top.total:.3f}; runner-up "
        f"{second.candidate.value} {second.candidate.unit or ''} from "
        f"{second.candidate.source_id} scored {second.total:.3f}, margin {margin:.3f})"
    )
    alternatives = [o.candidate for o in surviving if o.candidate is not top.candidate]
    return Resolution(
        canonical_id=canonical_id,
        decision=decision,
        chosen=top.candidate,
        alternatives=alternatives,
        rejected=[o.candidate for o in rejected],
        rationale=rationale,
        outcomes=outcomes,
        conflict=True,
        conflict_class=conflict_class,
        rubric_version=rubric.version,
    )


def resolve_parameter(
    canonical_id: str,
    candidates: Sequence[CandidateValue],
    target: TargetSpecification,
    rubric: Rubric,
) -> Resolution:
    """Resolve one parameter, then apply the chemistry-specific guard.

    Chemistry-specific values (the approved list in ``lexicon.py``) only
    transfer to a target of the same chemistry. An unknown chemistry is
    escalated to REVIEW; a known mismatch is a REJECT. This runs after the
    rubric so every adopted value is checked, including same-source conflicts.
    """
    from .lexicon import is_chemistry_specific

    result = _resolve_parameter_core(canonical_id, candidates, target, rubric)
    if not is_chemistry_specific(canonical_id) or result.chosen is None:
        return result
    if result.decision is Decision.REJECT or result.decision is Decision.REVIEW:
        return result

    fam = set(result.chosen.conditions.chemistry_families)
    target_fam = set(target.chemistry_families)
    # A positive-electrode parameter is decided by the cathode chemistry, a
    # negative-electrode or SEI parameter by the anode chemistry. Counting any
    # shared family (e.g. "graphite" from the cell's anode text) would let an
    # NMC-cathode value through for an LFP-cathode target.
    if canonical_id.startswith(("pos_", "positive_")):
        relevant = {"NMC", "NCA", "LFP", "LCO", "LMO", "Li-metal"}
    elif canonical_id.startswith(("sei_", "neg_", "negative_")):
        relevant = {"graphite", "Li-metal", "silicon"}
    else:
        relevant = fam | target_fam
    cand_relevant = fam & relevant
    target_relevant = target_fam & relevant
    if not cand_relevant:
        result.decision = Decision.REVIEW
        result.review_required = True
        result.rationale.append(
            "REVIEW: chemistry-specific parameter with unknown evidence chemistry; "
            "a human must decide whether it applies to this target"
        )
        return result
    if not (cand_relevant & target_relevant):
        result.decision = Decision.REJECT
        result.review_required = False
        result.chosen = None
        result.rationale.append(
            f"REJECT: chemistry-specific parameter measured on {sorted(cand_relevant)}, "
            f"target chemistry is {sorted(target_relevant)}"
        )
    return result
