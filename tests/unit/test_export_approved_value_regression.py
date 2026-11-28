"""Step 1 regressions: export only the approved value, never a registry value.

Only clearly labelled synthetic registry copies and gate files are used. No
data/ or results/ file is edited; no live model calls.
"""

from __future__ import annotations

import json
from pathlib import Path

from pybamm_closed_loop.assembly.gate import binding_sha256
from pybamm_closed_loop.cli import main

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data" / "registry" / "registry.json"
TARGET = ROOT / "configs" / "v2" / "target_lgm50.yaml"


def _config(tmp_path: Path) -> list[str]:
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path: Path) -> None:
    assert main([*_config(tmp_path), "init", "--workspace",
                 str(tmp_path / "ws"), "--non-interactive"]) == 0


def _registry_with_conflict(tmp_path: Path) -> Path:
    records = json.loads(REGISTRY.read_text(encoding="utf-8"))
    record = next(r for r in records if r["canonical_id"] == "cell_electrode_width")
    record["value"] = 9.99
    record["normalized_value"] = 9.99
    record["conditions"] = {}
    record["evidence"] = {}
    record["conflicts"] = [{
        "value": 1.58, "unit": "m", "normalized_value": 1.58,
        "normalized_value_unit": "m", "kind": "LITERATURE_DERIVED",
        "method": "measured with a Vernier caliper at teardown",
        "conditions": {"cell": "LG M50 21700", "temperature_k": 298.15},
        "source": {
            "document_id": "chen2020_jes_167_080534", "locator": "Table VII",
            "quote": "The electrode width is 1.58 m measured by Vernier caliper.",
            "doi_or_url": "10.1149/1945-7111/ab9050",
        },
    }]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def _approved_assembly(tmp_path: Path, registry: Path) -> Path:
    first = tmp_path / "assembly_first"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(registry), "--out", str(first)]) == 0
    report = json.loads((first / "report.json").read_text(encoding="utf-8"))
    dossier = next(d for d in report["parameters"]
                   if d["parameter"] == "cell_electrode_width")
    assert dossier["selected"]["value"] == 1.58
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"approvals": [{
        "parameter": "cell_electrode_width", "decision": dossier["decision"],
        "approved": True, "approver": "SYNTHETIC", "timestamp": "2026-11-28T00:00:00Z",
        "rubric_version": dossier["rubric_version"],
        "binding_sha256": binding_sha256(dossier),
    }]}))
    final = tmp_path / "assembly_final"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(registry), "--out", str(final),
                 "--gate", str(gate)]) == 0
    return final


def test_conflict_selected_exports_approved_value(tmp_path):
    """A conflict-selected approved value must not be replaced by the main value."""
    _init(tmp_path)
    registry = _registry_with_conflict(tmp_path)
    final = _approved_assembly(tmp_path, registry)
    assert json.loads((final / "pybamm_export.json").read_text()) == {
        "cell_electrode_width": 1.58
    }
    out = tmp_path / "params.py"
    assert main([*_config(tmp_path), "--quiet", "export", "--format", "pybamm",
                 "--from", str(final), "--output", str(out)]) == 0
    assert out.read_text(encoding="utf-8").strip() == (
        "PARAMETERS = {'Electrode width [m]': 1.58}"
    )


def test_hand_written_input_not_replaced_by_registry_value(tmp_path):
    """A direct value is never substituted with a registry value."""
    _init(tmp_path)
    source = tmp_path / "assembly"
    source.mkdir()
    (source / "pybamm_export.json").write_text(
        json.dumps({"cell_electrode_width": 999.0}), encoding="utf-8"
    )
    out = tmp_path / "params.py"
    assert main([*_config(tmp_path), "--quiet", "export", "--format", "pybamm",
                 "--from", str(source), "--output", str(out),
                 "--registry", str(REGISTRY)]) == 0
    assert out.read_text(encoding="utf-8").strip() == (
        "PARAMETERS = {'Electrode width [m]': 999.0}"
    )


def test_json_export_keeps_original_unit_and_value(tmp_path):
    """JSON export reports the exported value's own unit, not a registry unit."""
    _init(tmp_path)
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"neg_particle_radius": {
        "value": 5.86e-06, "unit": "m", "pybamm_names": ["Negative particle radius [m]"],
    }}), encoding="utf-8")
    for schema in (1, 2):
        out = tmp_path / f"out{schema}.json"
        assert main([*_config(tmp_path), "--quiet", "export", "--format", "json",
                     "--from", str(source), "--output", str(out),
                     "--schema-version", str(schema)]) == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        entry = payload["parameters"]["neg_particle_radius"]
        assert entry["value"] == 5.86e-06
        assert entry["unit"] == "m"
        if schema == 2:
            assert entry.get("original", {}).get("value") == 5.86e-06
            assert entry.get("original", {}).get("unit") == "m"


def test_reexport_does_not_convert_twice(tmp_path):
    """Re-exporting an artifact keeps the same value and unit."""
    _init(tmp_path)
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"neg_particle_radius": {
        "value": 5.86e-06, "unit": "m", "pybamm_names": ["Negative particle radius [m]"],
    }}), encoding="utf-8")
    first = tmp_path / "first.json"
    assert main([*_config(tmp_path), "--quiet", "export", "--format", "json",
                 "--from", str(source), "--output", str(first),
                 "--schema-version", "2"]) == 0
    second = tmp_path / "second.json"
    assert main([*_config(tmp_path), "--quiet", "export", "--format", "json",
                 "--from", str(first), "--output", str(second),
                 "--schema-version", "2"]) == 0
    entry = json.loads(second.read_text(encoding="utf-8"))["parameters"]["neg_particle_radius"]
    assert entry["value"] == 5.86e-06
    assert entry["unit"] == "m"
