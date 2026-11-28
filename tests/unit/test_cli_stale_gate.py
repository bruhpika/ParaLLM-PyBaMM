"""PHASE 1: the CLI export path must reject a stale gate end-to-end."""

from __future__ import annotations

import json
from pathlib import Path

from pybamm_closed_loop.cli import main

from tests._gate_helpers import binding_for_record, decision_for_registry_id

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "configs/v2/target_lgm50.yaml"


def _config(tmp_path):
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path):
    assert main([*_config(tmp_path), "init", "--workspace", str(tmp_path / "ws"),
                 "--non-interactive"]) == 0


def _record(value=5.86e-6):
    return {
        "canonical_id": "neg_particle_radius", "value": value,
        "value_unit": "m", "normalized_value": value, "normalized_value_unit": "m",
        "status": "LITERATURE_DERIVED", "method": "SEM measurement",
        "source_id": "doc",
        "evidence": {"source": {"document_id": "doc", "locator": "Table II",
                                "quote": "the mean particle radius is 5.86 um by SEM"}},
        "conditions": {"cell": "LG M50"}, "conflicts": [],
        "pybamm_names": ["Negative particle radius [m]"],
    }


def _gate(tmp_path, record):
    path = tmp_path / "gate.json"
    path.write_text(json.dumps({"approvals": [{
        "parameter": "neg_particle_radius",
        "decision": decision_for_registry_id("neg_particle_radius"),
        "approved": True, "approver": "owner", "rubric_version": "rubric-v2",
        "binding_sha256": binding_for_record(record),
    }]}), encoding="utf-8")
    return path


def test_stale_gate_blocks_cli_export(tmp_path, capsys):
    _init(tmp_path)
    original = _record()
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([original]), encoding="utf-8")
    gate = _gate(tmp_path, original)
    out = tmp_path / "assembly"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(registry), "--gate", str(gate), "--out", str(out)]) == 0
    assert json.loads((out / "pybamm_export.json").read_text()) == {
        "neg_particle_radius": 5.86e-6
    }

    # Change the value in the registry; the old gate is now stale.
    changed = _record(value=999.0)
    registry.write_text(json.dumps([changed]), encoding="utf-8")
    out2 = tmp_path / "assembly2"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(registry), "--gate", str(gate), "--out", str(out2)]) == 0
    assert json.loads((out2 / "pybamm_export.json").read_text()) == {}
