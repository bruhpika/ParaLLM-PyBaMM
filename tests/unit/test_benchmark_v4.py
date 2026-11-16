"""Unit tests for the private v4 condition benchmark (scorer + coercions).

No network, no LLM: the scorer is deterministic.
"""

from __future__ import annotations

import pytest

from pybamm_closed_loop.eval.benchmark_v4 import (
    CONDITION_FIELDS,
    NOT_STATED,
    V4Item,
    aggregate,
    build_v4_prompt,
    coerce_candidates,
    coerce_number,
    coerce_temperature,
    load_items,
    match_field,
    score_item,
)


def _item(**kw) -> V4Item:
    base = dict(
        item_id="V4-T1",
        category="A",
        document_id="doc",
        probe="9.61",
        parameter={"name": "negative electrode solid diffusivity", "value": 9.61e-15, "unit": "m2 s-1"},
        gold_conditions={
            "chemistry": "nca+graphite",
            "cell": "inr21700+50e",
            "format": "21700|cylindrical",
            "temperature_k": 298.15,
            "soc": NOT_STATED,
            "method": "gitt",
            "protocol": "c/10",
        },
        not_stated_fields=("soc",),
        evidence={"locator": "table"},
        notes="",
    )
    base.update(kw)
    return V4Item(**base)


def _candidate(**kw) -> dict:
    base = dict(
        parameter_name="negative electrode solid diffusivity",
        value=9.61e-15,
        unit="m2 s-1",
        definition="d",
        material="NCA cathode, graphite-SiOx anode",
        temperature=298.15,
        cell_config="Samsung INR21700-50E high energy cell, 21700",
        measurement_method="GITT",
        qualifier="measured",
        context="measured at 25 C; pulse protocol C/10",
        reported_uncertainty=None,
        source={"document_id": "doc", "page": 3, "locator": "Table VI", "quote": "9.61"},
    )
    base.update(kw)
    return base


class TestCoercions:
    def test_printed_exponent_forms(self):
        assert coerce_number("9.61·10−15") == pytest.approx(9.61e-15)
        assert coerce_number("1.10 × 10−13") == pytest.approx(1.1e-13)
        assert coerce_number("9.61e-15") == pytest.approx(9.61e-15)

    def test_plain_numbers(self):
        assert coerce_number("37.309") == pytest.approx(37.309)
        assert coerce_number("ca. 100") == pytest.approx(100.0)
        assert coerce_number(5) == 5

    def test_unparseable_is_unchanged(self):
        assert coerce_number("see Table VII") == "see Table VII"

    def test_temperature(self):
        assert coerce_temperature("25 °C") == pytest.approx(298.15)
        assert coerce_temperature("UNRESOLVED") is None
        assert coerce_temperature(298.15) == pytest.approx(298.15)

    def test_coerce_candidates_counts_changes(self):
        cands, n = coerce_candidates([_candidate(value="9.61·10−15", temperature="25 °C")])
        assert n == 2
        assert cands[0]["value"] == pytest.approx(9.61e-15)
        assert cands[0]["temperature"] == pytest.approx(298.15)


class TestFieldMatching:
    def test_not_stated_requires_absence(self):
        assert match_field("soc", NOT_STATED, None) is True
        assert match_field("soc", NOT_STATED, "UNRESOLVED") is True
        assert match_field("soc", NOT_STATED, "50 % SOC") is False

    def test_temperature_numeric(self):
        assert match_field("temperature_k", 298.15, 298.15) is True
        assert match_field("temperature_k", 298.15, 298.0) is True
        assert match_field("temperature_k", 298.15, 333.15) is False

    def test_keyword_alternatives_and_required_tokens(self):
        assert match_field("chemistry", "nca+graphite", "NCA cathode, graphite-SiOx anode") is True
        assert match_field("chemistry", "nca+graphite", "NCA cathode only") is False
        assert match_field("format", "21700|cylindrical", "21700 cell") is True

    def test_soc_numeric(self):
        assert match_field("soc", "50", "at 50 % SOC") is True
        assert match_field("soc", "50", "no SOC stated") is False


class TestScoring:
    def test_perfect_candidate(self):
        row = score_item(_item(), [_candidate()], abstained=False)
        assert row["field_hits"] == len(CONDITION_FIELDS)
        assert row["condition_score"] == 1.0
        assert row["parameter_value_ok"] is True
        assert row["invented_conditions"] == []

    def test_wrong_conditions_are_penalised(self):
        cand = _candidate(temperature=None, cell_config="UNRESOLVED", material="UNRESOLVED")
        row = score_item(_item(), [cand], abstained=False)
        assert row["condition_score"] < 0.6
        assert row["fields"]["temperature_k"] is False
        assert row["fields"]["cell"] is False

    def test_invented_condition_is_flagged(self):
        cand = _candidate(context="measured at 50 % SOC; pulse protocol C/10")
        row = score_item(_item(), [cand], abstained=False)
        assert "soc" in row["invented_conditions"]

    def test_value_selection_prefers_value_matched_candidate(self):
        good = _candidate()
        other = _candidate(value=1.10e-13, cell_config="Samsung INR21700-30T high power cell")
        row = score_item(_item(), [other, good], abstained=False)
        assert row["value_found"] is True
        assert row["parameter_value_ok"] is True
        assert row["fields"]["cell"] is True

    def test_abstention(self):
        row = score_item(_item(), [], abstained=True)
        assert row["condition_score"] == 0.0
        assert row["value_found"] is False

    def test_transport_error_rows_are_excluded_from_aggregate(self):
        rows = [
            score_item(_item(), [_candidate()], abstained=False),
            {"item_id": "x", "category": "A", "abstained": True, "n_candidates": 0,
             "fields": {}, "field_hits": 0, "field_total": len(CONDITION_FIELDS),
             "condition_score": 0.0, "parameter_value_ok": False,
             "parameter_unit_ok": False, "value_found": False,
             "invented_conditions": [], "transport_error": True},
        ]
        agg = aggregate(rows)
        assert agg["n_transport_errors"] == 1
        assert agg["all"]["n_items"] == 1
        assert agg["all"]["condition_field_accuracy"] == 1.0


class TestPrompt:
    def test_prompt_states_the_numeric_contract(self):
        prompt = build_v4_prompt()
        assert "JSON NUMBER" in prompt
        assert "document_id" in prompt and "quote" in prompt
        assert "not stated" in prompt.lower()


class TestFixtureLoading:
    def test_private_fixture_loads(self):
        from pathlib import Path

        path = Path("data/private_v4/fixture/benchmark_v4.jsonl")
        if not path.exists():
            pytest.skip("private fixture not present in this checkout")
        items = load_items(path)
        assert len(items) >= 20
        assert {i.category for i in items} >= {"A", "B", "C", "D", "E"}
        for item in items:
            assert set(item.gold_conditions) == set(CONDITION_FIELDS)
            for field, value in item.gold_conditions.items():
                if value == NOT_STATED:
                    assert field in item.not_stated_fields
