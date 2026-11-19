"""Unit tests for P5 ablation summary metadata (no network, no model calls)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "benchmarks" / "p5" / "run_ablation.py"
)
_spec = importlib.util.spec_from_file_location("run_ablation", _SCRIPT)
ablation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ablation)


def test_model_from_llm_provider_tag():
    assert (
        ablation._model_from_provider("llm:openai-compatible:mimo-v2.6-flash")
        == "mimo-v2.6-flash"
    )


def test_model_from_deterministic_provider_is_none():
    assert ablation._model_from_provider("deterministic:offline-pattern-extractor") is None
    assert ablation._model_from_provider(None) is None


def test_model_prefers_run_metadata_model():
    report = {
        "run_metadata": {"model": "mimo-v2.6-flash"},
        "raw_outputs": [{"provider": "llm:openai-compatible:other-model"}],
    }
    assert ablation._model_for_report(report) == "mimo-v2.6-flash"


def test_model_falls_back_to_raw_output_provider():
    report = {
        "run_metadata": {"condition": "no_retrieval_memory", "model": None},
        "raw_outputs": [
            {"provider": "llm:openai-compatible:mimo-v2.6-flash"},
            {"provider": "llm:openai-compatible:mimo-v2.6-flash"},
        ],
    }
    assert ablation._model_for_report(report) == "mimo-v2.6-flash"


def test_model_falls_back_through_aggregate_metadata_list():
    report = {
        "run_metadata": [{"condition": "no_retrieval_strict", "model": None}],
        "raw_outputs": [{"provider": "llm:openai-compatible:mimo-v2.6-flash"}],
    }
    assert ablation._model_for_report(report) == "mimo-v2.6-flash"


def test_offline_report_has_no_model():
    report = {
        "run_metadata": {"provider": "deterministic:offline-pattern-extractor"},
        "raw_outputs": [{"provider": "deterministic:offline-pattern-extractor"}],
    }
    assert ablation._model_for_report(report) is None


def test_repair_metadata_backfills_model_from_raw_provider(tmp_path):
    report = {
        "run_metadata": {"condition": "no_retrieval_memory", "model": None},
        "raw_outputs": [{"provider": "llm:openai-compatible:mimo-v2.6-flash"}],
        "per_item": [{"item_id": "x"}],
    }
    (tmp_path / "report_no_retrieval_memory_r0.json").write_text(json.dumps(report))
    aggregate = {
        "condition": "no_retrieval_memory",
        "repeats": 1,
        "aggregate": {"all": {}},
        "run_metadata": [{"condition": "no_retrieval_memory", "model": None}],
    }
    (tmp_path / "aggregate_no_retrieval_memory.json").write_text(json.dumps(aggregate))

    assert ablation._repair_metadata(tmp_path) == 2

    repaired_report = json.loads(
        (tmp_path / "report_no_retrieval_memory_r0.json").read_text()
    )
    assert repaired_report["run_metadata"]["model"] == "mimo-v2.6-flash"
    assert repaired_report["per_item"] == [{"item_id": "x"}]
    repaired_aggregate = json.loads(
        (tmp_path / "aggregate_no_retrieval_memory.json").read_text()
    )
    assert repaired_aggregate["run_metadata"][0]["model"] == "mimo-v2.6-flash"
    assert repaired_aggregate["aggregate"] == {"all": {}}


def test_repair_metadata_leaves_offline_report_untouched(tmp_path):
    report = {
        "run_metadata": {
            "condition": "offline",
            "model": None,
            "provider": "deterministic:offline-pattern-extractor",
        },
        "raw_outputs": [{"provider": "deterministic:offline-pattern-extractor"}],
    }
    path = tmp_path / "report_offline_r0.json"
    path.write_text(json.dumps(report))
    before = path.read_text()

    assert ablation._repair_metadata(tmp_path) == 0
    assert path.read_text() == before
