"""Unit tests for the V2.5 evidence layer (deterministic, no network)."""

from __future__ import annotations

from pathlib import Path

from pybamm_closed_loop.literature.evidence import (
    build_evidence_window,
    document_conditions,
    extract_conditions,
)

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/literature_store/raw"


def _raw(doc: str) -> str:
    return (RAW / f"{doc}.txt").read_text()


def _article_raw() -> str:
    import pytest

    from pybamm_closed_loop.literature.availability import (
        ARTICLE_MISSING_REASON,
        article_text_available,
    )

    if not article_text_available(ROOT / "data/literature_store"):
        pytest.skip(f"SKIP: {ARTICLE_MISSING_REASON}")
    return _raw("chen2020_jes_167_080534")


class TestConditionExtraction:
    def test_temperature_celsius_to_kelvin(self):
        facts = extract_conditions("The cell was tested in a chamber at 25 °C.")
        assert facts.temperature_k == pytest_approx(298.15)
        assert facts.coverage()["temperature"] is True

    def test_temperature_kelvin(self):
        facts = extract_conditions("All measurements were performed at 298.15 K.")
        assert facts.temperature_k == pytest_approx(298.15)

    def test_soc_and_rate(self):
        facts = extract_conditions("Impedance spectra were recorded at 50% SOC at 0.1C.")
        assert facts.soc_percent == 50
        assert 0.1 in facts.c_rates

    def test_no_conditions_is_empty(self):
        facts = extract_conditions("A short sentence without conditions.")
        assert facts.coverage() == {
            "temperature": False,
            "soc": False,
            "c_rate": False,
            "cell": False,
            "chemistry": False,
            "method": False,
        }


def pytest_approx(value: float):
    import pytest

    return pytest.approx(value)


class TestEvidenceWindow:
    def test_probe_is_kept_verbatim(self):
        raw = _raw("laue2021_jappl_electrochem_51_1253")
        window = build_evidence_window(raw, "doc", "55.25")
        assert "55.25" in window.text
        assert window.char_end > window.char_start

    def test_window_is_a_verbatim_substring(self):
        raw = _raw("laue2021_jappl_electrochem_51_1253")
        window = build_evidence_window(raw, "doc", "55.25")
        assert raw[window.char_start : window.char_end] == window.text

    def test_expansion_grows_the_window(self):
        raw = _raw("laue2021_jappl_electrochem_51_1253")
        compact = build_evidence_window(raw, "doc", "55.25", compact_chars=260, expand_chars=260)
        expanded = build_evidence_window(raw, "doc", "55.25", compact_chars=260, expand_chars=900)
        assert len(expanded.text) >= len(compact.text)

    def test_missing_probe_raises(self):
        raw = _raw("laue2021_jappl_electrochem_51_1253")
        try:
            build_evidence_window(raw, "doc", "this string is not in the document")
        except ValueError:
            return
        raise AssertionError("expected ValueError for a missing probe")


class TestDocumentConditions:
    def test_finds_setup_statements_in_real_document(self):
        raw = _article_raw()
        doc_conditions = document_conditions(raw, max_sentences=8)
        coverage = doc_conditions.coverage()
        assert coverage["temperature"] is True
        assert coverage["cell"] is True
        assert coverage["chemistry"] is True

    def test_statements_are_verbatim(self):
        raw = _article_raw()
        doc_conditions = document_conditions(raw, max_sentences=8)
        for sentence in doc_conditions.sentences:
            assert sentence in raw

    def test_deterministic(self):
        raw = _raw("laue2021_jappl_electrochem_51_1253")
        a = document_conditions(raw, max_sentences=6).sentences
        b = document_conditions(raw, max_sentences=6).sentences
        assert a == b


class TestEvidenceBlockSections:
    """expanded/v25 blocks always carry the cell + setup sections.

    This is the mechanism behind the v4 cell-identity condition (the table
    block can list several cells; the cell-identification section names the
    one the experiment used). Locked in here so a future edit cannot drop
    the sections silently; the LLM-side effect of the v25 cell regression is
    measured only on a live re-run.
    """

    TEXT = (
        "The mean negative particle diffusivity is 9.61·10−15 m2 s−1 as "
        "measured by GITT.\n\n"
        "All experiments were performed at 25 °C with a state of charge "
        "window of 50% between 2.5 and 4.2 V.\n\n"
        "LG M50 21700 cylindrical cells were used throughout this study.\n"
    )

    def test_sections_present_in_expanded_and_v25(self, tmp_path):
        from types import SimpleNamespace

        from pybamm_closed_loop.eval.benchmark_p5 import _evidence_block
        from pybamm_closed_loop.literature.ingest import DocumentStore

        store = DocumentStore(tmp_path / "store")
        store.ingest_text("doc1", self.TEXT)
        item = SimpleNamespace(
            item_id="T1", document_id="doc1", probe="9.61·10−15",
            passage_probe=None,
        )
        for mode in ("expanded", "v25"):
            block = _evidence_block(item, store, mode)
            assert "CELL IDENTIFICATION" in block, mode
            assert "LG M50" in block, mode
            assert "EXPERIMENT CONDITIONS" in block, mode
            assert "25 °C" in block, mode
            # the probe window itself is present
            assert "9.61·10−15" in block, mode
