"""Unit tests for rubric v2 dimensions (cell product, electrolyte) and the
new resolve paths (form mismatch, method divergence, trust vs applicability).

Deterministic; no network.
"""

from __future__ import annotations

import pytest

from pybamm_closed_loop.assembly import (
    CandidateValue,
    ConditionFacts,
    Decision,
    MethodClass,
    Rubric,
    TargetSpecification,
    resolve_parameter,
)
from pybamm_closed_loop.assembly.lexicon import (
    cell_tokens,
    is_cell_specific,
    parameter_family,
)

TARGET = TargetSpecification(
    target_id="lgm50",
    cell_product="LG M50",
    chemistry_families=("NMC", "graphite"),
    format="21700",
    temperature_k=298.15,
    soc="50%",
    electrolyte="1 mol dm-3 LiPF6 in EC:EMC (3:7 V/V), 1 wt% VC",
)


def _candidate(
    value,
    unit,
    *,
    canonical_id="p",
    method_class=MethodClass.MEASURED,
    source_id="doc-a",
    source_document="doc-a",
    conditions=None,
    quote=None,
    quote_verified=None,
    is_operative=False,
    model_applicable=True,
    model_note=None,
):
    return CandidateValue(
        canonical_id=canonical_id,
        value=value,
        unit=unit,
        canonical_value=float(value) if isinstance(value, (int, float)) else None,
        canonical_unit=unit,
        method_class=method_class,
        method="test method",
        status="LITERATURE_DERIVED",
        conditions=conditions
        or ConditionFacts(
            cell_product="LG M50",
            format="21700",
            chemistry_families=("NMC", "graphite"),
            temperature_k=298.15,
            soc="50%",
        ),
        source_id=source_id,
        source_document=source_document,
        source_locator="Table 1",
        page=7,
        quote=quote,
        quote_present=bool(quote),
        quote_verified=quote_verified,
        is_operative=is_operative,
        model_applicable=model_applicable,
        model_note=model_note,
    )


class TestLexiconV2:
    def test_cell_tokens(self):
        tokens = cell_tokens("Samsung INR21700-50E high energy cell")
        assert any("21700" in t for t in tokens)

    def test_cell_tokens_empty(self):
        assert cell_tokens(None) == ()
        assert cell_tokens("") == ()

    def test_is_cell_specific(self):
        assert is_cell_specific("neg_electrode_thickness") is True
        assert is_cell_specific("neg_electron_diffusivity") is False

    def test_parameter_family(self):
        assert parameter_family("electrolyte_diffusivity") == "electrolyte"
        assert parameter_family("neg_bruggeman_electrolyte") == "electrolyte"
        assert parameter_family("neg_electron_diffusivity") == "electrode"
        assert parameter_family("thermal_conductivity") == "electrode"


class TestRubricV2Dimensions:
    def test_weights_sum_to_one(self):
        rubric = Rubric("rubric-v2")
        assert abs(sum(rubric.weights.values()) - 1.0) < 1e-9
        assert abs(sum(rubric.electrolyte_weights.values()) - 1.0) < 1e-9

    def test_electrolyte_weights_must_sum_to_one(self):
        with pytest.raises(ValueError, match="electrolyte"):
            Rubric("bad", electrolyte_weights={"chemistry": 0.5})

    def test_electrolyte_weights_must_match_dimensions(self):
        with pytest.raises(ValueError, match="same dimensions"):
            Rubric("bad", electrolyte_weights={"chemistry": 1.0})

    def test_cell_product_and_electrolyte_are_scored(self):
        rubric = Rubric("rubric-v2")
        outcome = rubric.evaluate(_candidate(1.0, "dimensionless"), TARGET)
        assert "cell_product" in outcome.dimension_scores
        assert "electrolyte" in outcome.dimension_scores

    def test_cell_product_mismatch_lowers_score(self):
        rubric = Rubric("rubric-v2")
        other = ConditionFacts(
            cell_product="coin cell",
            format="coin",
            chemistry_families=("NMC", "graphite"),
            temperature_k=298.15,
        )
        match = rubric.evaluate(_candidate(1.0, "dimensionless"), TARGET)
        mismatch = rubric.evaluate(
            _candidate(1.0, "dimensionless", conditions=other), TARGET
        )
        assert mismatch.dimension_scores["cell_product"] < match.dimension_scores[
            "cell_product"
        ]
        assert mismatch.total < match.total

    def test_cell_specific_parameter_blocks_on_wrong_cell(self):
        rubric = Rubric("rubric-v2")
        wrong = ConditionFacts(
            cell_product="coin cell",
            format="coin",
            chemistry_families=("NMC", "graphite"),
            temperature_k=298.15,
            raw={"cell": "2032 coin cell"},
        )
        outcome = rubric.evaluate(
            _candidate(1.0, "um", canonical_id="neg_electrode_thickness", conditions=wrong),
            TARGET,
        )
        assert outcome.blocked
        assert any(b["dimension"] == "cell_product" for b in outcome.blockers)

    def test_electrolyte_match_scores_higher(self):
        rubric = Rubric("rubric-v2")
        same = ConditionFacts(
            cell_product="LG M50",
            chemistry_families=("NMC", "graphite"),
            raw={"electrolyte": "1 mol dm-3 LiPF6 in EC:EMC (3:7 V/V), 1 wt% VC"},
        )
        different = ConditionFacts(
            cell_product="LG M50",
            chemistry_families=("NMC", "graphite"),
            raw={"electrolyte": "1 M LiPF6 in EC:DMC"},
        )
        a = rubric.evaluate(
            _candidate(1.0, "m2.s-1", canonical_id="electrolyte_diffusivity", conditions=same),
            TARGET,
        )
        b = rubric.evaluate(
            _candidate(
                1.0, "m2.s-1", canonical_id="electrolyte_diffusivity", conditions=different
            ),
            TARGET,
        )
        assert a.dimension_scores["electrolyte"] > b.dimension_scores["electrolyte"]

    def test_electrolyte_family_weights_applied(self):
        rubric = Rubric("rubric-v2")
        assert rubric.weights_for("electrolyte_diffusivity") == rubric.electrolyte_weights
        assert rubric.weights_for("neg_electron_diffusivity") == rubric.weights


class TestResolveV2Paths:
    def test_form_mismatch_escalates_to_review(self):
        """Function-valued vs scalar is a modelling decision, not applicability."""
        rubric = Rubric("rubric-v2")
        scalar = _candidate(1.0, "dimensionless")
        function_valued = _candidate(
            2.0, "dimensionless", model_applicable=False, model_note="function-valued"
        )
        res = resolve_parameter("p", [scalar, function_valued], TARGET, rubric)
        assert res.decision is Decision.REVIEW
        assert res.review_required
        assert any("FORM" in r for r in res.rationale)

    def test_single_survivor_adopts_survivor(self):
        """Competing candidate blocked on chemistry → survivor adopted, not REVIEW."""
        rubric = Rubric("rubric-v2")
        good = _candidate(1.0, "dimensionless", source_id="a", source_document="a")
        bad = _candidate(
            2.0,
            "dimensionless",
            source_id="b",
            source_document="b",
            conditions=ConditionFacts(
                cell_product="other",
                chemistry_families=("LFP",),
                temperature_k=298.15,
            ),
        )
        res = resolve_parameter("p", [good, bad], TARGET, rubric)
        assert res.decision in (Decision.USE, Decision.FIX)
        assert res.chosen is good
        assert res.conflict is True
        assert len(res.rejected) == 1

    def test_trust_only_rejection_is_review(self):
        rubric = Rubric("rubric-v2")
        bad = _candidate(1.0, "dimensionless", quote="x", quote_verified=False)
        res = resolve_parameter("p", [bad], TARGET, rubric)
        assert res.decision is Decision.REVIEW
        assert res.review_required

    def test_applicability_rejection_is_reject(self):
        rubric = Rubric("rubric-v2")
        bad = _candidate(
            1.0,
            "dimensionless",
            conditions=ConditionFacts(chemistry_families=("LFP",)),
        )
        res = resolve_parameter("p", [bad], TARGET, rubric)
        assert res.decision is Decision.REJECT
        assert not res.review_required

    def test_method_divergence_with_small_margin_escalates(self):
        rubric = Rubric("rubric-v2", method_divergence_margin=0.5, review_margin=0.01)
        measured = _candidate(
            1.0, "dimensionless", method_class=MethodClass.MEASURED,
            source_id="a", source_document="a",
        )
        assumed = _candidate(
            2.0, "dimensionless", method_class=MethodClass.ASSUMED,
            source_id="b", source_document="b",
        )
        res = resolve_parameter("p", [measured, assumed], TARGET, rubric)
        # margin will be small relative to 0.5 → REVIEW on method divergence
        assert res.decision is Decision.REVIEW
        assert any("method class" in r for r in res.rationale)

    def test_rubric_version_recorded(self):
        rubric = Rubric("rubric-v2")
        res = resolve_parameter("p", [_candidate(1.0, "dimensionless")], TARGET, rubric)
        assert res.rubric_version == "rubric-v2"
