"""Unit tests: query-only retrieval arms and recall labels (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pybamm_closed_loop.eval.retrieval_arms import (
    ORACLE_LABEL,
    evaluate_recall,
    gold_segment_ids,
    query_for_item,
    query_from_parameter,
    recall_at_k,
    retrieval_context_for_item,
)
from pybamm_closed_loop.literature.index import BM25Index
from pybamm_closed_loop.literature.ingest import DocumentStore

TEXT_A = """Table I. Negative electrode parameters for the LGM50.

The negative electrode solid diffusivity is 9.61e-15 m2 s-1 measured by GITT
at 25 C.
"""

TEXT_B = """Positive electrode geometry.

The positive electrode thickness is 75 um.
"""


def _store(tmp_path):
    store = DocumentStore(tmp_path / "store")
    store.ingest_text("docA", TEXT_A, title="Diffusivity")
    store.ingest_text("docB", TEXT_B, title="Thickness")
    return store


def _v4_item(document_id="docA", probe="9.61e-15"):
    return SimpleNamespace(
        item_id="V4-T1",
        document_id=document_id,
        probe=probe,
        parameter={
            "name": "negative electrode solid diffusivity",
            "unit": "m2 s-1",
            "value": 9.61e-15,
            "as_printed": "9.61e-15",
        },
        gold_conditions={"temperature_k": "GOLDONLY", "method": "GITT"},
        evidence={"locator": "GOLDONLY"},
        notes="GOLDONLY probe context",
    )


def _v3_item(document_id="docA", probe="9.61e-15"):
    return SimpleNamespace(
        item_id="V3-T1",
        document_id=document_id,
        passage_probe=probe,
        facets={
            "parameter_names": ["negative electrode solid diffusivity"],
            "materials": ["graphite"],
            "cell_chemistry": ["LGM50"],
            "cell_format": ["21700"],
            "conditions": {"temperature": 298.15},
            "techniques": ["GITT"],
        },
    )


def test_oracle_label_is_a_location_oracle_not_an_upper_bound():
    assert "probe window" in ORACLE_LABEL
    assert "NOT a performance upper bound" in ORACLE_LABEL


def test_v4_query_uses_only_parameter_name_and_unit():
    query = query_from_parameter(_v4_item())
    assert query == "negative electrode solid diffusivity m2 s-1"
    for leaked in ("GOLDONLY", "9.61e-15", "docA", "GITT"):
        assert leaked not in query


def test_v3_query_uses_facets_not_probe():
    item = _v3_item()
    query = query_for_item(item)
    assert "negative electrode solid diffusivity" in query
    assert "21700" in query
    assert item.passage_probe not in query


def test_retrieval_searches_full_store_not_item_document(tmp_path):
    store = _store(tmp_path)
    item = _v4_item(document_id="docB", probe="75 um")
    context = retrieval_context_for_item(item, store, k=2)
    assert context.segments
    assert context.segments[0].document_id == "docA"
    assert "docB" not in context.retrieved_from


def test_gold_segment_ids_are_derived_from_probe(tmp_path):
    store = _store(tmp_path)
    item = _v4_item()
    gold = gold_segment_ids(item, store)
    segments = {s.segment_id: s for s in store.segments("docA")}
    assert gold
    assert any("9.61e-15" in segments[sid].text for sid in gold)


def test_recall_at_k_is_item_level():
    gold = ["docA#seg00001"]
    assert recall_at_k(["docB#seg00001", "docA#seg00001"], gold, 1) == 0.0
    assert recall_at_k(["docB#seg00001", "docA#seg00001"], gold, 2) == 1.0
    with pytest.raises(ValueError):
        recall_at_k([], gold, 0)


def test_evaluate_recall_reports_ks_and_audit(tmp_path):
    store = _store(tmp_path)
    items = [_v4_item(), _v4_item(document_id="docB", probe="75 um")]
    summary, rows = evaluate_recall(
        items,
        store,
        index=BM25Index(store.segments()),
        k_values=(1, 3),
        evidence_k=3,
    )
    assert summary["n_items"] == 2
    assert set(summary["recall"]) == {"recall@1", "recall@3"}
    assert len(rows) == 2
    assert all(row["query"] and row["gold_segment_ids"] for row in rows)
    assert rows[0]["retrieved_segment_ids"]
