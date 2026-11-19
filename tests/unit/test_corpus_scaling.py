"""Deterministic synthetic-distractor corpus construction (no downloads)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "corpus_scaling", REPO_ROOT / "benchmarks/v2/corpus_scaling.py"
)
assert _SPEC and _SPEC.loader
MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MOD)

from pybamm_closed_loop.literature.ingest import Segment  # noqa: E402


def _pool():
    return [
        Segment(f"doc{d}#seg{i}", f"doc{d}", 0, 5, None, None, f"text {d}-{i}")
        for d in range(4)
        for i in range(6)
    ]


def test_distractors_are_deterministic_and_unique():
    pool = _pool()
    a = MOD.synthetic_distractors(pool, 2, seed=7)
    b = MOD.synthetic_distractors(pool, 2, seed=7)
    assert a == b
    assert len(a) == 40
    assert len({s.segment_id for s in a}) == 40
    assert {s.document_id for s in a} == {"synthetic_distractor_000", "synthetic_distractor_001"}
    assert MOD.synthetic_distractors(pool, 2, seed=8) != a


def test_distractors_never_copy_gold_document_ids():
    pool = _pool()
    out = MOD.synthetic_distractors(pool, 1, seed=1)
    assert all(s.document_id.startswith("synthetic_distractor_") for s in out)
    assert not any(s.document_id in {"doc0", "doc1", "doc2", "doc3"} for s in out)


def test_distractor_size_respects_small_pool():
    pool = _pool()[:2]
    out = MOD.synthetic_distractors(pool, 1, seed=1)
    assert len(out) == 2
