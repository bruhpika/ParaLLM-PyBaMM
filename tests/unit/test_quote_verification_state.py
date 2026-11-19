"""Quote verification reports an explicit state when source text is absent."""

from __future__ import annotations

from pybamm_closed_loop.assembly.report import verify_record_quotes


def _record(doc_id: str, quote: str) -> dict:
    return {
        "canonical_id": "p",
        "evidence": {"source": {"document_id": doc_id, "quote": quote}},
    }


def test_missing_text_is_reported_not_silently_passed():
    records, stats = verify_record_quotes(
        [_record("chen2020_supplement_s1", "Table S1. Data sheet from the manufacturer.")],
        {},
    )
    source = records[0]["evidence"]["source"]
    assert source["quote_verification_state"] == "source text not present locally"
    assert source["quote_verified"] is None
    assert stats["n_no_text"] == 1
    assert stats["no_text_state"] == "source text not present locally"
    assert stats["n_checked"] == 0
    assert stats["n_verified"] == 0


def test_present_text_is_checked_with_explicit_state():
    records, stats = verify_record_quotes(
        [_record("doc", "A verbatim quote.")],
        {"doc": "Evidence says: A verbatim quote. Done."},
    )
    source = records[0]["evidence"]["source"]
    assert source["quote_verification_state"] == "verified"
    assert source["quote_verified"] is True
    bad, bad_stats = verify_record_quotes(
        [_record("doc", "not in the text")], {"doc": "other text"}
    )
    assert bad[0]["evidence"]["source"]["quote_verification_state"] == "failed verbatim check"
    assert bad_stats["n_failed"] == 1
    assert stats["n_verified"] == 1
