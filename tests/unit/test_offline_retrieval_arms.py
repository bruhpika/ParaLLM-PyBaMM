"""Offline retrieval arm wiring and side-by-side table parsing tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(relative: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p5_tuned_arm_is_offline_and_labelled():
    from pybamm_closed_loop.eval.benchmark_p5 import OFFLINE_CONDITIONS
    from pybamm_closed_loop.eval.retrieval_arms import tuned_index
    from pybamm_closed_loop.literature.index import BM25Index, SYNONYMS
    from pybamm_closed_loop.literature.ingest import Segment

    assert "offline_bm25_tuned" in OFFLINE_CONDITIONS
    runner = _load("benchmarks/p5/run_ablation.py", "p5_runner")
    assert "tuned b=0.5" in runner._CONDITION_LABELS["offline_bm25_tuned"]
    segs = [Segment("d#0", "d", 0, 4, None, None, "porosity 0.4")]
    base = BM25Index(segs)
    tuned = tuned_index(base)
    assert tuned.k1 == base.k1 and tuned.b == 0.5
    assert SYNONYMS["porosity"][0] == "porosity"


def test_v4_offline_arm_is_labelled_and_needs_no_live_flag():
    runner = _load("benchmarks/v2/run_v4_evaluation.py", "v4_runner")
    assert runner._is_offline_mode(runner.OFFLINE_TUNED_MODE)
    assert "deterministic offline" in runner._arm_label(runner.OFFLINE_TUNED_MODE)
    assert runner._is_retrieval_mode(runner.OFFLINE_TUNED_MODE)


def test_side_by_side_parser_reads_nested_aggregates(tmp_path):
    module = _load("benchmarks/v2/offline_side_by_side.py", "side_by_side")
    path = tmp_path / "report.json"
    path.write_text(
        '{"aggregate": {"all": {"value_extraction_accuracy": '
        '{"mean": 0.5, "std": 0.1}}}}'
    )
    metrics = module._metrics(path)
    assert metrics["value_extraction_accuracy"] == 0.5
