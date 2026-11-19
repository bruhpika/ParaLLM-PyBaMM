"""No-network tests for the v4 retrieval distractor stress report."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

_PATH = REPO_ROOT / "benchmarks/v2/report_retrieval_recall.py"
_SPEC = importlib.util.spec_from_file_location("report_retrieval_recall", _PATH)
assert _SPEC and _SPEC.loader
MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MOD)

from pybamm_closed_loop.eval.retrieval_arms import evaluate_recall  # noqa: E402
from pybamm_closed_loop.literature.index import BM25Index  # noqa: E402
from pybamm_closed_loop.literature.ingest import Segment  # noqa: E402


def _summary(value: float, k_values=(1, 3, 5, 10)) -> dict:
    return {
        "n_items": 30,
        "k_values": list(k_values),
        "evidence_k": 8,
        "recall": {f"recall@{k}": value for k in k_values},
    }


def test_stress_report_writes_side_by_side_numbers(tmp_path):
    MOD._write_stress_report(
        _summary(0.3), _summary(0.1), tmp_path, "v4 parameter name and unit only", (4, 10)
    )
    md = (tmp_path / "retrieval_recall_distractors.md").read_text()
    assert "| 1 | 0.300 | 0.000 |" not in md  # sanity: values come from arguments
    assert "| 1 | 0.300 | 0.100 |" in md
    assert "| 10 | 0.300 | 0.100 |" in md
    assert "overstates retrieval quality" in md
    payload = json.loads((tmp_path / "retrieval_recall_distractors.json").read_text())
    assert payload["small_corpus"]["documents"] == 4
    assert payload["full_corpus"]["documents"] == 10
    assert payload["full_corpus"]["recall"]["recall@1"] == 0.1


def test_stress_is_v4_only(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["report", "--benchmark", "v3", "--stress"])
    with pytest.raises(SystemExit, match="v4"):
        MOD.main()


class _FakeStore:
    def __init__(self, root: Path, segments: list[Segment]):
        self.raw_dir = root
        self._segments = segments

    def segments(self, document_id=None):
        if document_id is None:
            return list(self._segments)
        return [s for s in self._segments if s.document_id == document_id]


def test_full_corpus_distractors_lower_recall(tmp_path):
    probe = "Negative particle diffusivity"
    doc_id = "docA"
    (tmp_path / f"{doc_id}.txt").write_text(f"{probe} 3.3e-14 m2.s-1")
    gold = Segment(
        segment_id=f"{doc_id}#seg00000",
        document_id=doc_id,
        char_start=0,
        char_end=len(probe),
        page=None,
        heading=None,
        text=f"{probe} 3.3e-14 m2.s-1",
    )
    distractors = [
        Segment(
            segment_id=f"noise{i}#seg00000",
            document_id=f"noise{i}",
            char_start=0,
            char_end=len(probe) * 5,
            page=None,
            heading=None,
            text=" ".join([probe, "m2.s-1"] * 20),
        )
        for i in range(60)
    ]
    item = SimpleNamespace(
        item_id="it-1",
        document_id=doc_id,
        probe=probe,
        parameter={"name": probe, "unit": "m2.s-1"},
    )
    store = _FakeStore(tmp_path, [gold])
    full_store = _FakeStore(tmp_path, [gold, *distractors])

    small, _ = evaluate_recall([item], store, index=BM25Index(store.segments()), k_values=(1,))
    full, _ = evaluate_recall(
        [item], store, index=BM25Index(full_store.segments()), k_values=(1,)
    )
    assert small["recall"]["recall@1"] == 1.0
    assert full["recall"]["recall@1"] <= small["recall"]["recall@1"]
    assert full["recall"]["recall@1"] == 0.0
