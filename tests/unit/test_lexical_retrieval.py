"""Cheap lexical expansion tests (no model calls, no gold input)."""

from __future__ import annotations

from pybamm_closed_loop.literature.index import BM25Index, expand_query
from pybamm_closed_loop.literature.ingest import Segment
from pybamm_closed_loop.literature.lexical import (
    lexical_search,
    lexical_terms,
    registry_aliases,
    symbol_terms,
    unit_query_terms,
)


def test_unit_terms_are_declared_only_and_deterministic():
    assert unit_query_terms("m2.s-1") == unit_query_terms("m2.s-1")
    assert "m2" in unit_query_terms("m2 s-1")
    assert "s" in unit_query_terms("m2.s-1")
    assert unit_query_terms("dimensionless") == []


def test_registry_aliases_use_public_names_only():
    records = [
        {
            "canonical_id": "neg_particle_diffusivity",
            "pybamm_names": ["Negative particle diffusivity [m2.s-1]"],
        },
        {"canonical_id": "unrelated", "pybamm_names": ["Unrelated thing"]},
    ]
    aliases = registry_aliases("negative particle diffusivity", records)
    assert "neg" in aliases and "diffusivity" in aliases
    assert "unrelated" not in aliases


def test_symbol_terms_only_from_existing_synonym_groups():
    assert "j0" in symbol_terms("exchange current density")
    assert "sigma" in symbol_terms("electrode conductivity")
    assert symbol_terms("colour of the sky") == []


def test_lexical_terms_do_not_add_gold_conditions():
    base = "negative particle diffusivity m2.s-1"
    terms = lexical_terms(base, unit="m2.s-1", use_registry=False)
    assert "temperature" not in terms and "298" not in terms
    assert set(expand_query(base)).issubset(set(terms))


def test_lexical_search_boosts_without_changing_default_bm25():
    segs = [
        Segment("d#0", "d", 0, 20, 1, "Table 1", "porosity 0.4 m2.s-1"),
        Segment("d#1", "d", 21, 40, 2, None, "porosity prose without numbers"),
    ]
    index = BM25Index(segs)
    base = index.search("porosity", k=2)
    base_scores = index.score_terms(expand_query("porosity"))
    assert [s.segment_id for s, _ in base] == [
        segs[i].segment_id for i in sorted(range(2), key=lambda i: -base_scores[i])
    ]
    boosted = lexical_search(
        index,
        ["porosity"],
        k=2,
        boost_tables=True,
        unit_terms=["m2", "s"],
        boost_units=True,
    )
    assert boosted[0][0].segment_id == "d#0"
    assert boosted[0][1] > base_scores[0]
