"""Regression tests for the approved JSON export trust model and schema v2."""

from __future__ import annotations

import json
from pathlib import Path

from pybamm_closed_loop.cli import main

from tests._gate_helpers import (
    binding_for_record, binding_for_registry_id, decision_for_registry_id,
)
from pybamm_closed_loop.assembly import (
    Rubric, TargetSpecification, assemble,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data" / "registry" / "registry.json"
TARGET = ROOT / "configs" / "v2" / "target_lgm50.yaml"
DOCS = ROOT / "data" / "raw_documents"
FIXTURE = ROOT / "examples" / "candidate_archived.json"


def _config(tmp_path: Path) -> list[str]:
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path: Path) -> None:
    assert main([*_config(tmp_path), "init",
                 "--workspace", str(tmp_path / "workspace"), "--non-interactive"]) == 0


def _record(
    name: str,
    *,
    validation_state: str = "ACCEPTED",
    status: str = "LITERATURE_DERIVED",
    pybamm_names: list[str] | None = None,
    value: float = 298.15,
    unit: str = "K",
    quote: str | None = "measured at 25 C",
) -> dict:
    return {
        "canonical_id": name,
        "pybamm_names": pybamm_names if pybamm_names is not None else ["Ambient temperature [K]"],
        "pybop_mapping": None,
        "definition": f"test record {name}",
        "value": value,
        "value_unit": unit,
        "normalized_value": value,
        "normalized_value_unit": unit,
        "status": status,
        "source_id": "10.1149/test",
        "source_location": "Table I",
        "evidence": {
            "value": value, "unit": unit,
            "source": {"document_id": "paper", "locator": "Table I", "page": 3,
                       "quote": quote, "doi_or_url": "10.1149/test"},
            "kind": status, "reported_uncertainty": None, "uncertainty_note": None,
            "conditions": {"cell": "LG M50"}, "method": "measurement",
            "context": None, "review_state": "ACCEPTED", "review_reason": None,
        },
        "conditions": {"cell": "LG M50"},
        "method": "measurement",
        "reported_uncertainty": None,
        "validation_state": validation_state,
        "compatibility": {}, "conflicts": [], "notes": [],
    }


def _gate(path: Path, names: list[str], *, approved: bool = True,
          registry: Path | None = None) -> Path:
    records = json.loads((registry or REGISTRY).read_text())
    by_id = {r["canonical_id"]: r for r in records}
    if registry is not None:
        target = TargetSpecification(
            target_id="lgm50_chen2020_dfn", cell_product="LG M50",
            chemistry_families=("NMC", "graphite"), format="21700",
            temperature_k=298.15, soc="50%",
        )
        report = assemble(records, target, Rubric("rubric-v2"))
        decisions = {d["parameter"]: d["decision"] for d in report.dossiers}
    else:
        decisions = {}
    payload = {"approvals": [
        {"parameter": name, "decision": decisions.get(name, decision_for_registry_id(name)),
         "approved": approved,
         "approver": "owner", "rubric_version": "rubric-v2", "timestamp": "2026-11-23T00:00:00Z",
         "binding_sha256": (binding_for_record(by_id[name])
                            if name in by_id else binding_for_registry_id(name))}
        for name in names
    ]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _assemble(tmp_path: Path, out: str, *, registry: Path, gate: Path | None,
              documents: bool = False) -> Path:
    args = [*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
            "--registry", str(registry), "--out", str(tmp_path / out)]
    if gate is not None:
        args += ["--gate", str(gate)]
    if documents:
        args += ["--documents", str(DOCS)]
    assert main(args) == 0
    return tmp_path / out


def _export(tmp_path: Path, src: Path, output: Path, *extra: str) -> int:
    return main([*_config(tmp_path), "--json", "export", "--from", str(src),
                 "--output", str(output), "--schema-version", "2", *extra])


def _envelope(capsys) -> dict:
    output = capsys.readouterr().out
    return json.loads(output[output.index("{"):])


def _artifact(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- Phase 1: attestation -------------------------------------------------
def test_valid_assembly_attestation(tmp_path, capsys):
    _init(tmp_path)
    gate = _gate(tmp_path / "gate.json", ["ambient_temperature"])
    source = _assemble(tmp_path, "assembly", registry=REGISTRY, gate=gate, documents=True)
    assert _export(tmp_path, source, tmp_path / "out.json") == 0
    envelope = _envelope(capsys)
    assert envelope["data"]["attestation"]["level"] == "ATTESTED"
    assert envelope["data"]["export_status"] == "COMPLETE"
    artifact = _artifact(tmp_path / "out.json")
    entry = artifact["parameters"]["ambient_temperature"]
    assert entry["source"]["document_id"] == "chen2020_jes_167_080534"
    assert entry["source"]["quote"]
    assert entry["validation"]["state"] in ("ACCEPTED", "NEEDS_REVIEW")
    assert entry["approval"]["status"] == "APPROVED"
    assert artifact["approved_only"] is True
    assert (source / "manifest.json").exists()
    manifest = _artifact(source / "manifest.json")
    assert "pybamm_export.json" in manifest["outputs_sha256"]


def test_modified_gate_file_fails_closed(tmp_path, capsys):
    _init(tmp_path)
    gate = _gate(tmp_path / "gate.json", ["ambient_temperature"])
    source = _assemble(tmp_path, "assembly", registry=REGISTRY, gate=gate)
    gate.write_text(json.dumps({"approvals": []}), encoding="utf-8")
    assert _export(tmp_path, source, tmp_path / "out.json") == 2
    assert _envelope(capsys)["diagnostics"][0]["code"] == "E404"
    assert not (tmp_path / "out.json").exists()


def test_modified_registry_fails_closed(tmp_path, capsys):
    _init(tmp_path)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([_record("ambient_temperature")]), encoding="utf-8")
    gate = _gate(tmp_path / "gate.json", ["ambient_temperature"])
    source = _assemble(tmp_path, "assembly", registry=registry, gate=gate)
    records = json.loads(registry.read_text(encoding="utf-8"))
    records[0]["value"] = 999.0
    registry.write_text(json.dumps(records), encoding="utf-8")
    assert _export(tmp_path, source, tmp_path / "out.json") == 2
    assert _envelope(capsys)["diagnostics"][0]["code"] == "E404"
    assert not (tmp_path / "out.json").exists()


def test_modified_assembly_export_fails_closed(tmp_path, capsys):
    _init(tmp_path)
    gate = _gate(tmp_path / "gate.json", ["ambient_temperature"])
    source = _assemble(tmp_path, "assembly", registry=REGISTRY, gate=gate)
    (source / "pybamm_export.json").write_text(
        json.dumps({"ambient_temperature": 999.0}), encoding="utf-8"
    )
    assert _export(tmp_path, source, tmp_path / "out.json") == 2
    assert _envelope(capsys)["diagnostics"][0]["code"] == "E404"
    assert not (tmp_path / "out.json").exists()


def test_missing_manifest_is_unverified(tmp_path, capsys):
    _init(tmp_path)
    source = tmp_path / "assembly"
    source.mkdir()
    (source / "pybamm_export.json").write_text(
        json.dumps({"ambient_temperature": 298.15}), encoding="utf-8"
    )
    assert _export(tmp_path, source, tmp_path / "out.json") == 0
    artifact = _artifact(tmp_path / "out.json")
    assert artifact["artifact"]["attestation"]["level"] == "UNVERIFIED"
    assert artifact["approved_only"] is False
    assert "UNVERIFIED" in _envelope(capsys)["data"]["warnings"][0]


def test_forged_approval_claim_is_never_trusted(tmp_path, capsys):
    _init(tmp_path)
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps({
        "schema_version": 2,
        "artifact": {"attestation": {"level": "ATTESTED"}},
        "parameters": {"fake_parameter": 1.234},
        "approved_only": True,
    }), encoding="utf-8")
    assert _export(tmp_path, forged, tmp_path / "out.json") == 0
    artifact = _artifact(tmp_path / "out.json")
    assert artifact["artifact"]["attestation"]["level"] == "UNVERIFIED"
    assert artifact["approved_only"] is False
    assert "approved_only" in artifact["artifact"]["reported_claims"]
    assert artifact["parameters"]["fake_parameter"]["value"] == 1.234


def test_attested_empty_export(tmp_path, capsys):
    _init(tmp_path)
    source = _assemble(tmp_path, "assembly", registry=REGISTRY, gate=None)
    assert _export(tmp_path, source, tmp_path / "out.json") == 0
    envelope = _envelope(capsys)
    assert envelope["data"]["attestation"]["level"] == "ATTESTED_EMPTY"
    assert envelope["data"]["export_status"] == "INTENTIONALLY_EMPTY"
    artifact = _artifact(tmp_path / "out.json")
    assert artifact["export"]["status"] == "INTENTIONALLY_EMPTY"
    assert artifact["export"]["n_exported"] == 0
    assert artifact["approved_only"] is False


# --- Phase 3: validation / approval policy --------------------------------
def test_rejected_validation_never_exported(tmp_path, capsys):
    _init(tmp_path)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([_record("ambient_temperature", validation_state="REJECTED")]),
                        encoding="utf-8")
    gate = _gate(tmp_path / "gate.json", ["ambient_temperature"], registry=registry)
    source = _assemble(tmp_path, "assembly", registry=registry, gate=gate)
    assert _export(tmp_path, source, tmp_path / "out.json") == 2
    diagnostic = _envelope(capsys)["diagnostics"][0]
    assert "VALIDATION_REJECTED" in str(diagnostic["why"])
    assert not (tmp_path / "out.json").exists()


def test_needs_review_with_approval_is_flagged(tmp_path, capsys):
    _init(tmp_path)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([_record("ambient_temperature", validation_state="NEEDS_REVIEW")]),
                        encoding="utf-8")
    gate = _gate(tmp_path / "gate.json", ["ambient_temperature"], registry=registry)
    source = _assemble(tmp_path, "assembly", registry=registry, gate=gate)
    assert _export(tmp_path, source, tmp_path / "out.json") == 0
    artifact = _artifact(tmp_path / "out.json")
    entry = artifact["parameters"]["ambient_temperature"]
    assert entry["validation"]["state"] == "NEEDS_REVIEW"
    assert entry["validation"]["disposition"] == "approved_with_pending_validation"
    assert any("NEEDS_REVIEW" in w for w in artifact["export"]["warnings"])


def test_needs_review_without_approval_is_not_exported(tmp_path, capsys):
    _init(tmp_path)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([_record("ambient_temperature", validation_state="NEEDS_REVIEW")]),
                        encoding="utf-8")
    gate = _gate(tmp_path / "gate.json", [], approved=False)
    assert main([*_config(tmp_path), "--json", "export", "--from", str(registry),
                 "--output", str(tmp_path / "out.json"), "--schema-version", "2",
                 "--gate", str(gate)]) == 2
    assert "NEEDS_APPROVAL" in str(_envelope(capsys)["diagnostics"][0]["why"])


def test_unknown_validation_state_is_never_promoted(tmp_path, capsys):
    _init(tmp_path)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([_record("ambient_temperature", validation_state="BOGUS")]),
                        encoding="utf-8")
    gate = _gate(tmp_path / "gate.json", ["ambient_temperature"])
    assert main([*_config(tmp_path), "--json", "export", "--from", str(registry),
                 "--output", str(tmp_path / "out.json"), "--schema-version", "2",
                 "--gate", str(gate)]) == 2
    assert "VALIDATION_UNKNOWN" in str(_envelope(capsys)["diagnostics"][0]["why"])


def test_missing_provenance_uses_explicit_sentinels(tmp_path, capsys):
    _init(tmp_path)
    direct = tmp_path / "direct.json"
    direct.write_text(json.dumps({"p": 1.23}), encoding="utf-8")
    assert _export(tmp_path, direct, tmp_path / "out.json") == 0
    entry = _artifact(tmp_path / "out.json")["parameters"]["p"]
    assert entry["source"]["document_id"] == "NOT_RECORDED"
    assert entry["validation"]["state"] == "NOT_RECORDED"
    assert entry["validation"]["results"] == "NOT_PERFORMED"
    assert entry["approval"]["status"] == "NOT_RECORDED"
    assert entry["calibration"]["status"] == "NOT CALIBRATED"
    assert entry["source"]["page"] == "NOT_APPLICABLE"


# --- Phase 2: reading, migration and empty semantics ----------------------
def test_nested_parameter_re_export_preserves_entry(tmp_path, capsys):
    _init(tmp_path)
    nested = tmp_path / "nested.json"
    nested.write_text(json.dumps({
        "parameters": {"ambient_temperature": {"value": 298.15, "unit": "K"}}
    }), encoding="utf-8")
    assert _export(tmp_path, nested, tmp_path / "out.json") == 0
    artifact = _artifact(tmp_path / "out.json")
    assert artifact["parameters"]["ambient_temperature"]["value"] == 298.15
    assert artifact["parameters"]["ambient_temperature"]["unit"] == "K"
    assert artifact["export"]["n_exported"] == 1


def test_v1_to_v2_migration_marks_unverified(tmp_path, capsys):
    _init(tmp_path)
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"p": 1.23}), encoding="utf-8")
    assert main([*_config(tmp_path), "--json", "export", "--from", str(legacy),
                 "--output", str(tmp_path / "v1.json")]) == 0
    capsys.readouterr()
    assert main([*_config(tmp_path), "--json", "export", "--from", str(tmp_path / "v1.json"),
                 "--output", str(tmp_path / "v2.json"), "--schema-version", "2"]) == 0
    capsys.readouterr()
    artifact = _artifact(tmp_path / "v2.json")
    assert artifact["artifact"]["migrated_from"] == 1
    assert artifact["artifact"]["attestation"]["level"] == "UNVERIFIED"
    assert artifact["parameters"]["p"]["value"] == 1.23


def test_v1_remains_default(tmp_path, capsys):
    _init(tmp_path)
    direct = tmp_path / "direct.json"
    direct.write_text(json.dumps({"p": 1.23}), encoding="utf-8")
    assert main([*_config(tmp_path), "--json", "export", "--from", str(direct),
                 "--output", str(tmp_path / "v1.json")]) == 0
    artifact = _artifact(tmp_path / "v1.json")
    assert artifact["schema_version"] == 1
    assert "artifact" not in artifact
    assert set(artifact["parameters"]["p"]) == {"value", "unit", "pybamm_names"}


def test_unsupported_schema_version_rejected(tmp_path, capsys):
    _init(tmp_path)
    future = tmp_path / "future.json"
    future.write_text(json.dumps({"schema_version": 99, "parameters": {}}), encoding="utf-8")
    assert _export(tmp_path, future, tmp_path / "out.json") == 2
    assert "Unsupported export schema version" in str(_envelope(capsys)["diagnostics"][0]["what"])
    assert not (tmp_path / "out.json").exists()


def test_partial_export(tmp_path, capsys):
    _init(tmp_path)
    source = tmp_path / "assembly"
    source.mkdir()
    (source / "pybamm_export.json").write_text(
        json.dumps({"ambient_temperature": 298.15, "unmapped": "<function unsupported>"}),
        encoding="utf-8"
    )
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([_record("ambient_temperature")]), encoding="utf-8")
    (source / "manifest.json").write_text(
        json.dumps({"registry": {"path": str(registry)}}), encoding="utf-8"
    )
    assert _export(tmp_path, source, tmp_path / "out.json") == 0
    artifact = _artifact(tmp_path / "out.json")
    assert artifact["export"]["status"] == "PARTIAL"
    assert artifact["export"]["n_exported"] == 1
    assert artifact["export"]["n_skipped"] == 1


def test_empty_after_filtering_fails(tmp_path, capsys):
    _init(tmp_path)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([_record("ambient_temperature", validation_state="REJECTED")]),
                        encoding="utf-8")
    gate = _gate(tmp_path / "gate.json", ["ambient_temperature"], registry=registry)
    source = _assemble(tmp_path, "assembly", registry=registry, gate=gate)
    assert _export(tmp_path, source, tmp_path / "out.json") == 2
    assert _envelope(capsys)["diagnostics"][0]["code"] == "E404"
    assert not (tmp_path / "out.json").exists()


def test_overwrite_protection_preserved(tmp_path, capsys):
    _init(tmp_path)
    direct = tmp_path / "direct.json"
    direct.write_text(json.dumps({"p": 1.23}), encoding="utf-8")
    output = tmp_path / "out.json"
    assert _export(tmp_path, direct, output) == 0
    capsys.readouterr()
    assert _export(tmp_path, direct, output) == 2
    assert _envelope(capsys)["diagnostics"][0]["code"] == "E403"


# --- Phase 4: PyBaMM compatibility and regression guards -----------------
def test_pybamm_overlay_unchanged(tmp_path, capsys):
    _init(tmp_path)
    gate = _gate(tmp_path / "gate.json", ["ambient_temperature"])
    source = _assemble(tmp_path, "assembly", registry=REGISTRY, gate=gate)
    output = tmp_path / "parameters.py"
    assert main([*_config(tmp_path), "--json", "export", "--format", "pybamm",
                 "--from", str(source), "--output", str(output)]) == 0
    text = output.read_text(encoding="utf-8")
    assert text.startswith("PARAMETERS = {")
    assert "Ambient temperature [K]" in text
    for forbidden in ("provenance", "validation", "approval", "artifact"):
        assert forbidden not in text


def test_round_trip_preserves_values_and_metadata(tmp_path, capsys):
    _init(tmp_path)
    gate = _gate(tmp_path / "gate.json", ["ambient_temperature"])
    source = _assemble(tmp_path, "assembly", registry=REGISTRY, gate=gate, documents=True)
    first = tmp_path / "first.json"
    assert _export(tmp_path, source, first) == 0
    capsys.readouterr()
    second = tmp_path / "second.json"
    assert _export(tmp_path, first, second) == 0
    capsys.readouterr()
    original = _artifact(first)["parameters"]["ambient_temperature"]
    round_tripped = _artifact(second)["parameters"]["ambient_temperature"]
    assert round_tripped["value"] == original["value"]
    assert round_tripped["unit"] == original["unit"]
    assert round_tripped["source"] == original["source"]
    assert round_tripped["validation"] == original["validation"]
    assert round_tripped["approval"] == original["approval"]
    assert "verified_on_export" not in round_tripped["approval"]
    result = _artifact(second)
    assert result["artifact"]["attestation"]["level"] == "ATTESTED"
    assert "attestation re-verified on re-export" in result["artifact"]["attestation"]["notes"]


def test_archived_fixture_failure_preserved(capsys):
    assert main(["--json", "validate", str(FIXTURE)]) == 1
    payload = _envelope(capsys)
    checks = {c["name"]: c["level"] for c in payload["data"]["results"][0]["checks"]}
    assert checks["physical_plausibility"] == "FAILED"
