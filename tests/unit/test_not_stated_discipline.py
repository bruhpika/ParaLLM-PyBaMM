"""Unit tests for the V2.5 verification pass + `not_stated` discipline.

Deterministic, no network: the rules only inspect the evidence text that was
shown to the model.
"""

from __future__ import annotations

from pybamm_closed_loop.eval.benchmark_v4 import (
    CONDITION_FIELDS,
    apply_discipline,
    enforce_not_stated,
    evidence_support,
    score_with_discipline,
)
from pybamm_closed_loop.literature.evidence import (
    cell_identification_sentences,
    verify_quote_in_evidence,
)

EVIDENCE = """
TABLE VI. Parameter values of the Samsung INR21700-50E cell.
Diffusion coefficient of anode Dn = 9.61·10−15 m2 s−1.
All measurements were performed in a climate chamber at 25 °C (298.15 K)
using GITT with a C/10 protocol. SOC was not stated in the evidence.
"""


def _cand(**kw) -> dict:
    base = dict(
        parameter_name="Diffusion coefficient of anode Dn",
        value=9.61e-15,
        unit="m2 s−1",
        material="graphite-SiOx anode",
        temperature=298.15,
        cell_config="Samsung INR21700-50E high energy cell, 21700",
        measurement_method="GITT",
        qualifier="measured",
        context="measured at 25 C; pulse protocol C/10",
        source={"document_id": "doc", "page": 3, "locator": "Table VI", "quote": "9.61"},
    )
    base.update(kw)
    return base


class TestVerifyQuote:
    def test_quote_in_evidence(self):
        assert verify_quote_in_evidence("9.61", EVIDENCE) is True

    def test_quote_not_in_evidence(self):
        assert verify_quote_in_evidence("not there at all", EVIDENCE) is False

    def test_empty_quote(self):
        assert verify_quote_in_evidence("", EVIDENCE) is False

    def test_whitespace_and_unicode_folded(self):
        assert verify_quote_in_evidence("climate  chamber", EVIDENCE) is True


class TestEvidenceSupport:
    def test_temperature_supported(self):
        assert evidence_support(EVIDENCE, "temperature_k", 298.15) is True

    def test_temperature_unsupported(self):
        assert evidence_support(EVIDENCE, "temperature_k", 333.15) is False

    def test_cell_supported_when_distinguishing_token_present(self):
        assert evidence_support(EVIDENCE, "cell", "INR21700-50E high energy cell") is True

    def test_cell_unsupported_when_wrong_model(self):
        assert evidence_support(EVIDENCE, "cell", "INR21700-30T high power cell") is False

    def test_generic_cell_words_alone_are_not_enough(self):
        # "21700" alone is generic and appears; "30t" does not
        assert evidence_support(EVIDENCE, "cell", "21700 30T") is False

    def test_method_supported(self):
        assert evidence_support(EVIDENCE, "method", "GITT") is True

    def test_method_unsupported(self):
        assert evidence_support(EVIDENCE, "method", "EIS only") is False

    def test_none_value_is_unsupported(self):
        assert evidence_support(EVIDENCE, "method", None) is False


class TestEnforceNotStated:
    def test_supported_fields_are_kept(self):
        cleaned, dropped = enforce_not_stated(EVIDENCE, _cand())
        assert "temperature_k" not in dropped
        assert cleaned["temperature"] == 298.15

    def test_unsupported_temperature_is_dropped(self):
        cleaned, dropped = enforce_not_stated(
            EVIDENCE, _cand(temperature=333.15)
        )
        assert "temperature_k" in dropped
        assert cleaned["temperature"] is None

    def test_unsupported_cell_is_dropped(self):
        cleaned, dropped = enforce_not_stated(
            EVIDENCE, _cand(cell_config="INR21700-30T high power cell")
        )
        assert "cell" in dropped
        assert cleaned["cell_config"] is None

    def test_dropped_fields_are_reported_not_hidden(self):
        _, dropped = enforce_not_stated(
            EVIDENCE, _cand(temperature=333.15, measurement_method="EIS")
        )
        assert set(dropped) >= {"temperature_k", "method"}

    def test_context_soc_fragment_stripped_when_unsupported(self):
        # evidence never states SOC as a condition (the "50" inside
        # INR21700-50E is a product name, not a SOC); context claims 50%
        cleaned, dropped = enforce_not_stated(
            EVIDENCE, _cand(context="measured at 50 % SOC; pulse protocol C/10")
        )
        assert "soc" in dropped
        assert "50" not in (cleaned.get("context") or "")


class TestApplyDiscipline:
    def test_stats_shape(self):
        cleaned, stats = apply_discipline(EVIDENCE, [_cand()])
        assert len(cleaned) == 1
        assert stats["n_dropped_conditions"] >= 0
        assert stats["quote_in_evidence_rate"] is not None
        assert cleaned[0]["_quote_in_evidence"] is True

    def test_quote_flagged_when_not_in_evidence(self):
        cleaned, stats = apply_discipline(
            EVIDENCE, [_cand(source={"document_id": "doc", "quote": "absent quote"})]
        )
        assert cleaned[0]["_quote_in_evidence"] is False
        assert stats["n_quote_not_in_evidence"] == 1
        assert stats["quote_in_evidence_rate"] == 0.0

    def test_empty_candidates(self):
        cleaned, stats = apply_discipline(EVIDENCE, [])
        assert cleaned == []
        assert stats["quote_in_evidence_rate"] is None


class TestScoreWithDiscipline:
    def _item(self):
        from pybamm_closed_loop.eval.benchmark_v4 import V4Item

        return V4Item(
            item_id="T1",
            category="A",
            document_id="doc",
            probe="9.61",
            parameter={"name": "anode Dn", "value": 9.61e-15, "unit": "m2 s−1"},
            gold_conditions={
                "chemistry": "graphite+silicon|siox|si",
                "cell": "inr21700+50e",
                "format": "21700|cylindrical",
                "temperature_k": 298.15,
                "soc": "not_stated",
                "method": "gitt",
                "protocol": "c/10",
            },
            not_stated_fields=("soc",),
            evidence={"locator": "table"},
        )

    def test_discipline_metrics_present(self):
        row = score_with_discipline(
            self._item(), EVIDENCE, [_cand()], transport_error=False
        )
        assert "n_dropped_conditions" in row
        assert "raw_condition_score" in row
        assert "quote_in_evidence_rate" in row
        assert row["transport_error"] is False

    def test_transport_error_row(self):
        row = score_with_discipline(self._item(), EVIDENCE, [], transport_error=True)
        assert row["transport_error"] is True
        assert row["abstained"] is True
        assert row["raw_condition_score"] == 0.0

    def test_all_condition_fields_covered_by_discipline(self):
        # every FIELD_SOURCE mapping target is a CONDITION_FIELDS member
        from pybamm_closed_loop.eval.benchmark_v4 import FIELD_SOURCE

        assert set(FIELD_SOURCE) == set(CONDITION_FIELDS)


class TestCellIdentificationSentences:
    def test_finds_cell_sentence(self):
        text = (
            "The commercial LG M50 cell was used throughout. "
            "All tests ran at 25 C with GITT."
        )
        sents = cell_identification_sentences(text)
        assert any("LG M50" in s or "M50" in s for s in sents)

    def test_empty_text(self):
        assert cell_identification_sentences("") == []

    def test_deterministic(self):
        text = "An INR21700-50E cell was tested with GITT at 25 °C."
        assert cell_identification_sentences(text) == cell_identification_sentences(text)
