"""Unit tests for the applicability case schema and agreement aggregation."""

from __future__ import annotations

import json
from pathlib import Path

from pybamm_closed_loop.eval.assembly_cases import (
    ApplicabilityCase,
    agreement,
    load_cases,
    score_case,
)
from pybamm_closed_loop.assembly import Rubric, TargetSpecification

TARGET = TargetSpecification(
    target_id="lgm50",
    cell_product="LG M50",
    chemistry_families=("NMC", "graphite"),
    format="21700",
    temperature_k=298.15,
    soc="50%",
    electrolyte="1 mol dm-3 LiPF6 in EC:EMC (3:7 V/V), 1 wt% VC",
)


def _case(**kw) -> ApplicabilityCase:
    base = dict(
        case_id="C1",
        target_id="lgm50",
        parameter="p",
        candidates=[
            {
                "value": 1.0,
                "unit": "dimensionless",
                "method_class": "measured",
                "source_id": "doc-a",
                "source_document": "doc-a",
                "conditions": {
                    "cell": "LG M50",
                    "chemistry": "NMC",
                    "temperature_k": 298.15,
                },
            }
        ],
        expert_decision="USE",
        expert_choice=0,
        case_class="conflict",
    )
    base.update(kw)
    return ApplicabilityCase(**base)


class TestCaseSchema:
    def test_roundtrip_to_dict(self):
        c = _case(reviewed_by="owner", reviewed_on="2026-11-20")
        d = c.to_dict()
        assert d["case_id"] == "C1"
        assert d["expert_decision"] == "USE"
        assert d["reviewed_by"] == "owner"
        assert d["reviewed_on"] == "2026-11-20"

    def test_load_cases_reads_review_metadata(self, tmp_path):
        path = tmp_path / "cases.jsonl"
        path.write_text(
            json.dumps(
                {
                    "case_id": "C1",
                    "target_id": "lgm50",
                    "parameter": "p",
                    "candidates": [{"value": 1.0, "source_id": "doc-a"}],
                    "expert_decision": "USE",
                    "reviewed_by": "owner",
                    "reviewed_on": "2026-11-20",
                }
            )
            + "\n"
        )
        cases = load_cases(path)
        assert cases[0].reviewed_by == "owner"
        assert cases[0].reviewed_on == "2026-11-20"

    def test_score_case_reports_source_counts(self):
        c = _case(
            candidates=[
                {
                    "value": 1.0,
                    "unit": "dimensionless",
                    "method_class": "measured",
                    "source_id": "doc-a",
                    "source_document": "doc-a",
                },
                {
                    "value": 2.0,
                    "unit": "dimensionless",
                    "method_class": "measured",
                    "source_id": "doc-b",
                    "source_document": "doc-b",
                },
            ],
            expert_decision="REVIEW",
            expert_choice=None,
            ambiguous=True,
            case_class="ambiguous",
        )
        row = score_case(c, Rubric("rubric-v2"), TARGET)
        assert row["n_candidates"] == 2
        assert row["n_distinct_sources"] == 2
        assert row["cross_source"] is True


class TestAgreement:
    def test_perfect_agreement(self):
        rows = [
            {
                "decision_match": True,
                "match": True,
                "ambiguous": False,
                "case_class": "conflict",
                "chosen_match": True,
                "reviewed_by": None,
            },
            {
                "decision_match": True,
                "match": True,
                "ambiguous": False,
                "case_class": "conflict",
                "chosen_match": True,
                "reviewed_by": "owner",
            },
        ]
        agg = agreement(rows)
        assert agg["all"]["decision_agreement"] == 1.0
        assert agg["all"]["n_cases"] == 2
        assert agg["label_status"] == {"drafted": 1, "reviewed": 1}

    def test_mismatch_counted(self):
        rows = [
            {
                "decision_match": False,
                "match": False,
                "ambiguous": True,
                "case_class": "ambiguous",
                "chosen_match": False,
                "reviewed_by": None,
            }
        ]
        agg = agreement(rows)
        assert agg["all"]["decision_agreement"] == 0.0
        assert agg["all"]["n_mismatched_decision"] == 1
        assert agg["class:ambiguous"]["n_cases"] == 1

    def test_empty_rows(self):
        assert agreement([]) == {}


class TestPrivateCaseSet:
    def test_load_if_present(self):
        path = Path("data/private_v4/applicability_cases_v1.jsonl")
        if not path.exists():
            import pytest

            pytest.skip("private case set not present")
        cases = load_cases(path)
        assert len(cases) >= 20
        assert all(c.expert_decision for c in cases)
        # owner approval is recorded on every case (2026-11-20)
        assert all(c.reviewed_by for c in cases)
        assert all(c.reviewed_on for c in cases)
        # every candidate value must be present (no invented placeholders)
        for c in cases:
            assert c.candidates
            for cand in c.candidates:
                assert "value" in cand
                assert "source_id" in cand or "source_document" in cand
