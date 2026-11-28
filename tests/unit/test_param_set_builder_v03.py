"""Unit tests: deterministic first-party parameter-set builder (v0.3).

The builder must copy values from the committed inputs, never author them, and
must flag every field that has no literature evidence. These tests exercise the
pure build function (no network, no registry writes).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from tests._gate_helpers import binding_for_registry_id

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/v03/build_param_set.py"
CONFIG = ROOT / "configs/v03/param_set.yaml"
ARTIFACT = ROOT / "results/v03/param_set/parallm_chen2020_ext.json"
MANIFEST = ROOT / "results/v03/param_set/manifest.json"

_spec = importlib.util.spec_from_file_location("build_param_set_v03", SCRIPT)
assert _spec and _spec.loader
MOD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MOD)


def _artifact() -> dict:
    return json.loads(ARTIFACT.read_text())


def _config_copy(tmp_path: Path, **changes: object) -> Path:
    cfg = yaml.safe_load(CONFIG.read_text())
    cfg.update(changes)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=True))
    return path


def _input_copy(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path


def test_rebuild_is_byte_deterministic_and_matches_committed_artifact():
    first, first_manifest = MOD.build(CONFIG)
    second, second_manifest = MOD.build(CONFIG)
    assert MOD._canonical_bytes(first) == MOD._canonical_bytes(second)
    assert MOD._canonical_bytes(first_manifest) == MOD._canonical_bytes(second_manifest)
    committed = _artifact()
    # Content is fixed by the inputs; the recorded Python build tool version may
    # legitimately differ across the supported interpreters.
    for key in ("parameters", "counts", "status", "limitations", "content_sha256"):
        assert first[key] == committed[key]
    committed_manifest = json.loads(MANIFEST.read_text())
    for key in committed_manifest:
        if key != "generator":
            assert first_manifest[key] == committed_manifest[key]
    assert {k: v for k, v in first_manifest["generator"].items() if k != "python"} == {
        k: v for k, v in committed_manifest["generator"].items() if k != "python"
    }
    assert first["content_sha256"] == first_manifest["output"]["content_sha256"]


def test_manifest_records_tool_versions_and_input_hashes():
    _, manifest = MOD.build(CONFIG)
    assert manifest["generator"]["pybamm_version"] == "26.8.0.0"
    assert manifest["generator"]["package_version"] == MOD.package_version
    assert manifest["generator"]["python"]
    for key in ("discrepancies", "registry"):
        entry = manifest["inputs"][key]
        assert entry["sha256"] == MOD.sha256_file(ROOT / entry["path"])
    assert manifest["config"]["sha256"] == MOD.sha256_file(CONFIG)
    assert manifest["name_verification"]["all_present"] is True
    assert manifest["name_verification"]["missing"] == []
    assert manifest["name_verification"]["n_requested"] == 27
    assert manifest["value_verification"]["mismatches"] == []


def test_every_field_has_complete_provenance():
    artifact = _artifact()
    assert artifact["counts"]["fields"] == 27
    assert artifact["counts"]["numeric_discrepancy_families"] == 11
    assert artifact["counts"]["set_extension_families"] == 16
    fields = artifact["parameters"]
    assert len(fields) == len({f["canonical_id"] for f in fields})
    for field in fields:
        cid = field["canonical_id"]
        assert field["pybamm_names"], cid
        assert field["operative"]["value"] is not None, cid
        assert field["operative"]["unit"], cid
        prov = field["provenance"]
        assert prov["status"] in {
            "LITERATURE_DERIVED",
            "CALCULATED",
            "CALIBRATED",
            "ASSUMED",
            "UNRESOLVED",
        }, cid
        assert prov["locator"], cid
        source = prov["source"]
        for key in (
            "kind",
            "document_id",
            "locator",
            "quote",
            "char_start",
            "char_end",
            "has_literature_source",
        ):
            assert key in source, (cid, key)
        assert field["approval"]["status"] in {"NOT_RECORDED", "APPROVED", "REJECTED"}


def test_discrepancy_fields_preserve_paper_side_and_conflicts():
    artifact = _artifact()
    discrepancies = json.loads((ROOT / "data/registry/chen2020_discrepancies.json").read_text())
    fields = {f["canonical_id"]: f for f in artifact["parameters"]}
    for item in discrepancies["discrepancies"]:
        field = fields[item["canonical_id"]]
        assert field["family"] == "numeric_discrepancy"
        assert field["operative"]["value"] == item["pybamm"]["value"]
        assert field["provenance"]["source"]["has_literature_source"] is True
        assert field["provenance"]["source"]["document_id"] == item["paper"]["source_document"]
        assert field["paper_evidence"]["source_quote"] == item["paper"]["source_quote"]
        assert field["paper_evidence"]["conditions"] == item["paper"]["conditions"]
        assert field["paper_evidence"]["value"] == item["paper"]["value"]
    n_conflicts = sum(len(f["preserved_conflicts"]) for f in artifact["parameters"])
    assert n_conflicts == 7


def test_set_extensions_are_unsourced_and_values_are_copied():
    artifact = _artifact()
    registry = {
        r["canonical_id"]: r
        for r in json.loads((ROOT / "data/registry/registry.json").read_text())
    }
    set_extensions = json.loads(
        (ROOT / "data/registry/chen2020_discrepancies.json").read_text()
    )["set_extensions"]["families"]
    fields = {f["canonical_id"]: f for f in artifact["parameters"]}
    assert len(set_extensions) == 16
    for item in set_extensions:
        cid = item["canonical_id"]
        field = fields[cid]
        assert field["family"] == "set_extension"
        assert field["provenance"]["status"] in {"ASSUMED", "UNRESOLVED"}
        assert field["operative"]["status"] == registry[cid]["status"]
        assert field["operative"]["value"] == registry[cid]["normalized_value"]
        assert field["operative"]["unit"] == registry[cid]["normalized_value_unit"]
        source = field["provenance"]["source"]
        assert source["has_literature_source"] is False
        assert source["document_id"] == "NOT_RECORDED"
        assert source["doi_or_url"] == "NOT_RECORDED"
        assert source["quote"] == "NOT_RECORDED"
        assert source["char_start"] == "NOT_RECORDED"
        assert source["char_end"] == "NOT_RECORDED"
        assert field["paper_evidence"]["status"] == "NOT_APPLICABLE"


def test_no_gate_means_no_approval_and_no_export():
    artifact = _artifact()
    status = artifact["status"]
    assert status["approval"] == "PENDING_HUMAN_APPROVAL"
    assert status["n_approved_fields"] == 0
    assert status["exportable"] is False
    assert status["pybamm_set_registered"] is False
    for field in artifact["parameters"]:
        assert field["approval"]["status"] == "NOT_RECORDED"


def test_explicit_gate_only_annotates_approval(tmp_path: Path):
    gate = {
        "approvals": [
            {
                "parameter": "contact_resistance",
                "decision": "FIX",
                "approved": True,
                "approver": "owner",
                "rubric_version": "rubric-v2",
                "binding_sha256": binding_for_registry_id("contact_resistance"),
                "timestamp": "2026-11-27T00:00:00+00:00",
                "note": "test fixture",
            }
        ]
    }
    gate_path = _input_copy(tmp_path, "gate.json", gate)
    config = _config_copy(tmp_path, inputs={"discrepancies": "data/registry/chen2020_discrepancies.json",
                                            "registry": "data/registry/registry.json",
                                            "gate": str(gate_path)})
    artifact, manifest = MOD.build(config)
    approved = [f for f in artifact["parameters"] if f["approval"]["status"] == "APPROVED"]
    assert [f["canonical_id"] for f in approved] == ["contact_resistance"]
    assert approved[0]["approval"]["approver"] == "owner"
    assert artifact["status"]["n_approved_fields"] == 1
    assert manifest["inputs"]["gate"]["sha256"] == MOD.sha256_file(gate_path)
    # A gate annotation never makes this builder an exporter or registrar.
    assert artifact["status"]["exportable"] is False
    assert artifact["status"]["pybamm_set_registered"] is False


def test_unknown_pybamm_name_is_refused(tmp_path: Path):
    discrepancies = json.loads((ROOT / "data/registry/chen2020_discrepancies.json").read_text())
    registry = json.loads((ROOT / "data/registry/registry.json").read_text())
    fake = "Invented parameter [m]"
    discrepancies["discrepancies"][0]["pybamm"]["pybamm_names"] = [fake]
    for record in registry:
        if record["canonical_id"] == "neg_particle_diffusivity":
            record["pybamm_names"] = [fake]
    dpath = _input_copy(tmp_path, "discrepancies.json", discrepancies)
    rpath = _input_copy(tmp_path, "registry.json", registry)
    config = _config_copy(tmp_path, inputs={"discrepancies": str(dpath),
                                            "registry": str(rpath), "gate": None})
    with pytest.raises(ValueError, match="PyBaMM name verification FAILED"):
        MOD.build(config)


def test_invented_numeric_value_is_refused(tmp_path: Path):
    discrepancies = json.loads((ROOT / "data/registry/chen2020_discrepancies.json").read_text())
    discrepancies["discrepancies"][0]["pybamm"]["value"] = 1.234e-14
    dpath = _input_copy(tmp_path, "discrepancies.json", discrepancies)
    config = _config_copy(tmp_path, inputs={"discrepancies": str(dpath),
                                            "registry": "data/registry/registry.json",
                                            "gate": None})
    with pytest.raises(ValueError, match="operative value for .* disagrees"):
        MOD.build(config)


def test_builder_never_writes_the_registry(tmp_path: Path):
    source = SCRIPT.read_text()
    assert "RegistryStore" not in source
    assert "pybamm.ParameterValues(" not in source
    assert "add_parameter" not in source


def test_duplicate_json_keys_are_refused(tmp_path: Path):
    path = tmp_path / "dup.json"
    path.write_text('{"a": 1, "a": 2}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        MOD.load_json(path)
