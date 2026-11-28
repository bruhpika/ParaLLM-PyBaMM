"""Regression tests for the adversarial trust-audit remediation (H1-H3, M1-M6)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from pybamm_closed_loop.cli import main
from pybamm_closed_loop.cli_app.artifact import normalise_validation_state

from tests._gate_helpers import binding_for_registry_id, decision_for_registry_id

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data" / "registry" / "registry.json"
TARGET = ROOT / "configs" / "v2" / "target_lgm50.yaml"
FIXTURE = ROOT / "examples" / "candidate_archived.json"

H1 = "H1 validation-state normalisation"
H2 = "H2 contradictory gate rejection"
H3 = "H3 v2 attestation re-verification"
M1 = "M1 empty export semantics"
M2 = "M2 non-finite / boolean values"
M3 = "M3 duplicate parameter ids"
M4 = "M4 PyBaMM registry-list source"
M5 = "M5 malformed gate errors"


def _config(tmp_path: Path) -> list[str]:
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path: Path) -> None:
    assert main([*_config(tmp_path), "init", "--workspace", str(tmp_path / "ws"),
                 "--non-interactive"]) == 0


def _approval(name: str = "ambient_temperature", approved: bool = True) -> dict:
    return {"parameter": name, "decision": decision_for_registry_id(name), "approved": approved,
            "approver": "owner", "rubric_version": "rubric-v2",
            "binding_sha256": binding_for_registry_id(name)}


def _gate(path: Path, *records: dict) -> Path:
    path.write_text(json.dumps({"approvals": list(records)}), encoding="utf-8")
    return path


def _assemble(tmp_path: Path, out: str, *, registry: Path = REGISTRY, gate: Path | None) -> Path:
    args = [*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
            "--registry", str(registry), "--out", str(tmp_path / out)]
    if gate is not None:
        args += ["--gate", str(gate)]
    assert main(args) == 0
    return tmp_path / out


def _envelope(capsys) -> dict:
    output = capsys.readouterr().out
    return json.loads(output[output.index("{"):])


def _export_json(src: Path, output: Path, *extra: str, fmt: str = "json") -> int:
    return main(["--json", "export", "--from", str(src), "--output", str(output),
                 "--overwrite", "--format", fmt, "--schema-version", "2", *extra])


def _artifact(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _v2_payload(parameters: dict, **attestation) -> dict:
    return {"schema_version": 2, "artifact": {"attestation": attestation},
            "parameters": parameters}


# --- H1 -------------------------------------------------------------------
@pytest.mark.parametrize("state", ["BOGUS", 1, ["ACCEPTED"], {"state": "ACCEPTED"}])
def test_h1_unknown_or_invalid_v2_state_fails_closed(tmp_path, capsys, state):
    _init(tmp_path)
    source = tmp_path / "input.json"
    source.write_text(json.dumps(_v2_payload({"p": {"value": 1.0, "validation": {"state": state}}})),
                      encoding="utf-8")
    assert _export_json(source, tmp_path / "out.json") == 2
    assert "VALIDATION_UNKNOWN" in str(_envelope(capsys)["diagnostics"][0]["why"])


@pytest.mark.parametrize("payload,expected", [
    (None, "NOT_RECORDED"),
    ("NOT_PERFORMED", "NOT_PERFORMED"),
    ("NOT_APPLICABLE", "NOT_APPLICABLE"),
    ("ACCEPTED", "ACCEPTED"),
    ("NEEDS_REVIEW", "NEEDS_REVIEW"),
    ("REJECTED", "REJECTED"),
    ("UNKNOWN", "UNKNOWN"),
    ("bogus", "UNKNOWN"),
    (True, "UNKNOWN"),
])
def test_h1_normaliser_semantics(payload, expected):
    assert normalise_validation_state(payload) == expected


def test_h1_null_and_missing_state_are_not_accepted(tmp_path, capsys):
    _init(tmp_path)
    null_state = _v2_payload({"p": {"value": 1.0, "validation": {"state": None}}})
    missing_state = _v2_payload({"p": {"value": 1.0, "validation": {}}})
    for index, payload in enumerate((null_state, missing_state)):
        source = tmp_path / f"input{index}.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        assert _export_json(source, tmp_path / f"out{index}.json") == 0
        entry = _artifact(tmp_path / f"out{index}.json")["parameters"]["p"]
        assert entry["validation"]["state"] == "NOT_RECORDED"
        assert any("NOT_RECORDED" in item for item in _artifact(tmp_path / f"out{index}.json")["export"]["limitations"])


def test_h1_unknown_state_from_registry_fails_closed(tmp_path, capsys):
    _init(tmp_path)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([{
        "canonical_id": "p", "value": 1.0, "value_unit": "K", "pybamm_names": [],
        "validation_state": "SOMETHING_ELSE",
    }]), encoding="utf-8")
    gate = _gate(tmp_path / "gate.json", _approval("p"))
    assert _export_json(registry, tmp_path / "out.json", "--gate", str(gate)) == 2
    assert "VALIDATION_UNKNOWN" in str(_envelope(capsys)["diagnostics"][0]["why"])


def test_h1_unknown_state_from_nested_metadata_fails_closed(tmp_path, capsys):
    _init(tmp_path)
    source = tmp_path / "nested.json"
    source.write_text(json.dumps({"parameters": {
        "p": {"value": 1.0, "validation": {"state": "BOGUS"}}
    }}), encoding="utf-8")
    assert _export_json(source, tmp_path / "out.json") == 2
    assert "VALIDATION_UNKNOWN" in str(_envelope(capsys)["diagnostics"][0]["why"])


def test_h1_unknown_state_during_v2_reexport(tmp_path, capsys):
    _init(tmp_path)
    first = tmp_path / "first.json"
    first.write_text(json.dumps(_v2_payload({"p": {"value": 1.0}})), encoding="utf-8")
    assert _export_json(first, tmp_path / "base.json") == 0
    capsys.readouterr()
    v2 = _artifact(tmp_path / "base.json")
    v2["parameters"]["p"]["validation"] = {"state": "BOGUS"}
    v2["artifact"]["attestation"]["derived_content_sha256"] = "0000"
    modified = tmp_path / "modified.json"
    modified.write_text(json.dumps(v2), encoding="utf-8")
    assert _export_json(modified, tmp_path / "out.json") == 2
    assert "VALIDATION_UNKNOWN" in str(_envelope(capsys)["diagnostics"][0]["why"])


# --- H2 -------------------------------------------------------------------
@pytest.mark.parametrize("records", [
    (_approval(approved=False), _approval(approved=True)),
    (_approval(approved=True), _approval(approved=False)),
    (_approval(), _approval()),
    (_approval(approved=False), _approval(approved=False)),
])
def test_h2_duplicate_or_contradictory_gate_rejected(tmp_path, capsys, records):
    _init(tmp_path)
    gate = _gate(tmp_path / "gate.json", *records)
    source = tmp_path / "registry.json"
    source.write_text(json.dumps([{"canonical_id": "ambient_temperature", "value": 298.15,
                                   "value_unit": "K", "pybamm_names": [],
                                   "validation_state": "ACCEPTED"}]), encoding="utf-8")
    assert _export_json(source, tmp_path / "out.json", "--gate", str(gate)) == 2
    assert _envelope(capsys)["diagnostics"][0]["code"] == "E201"


def test_h2_gate_order_does_not_change_result(tmp_path, capsys):
    _init(tmp_path)
    outcomes = []
    for index, records in enumerate((
        (_approval(approved=False), _approval(approved=True)),
        (_approval(approved=True), _approval(approved=False)),
    )):
        gate = _gate(tmp_path / f"gate{index}.json", *records)
        outcomes.append(_export_json(REGISTRY, tmp_path / f"out{index}.json", "--gate", str(gate)))
    assert outcomes == [2, 2]


def test_h2_contradictory_gate_rejected_by_assembly(tmp_path, capsys):
    _init(tmp_path)
    gate = _gate(tmp_path / "gate.json", _approval(approved=False), _approval(approved=True))
    assert main([*_config(tmp_path), "--json", "assemble", "--target", str(TARGET),
                 "--registry", str(REGISTRY), "--out", str(tmp_path / "assembly"),
                 "--gate", str(gate)]) == 2
    assert _envelope(capsys)["diagnostics"][0]["code"] == "E201"


def test_h2_duplicate_canonical_id_with_representation(tmp_path, capsys):
    _init(tmp_path)
    gate = _gate(tmp_path / "gate.json",
                 _approval("ambient_temperature"), _approval(" ambient_temperature "))
    assert _export_json(REGISTRY, tmp_path / "out.json", "--gate", str(gate)) == 2
    assert "duplicate approval" in str(_envelope(capsys)["diagnostics"][0]["why"])


# --- H3 -------------------------------------------------------------------
def _attested_source(tmp_path: Path) -> tuple[Path, Path]:
    gate = _gate(tmp_path / "gate.json", _approval())
    source = _assemble(tmp_path, "assembly", gate=gate)
    first = tmp_path / "first.json"
    assert _export_json(source, first) == 0
    return source, first


def test_h3_valid_attested_reexport_preserves_trust(tmp_path, capsys):
    _init(tmp_path)
    _, first = _attested_source(tmp_path)
    capsys.readouterr()
    assert _export_json(first, tmp_path / "second.json") == 0
    result = _artifact(tmp_path / "second.json")
    assert result["artifact"]["attestation"]["level"] == "ATTESTED"
    assert "attestation re-verified on re-export" in result["artifact"]["attestation"]["notes"]


def test_h3_attested_empty_reexport_preserves_empty_trust(tmp_path, capsys):
    _init(tmp_path)
    source = _assemble(tmp_path, "assembly", gate=None)
    first = tmp_path / "first.json"
    assert _export_json(source, first) == 0
    capsys.readouterr()
    assert _export_json(first, tmp_path / "second.json") == 0
    result = _artifact(tmp_path / "second.json")
    assert result["artifact"]["attestation"]["level"] == "ATTESTED_EMPTY"
    assert result["export"]["status"] == "INTENTIONALLY_EMPTY"


@pytest.mark.parametrize("mutation", ["value", "validation", "attestation"])
def test_h3_tampered_v2_downgrades_with_actual_previous_level(tmp_path, capsys, mutation):
    _init(tmp_path)
    _, first = _attested_source(tmp_path)
    payload = _artifact(first)
    if mutation == "value":
        payload["parameters"]["ambient_temperature"]["value"] = 999.0
    elif mutation == "validation":
        payload["parameters"]["ambient_temperature"]["validation"] = {"state": "ACCEPTED"}
    else:
        payload["artifact"]["attestation"]["gate"]["n_approved"] = 99
    modified = tmp_path / "modified.json"
    modified.write_text(json.dumps(payload), encoding="utf-8")
    assert _export_json(modified, tmp_path / "out.json") == 0
    trust = _artifact(tmp_path / "out.json")["artifact"]["attestation"]
    assert trust["level"] == "UNVERIFIED"
    assert trust["downgraded_from"] == "ATTESTED"
    assert trust["notes"]


@pytest.mark.parametrize("target", ["gate", "registry", "artifact"])
def test_h3_modified_original_chain_downgrades(tmp_path, capsys, target):
    _init(tmp_path)
    registry = tmp_path / "registry.json"
    shutil.copy(REGISTRY, registry)
    gate = _gate(tmp_path / "gate.json", _approval())
    source = _assemble(tmp_path, "assembly", registry=registry, gate=gate)
    first = tmp_path / "first.json"
    assert _export_json(source, first) == 0
    capsys.readouterr()

    if target == "gate":
        gate.write_text(json.dumps({"approvals": []}), encoding="utf-8")
    elif target == "registry":
        records = json.loads(registry.read_text(encoding="utf-8"))
        records[0]["value"] = 999.0
        registry.write_text(json.dumps(records), encoding="utf-8")
    else:
        (source / "pybamm_export.json").write_text('{"ambient_temperature": 999.0}', encoding="utf-8")
    _run_reexport(tmp_path, first, capsys)


def _run_reexport(tmp_path: Path, first: Path, capsys) -> None:
    assert _export_json(first, tmp_path / f"re-{first.stem}.json", "--overwrite") == 0
    trust = _artifact(tmp_path / f"re-{first.stem}.json")["artifact"]["attestation"]
    assert trust["level"] == "UNVERIFIED"
    assert trust["downgraded_from"] == "ATTESTED"
    assert trust["notes"]


def test_h3_invalid_manifest_downgrades(tmp_path, capsys):
    _init(tmp_path)
    _, first = _attested_source(tmp_path)
    payload = _artifact(first)
    payload["artifact"]["attestation"]["manifest_path"] = str(tmp_path / "missing.json")
    modified = tmp_path / "modified.json"
    modified.write_text(json.dumps(payload), encoding="utf-8")
    assert _export_json(modified, tmp_path / "out.json") == 0
    trust = _artifact(tmp_path / "out.json")["artifact"]["attestation"]
    assert trust["level"] == "UNVERIFIED"
    assert trust["downgraded_from"] == "ATTESTED"


def test_h3_forged_attestation_claim_never_upgrades(tmp_path, capsys):
    _init(tmp_path)
    source, _ = _attested_source(tmp_path)
    claim = {"level": "ATTESTED", "manifest_path": str(source / "manifest.json")}
    payload = _v2_payload({"p": {"value": 1.0}}, **claim)
    direct = tmp_path / "direct.json"
    direct.write_text(json.dumps(payload), encoding="utf-8")
    assert _export_json(direct, tmp_path / "out.json") == 0
    result = _artifact(tmp_path / "out.json")
    assert result["artifact"]["attestation"]["level"] == "UNVERIFIED"
    assert result["approved_only"] is False


# --- M1-M4 ----------------------------------------------------------------
@pytest.mark.parametrize("version", ["1", "2"])
def test_m1_intentional_empty_not_marked_complete(tmp_path, capsys, version):
    _init(tmp_path)
    source = _assemble(tmp_path, "assembly", gate=None)
    assert main(["--json", "export", "--from", str(source), "--output",
                 str(tmp_path / f"out{version}.json"), "--overwrite",
                 "--schema-version", version]) == 0
    artifact = _artifact(tmp_path / f"out{version}.json")
    if version == "1":
        assert artifact["complete"] is False
    else:
        assert artifact["export"]["status"] == "INTENTIONALLY_EMPTY"
    assert _envelope(capsys)["data"]["export_status"] == "INTENTIONALLY_EMPTY"


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity", "true"])
def test_m2_non_finite_and_boolean_values_rejected(tmp_path, capsys, raw):
    _init(tmp_path)
    source = tmp_path / "input.json"
    source.write_text('{"p": ' + raw + '}', encoding="utf-8")
    assert _export_json(source, tmp_path / "out.json") == 2
    assert _envelope(capsys)["diagnostics"][0]["code"] == "E201"
    assert not (tmp_path / "out.json").exists()


def test_m2_serialisation_is_strict():
    from pybamm_closed_loop.cli_app.artifact import write_artifact_payload
    from pybamm_closed_loop.cli_app.artifact import Attestation, UNVERIFIED

    with pytest.raises(ValueError):
        write_artifact_payload(
            version=2, source_label="test", source_path="test", source_kind="direct_json",
            source_sha256="0", attestation=Attestation(UNVERIFIED, "none"),
            status="COMPLETE", entries={"p": {"value": float("nan"), "unit": "K",
                                               "pybamm_names": [], "metadata": {"unit": "K"}}},
            skipped=[], warnings=[], limitations=[], migrated_from=None,
            rubric_version=None, validation_policy="test", tool_version="test",
            generated="now", python_version="3",
        )


def test_m3_duplicate_json_keys_rejected(tmp_path, capsys):
    _init(tmp_path)
    source = tmp_path / "input.json"
    source.write_text('{"p": 1.0, "p": 2.0}', encoding="utf-8")
    assert _export_json(source, tmp_path / "out.json") == 2
    assert "Duplicate JSON key" in str(_envelope(capsys)["diagnostics"][0]["what"])


def test_m3_duplicate_canonical_ids_rejected(tmp_path, capsys):
    _init(tmp_path)
    source = tmp_path / "registry.json"
    source.write_text(json.dumps([
        {"canonical_id": "p", "value": 1.0, "value_unit": "K", "pybamm_names": [],
         "validation_state": "ACCEPTED"},
        {"canonical_id": "p", "value": 2.0, "value_unit": "K", "pybamm_names": [],
         "validation_state": "ACCEPTED"},
    ]), encoding="utf-8")
    gate = _gate(tmp_path / "gate.json", _approval("p"))
    assert _export_json(source, tmp_path / "out.json", "--gate", str(gate)) == 2
    assert "Duplicate canonical" in str(_envelope(capsys)["diagnostics"][0]["what"])


def test_m4_pybamm_registry_list_source_without_redundant_registry(tmp_path, capsys):
    _init(tmp_path)
    source = tmp_path / "registry.json"
    source.write_text(json.dumps([{
        "canonical_id": "ambient_temperature", "value": 298.15, "value_unit": "K",
        "pybamm_names": ["Ambient temperature [K]"], "validation_state": "ACCEPTED",
    }]), encoding="utf-8")
    gate = _gate(tmp_path / "gate.json", _approval())
    assert main(["--json", "export", "--from", str(source), "--output",
                 str(tmp_path / "params.py"), "--overwrite", "--format", "pybamm",
                 "--gate", str(gate)]) == 0
    assert "Ambient temperature [K]" in (tmp_path / "params.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("record", [
    {"parameter": "p", "decision": "USE", "approved": True, "rubric_version": "rubric-v2"},
    {"parameter": "p", "decision": "USE", "approved": True, "approver": "o", "rubric_version": 5},
    {"decision": "USE", "approved": True, "approver": "o", "rubric_version": "rubric-v2"},
    "not-an-object",
])
def test_m5_malformed_gate_is_domain_error(tmp_path, capsys, record):
    _init(tmp_path)
    gate = _gate(tmp_path / "gate.json", record)
    source = tmp_path / "registry.json"
    source.write_text(json.dumps([{"canonical_id": "p", "value": 1.0, "value_unit": "K",
                                   "pybamm_names": [], "validation_state": "ACCEPTED"}]),
                      encoding="utf-8")
    assert _export_json(source, tmp_path / "out.json", "--gate", str(gate)) == 2
    assert _envelope(capsys)["diagnostics"][0]["code"] == "E201"


# --- Phase 5 / regression guards -----------------------------------------
def test_boolean_schema_version_rejected(tmp_path, capsys):
    _init(tmp_path)
    source = tmp_path / "input.json"
    source.write_text('{"schema_version": true, "parameters": {"p": {"value": 1.0}}}',
                      encoding="utf-8")
    assert _export_json(source, tmp_path / "out.json") == 2
    assert "Unsupported export schema version" in str(_envelope(capsys)["diagnostics"][0]["what"])


def test_archived_fixture_unchanged():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == (
        "6b4ecf8827c929655bbe2647c62e021f6ced45f1d7f577a1a01ff84a4ade4796"
    )


def test_archived_fixture_still_fails_unit_check(capsys):
    assert main(["--json", "validate", str(FIXTURE)]) == 1
    checks = {c["name"]: c["level"] for c in _envelope(capsys)["data"]["results"][0]["checks"]}
    assert checks["physical_plausibility"] == "FAILED"
