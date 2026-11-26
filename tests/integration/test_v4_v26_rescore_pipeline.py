"""v26 replay/rescore pipeline: no model calls, no private fixture required."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(relative: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synthetic_item() -> dict:
    return {
        "item_id": "V4-TEST1",
        "category": "A",
        "document_id": "synthetic",
        "probe": "1.0",
        "parameter": {
            "name": "synthetic test parameter",
            "value": 1.0,
            "unit": "m2 s-1",
        },
        "gold_conditions": {
            "chemistry": "not_stated",
            "cell": "not_stated",
            "format": "not_stated",
            "temperature_k": "not_stated",
            "soc": "not_stated",
            "method": "not_stated",
            "protocol": "not_stated",
        },
        "not_stated_fields": [
            "chemistry",
            "cell",
            "format",
            "temperature_k",
            "soc",
            "method",
            "protocol",
        ],
        "evidence": {"locator": "synthetic"},
        "notes": "software test only; not a scientific parameter",
    }


def _synthetic_raw() -> dict:
    candidate = {
        "parameter_name": "synthetic test parameter",
        "value": 1.0,
        "unit": "m2 s-1",
        "definition": "Synthetic value used only to test the replay pipeline.",
        "material": "UNRESOLVED",
        "temperature": None,
        "cell_config": "UNRESOLVED",
        "measurement_method": "UNRESOLVED",
        "qualifier": "unknown",
        "context": "No conditions stated in the evidence.",
        "reported_uncertainty": None,
        "source": {
            "document_id": "synthetic",
            "page": None,
            "locator": "UNRESOLVED",
            "quote": "1.0",
        },
    }
    return {
        "item_id": "V4-TEST1",
        "mode": "v25",
        "repeat": 0,
        "raw": json.dumps([candidate]),
        "evidence": "1.0",
        "evidence_source": "oracle",
        "retrieval": None,
    }


def test_v26_rescore_then_aggregate_keeps_suffixed_rows(tmp_path, monkeypatch):
    runner = _load("benchmarks/v2/run_v4_evaluation.py", "v4_runner")
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(_synthetic_item()) + "\n")
    private = tmp_path / "private"
    private.mkdir()
    (private / "raw_v25_r0_v26.jsonl").write_text(
        json.dumps(_synthetic_raw()) + "\n"
    )
    assoc_out = tmp_path / "assoc"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_v4_evaluation.py",
            "--rescore",
            "--modes",
            "v25",
            "--repeats",
            "1",
            "--items",
            str(items_path),
            "--prompt-version",
            "v26",
            "--discipline",
            "association",
            "--out",
            str(assoc_out),
            "--private-out",
            str(private),
        ],
    )
    assert runner.main() == 0
    assert (private / "rows_v25_r0_v26.json").exists()
    assert "prompt: `v26`" in (assoc_out / "summary.md").read_text()

    agg_out = tmp_path / "agg"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_v4_evaluation.py",
            "--aggregate-only",
            "--modes",
            "v25",
            "--repeats",
            "1",
            "--items",
            str(items_path),
            "--prompt-version",
            "v26",
            "--out",
            str(agg_out),
            "--private-out",
            str(private),
        ],
    )
    assert runner.main() == 0
    assert "| condition_field_accuracy | 1.000 +/- 0.000 |" in (
        agg_out / "summary.md"
    ).read_text()
