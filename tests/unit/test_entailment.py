"""Unit tests for the label-free deterministic entailment pass."""

from __future__ import annotations

from pybamm_closed_loop.eval.benchmark_v4 import score_with_discipline
from pybamm_closed_loop.eval.entailment import (
    _quote_numbers,
    apply_entailment,
    verify_candidate,
)


def _candidate(value=9.61e-15, quote=None, **overrides):
    cand = {
        "parameter_name": "anode diffusion coefficient",
        "value": value,
        "unit": "m2 s-1",
        "definition": "test",
        "material": "graphite-SiOx",
        "temperature": None,
        "cell_config": "INR21700-50E",
        "measurement_method": "GITT",
        "qualifier": "measured",
        "context": "SOC not stated in the evidence.",
        "reported_uncertainty": None,
        "source": {
            "document_id": "UNRESOLVED",
            "page": None,
            "locator": "UNRESOLVED",
            "quote": quote or "Diffusion coefficient of anode 9.61·10−15",
        },
    }
    cand.update(overrides)
    return cand


EVIDENCE = (
    "Table: High energy (HE): INR21700 -50E\n"
    "Diffusion coefficient of anode 9.61·10−15 m2 s-1\n"
)


class TestQuoteNumbers:
    def test_scientific_notation_is_read(self):
        numbers = _quote_numbers("9.61·10−15 and 1.10·10^-13 and 25.3")
        assert any(abs(n - 9.61e-15) / 9.61e-15 < 1e-6 for n in numbers)
        assert any(abs(n - 1.10e-13) / 1.10e-13 < 1e-6 for n in numbers)
        assert any(abs(n - 25.3) < 1e-6 for n in numbers)


class TestVerifyCandidate:
    def test_value_in_quote_is_kept(self):
        cleaned, reasons = verify_candidate(EVIDENCE, _candidate())
        assert "value_not_in_quote" not in reasons
        assert cleaned["material"] == "graphite-SiOx"

    def test_value_not_in_quote_is_a_definitive_drop(self):
        cleaned, reasons = verify_candidate(
            EVIDENCE, _candidate(value=1.0, quote="anode diffusion coefficient")
        )
        assert "value_not_in_quote" in reasons
        kept, stats = apply_entailment(EVIDENCE, [_candidate(value=1.0)])
        assert kept == []
        assert stats["n_entailment_dropped"] == 1

    def test_role_only_material_is_cleared(self):
        cleaned, reasons = verify_candidate(
            EVIDENCE, _candidate(material="HE anode")
        )
        assert cleaned["material"] is None
        assert "role_only_material" in reasons

    def test_imported_cell_name_is_cleared(self):
        cleaned, reasons = verify_candidate(
            EVIDENCE, _candidate(cell_config="Samsung 18650 cell")
        )
        assert cleaned["cell_config"] is None
        assert "cell_not_in_evidence" in reasons

    def test_non_verbatim_quote_is_flagged_but_not_dropped(self):
        cleaned, reasons = verify_candidate(
            EVIDENCE, _candidate(quote="this quote is not in the evidence")
        )
        assert "quote_not_verbatim" in reasons
        assert cleaned["value"] == 9.61e-15


class TestDisciplineIntegration:
    def test_entailment_discipline_scores_without_model_calls(self):
        row = score_with_discipline(
            _item_for_integration(),
            EVIDENCE,
            [_candidate()],
            transport_error=False,
            discipline="entailment",
        )
        assert row["discipline"] == "entailment"
        assert row["n_entailment_candidates"] == 1
        assert row["n_entailment_dropped"] == 0


def _item_for_integration():
    from pybamm_closed_loop.eval.benchmark_v4 import V4Item

    return V4Item(
        item_id="V4-T1",
        category="A",
        document_id="doc",
        probe="9.61",
        parameter={"name": "anode diffusion coefficient", "value": 9.61e-15, "unit": "m2 s-1"},
        gold_conditions={
            "chemistry": "not_stated",
            "cell": "not_stated",
            "format": "not_stated",
            "temperature_k": "not_stated",
            "soc": "not_stated",
            "method": "not_stated",
            "protocol": "not_stated",
        },
        not_stated_fields=tuple("chemistry cell format temperature_k soc method protocol".split()),
        evidence={"locator": "table"},
        notes="",
    )
