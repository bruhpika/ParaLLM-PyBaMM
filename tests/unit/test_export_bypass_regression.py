"""Phase 1 regression: close the registry/gate export bypass.

The review found that `parallm export --format pybamm --from <registry-copy>
--gate <fake>` would write a tampered value even when the gate's decision,
rubric version and binding hash did not describe that value.  These tests
reproduce the bypass using only public CLI commands and clearly synthetic gate
files (no human approval is simulated without an explicit label).
"""

from __future__ import annotations

import json
from pathlib import Path

from pybamm_closed_loop.cli import main

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data" / "registry" / "registry.json"
TARGET = ROOT / "configs" / "v2" / "target_lgm50.yaml"
PARAMETER = "cell_electrode_width"


def _config(tmp_path: Path) -> list[str]:
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path: Path) -> None:
    assert main([*_config(tmp_path), "init", "--workspace",
                 str(tmp_path / "ws"), "--non-interactive"]) == 0


def _envelope(capsys) -> dict:
    output = capsys.readouterr().out
    return json.loads(output[output.index("{"):])


def _tampered_registry(tmp_path: Path) -> Path:
    """A registry copy with one value changed to a labelled synthetic 999."""
    records = json.loads(REGISTRY.read_text(encoding="utf-8"))
    record = next(r for r in records if r["canonical_id"] == PARAMETER)
    record["value"] = 999
    record["normalized_value"] = 999
    path = tmp_path / "registry_copy.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def _fake_gate(tmp_path: Path, *, approved: bool = True) -> Path:
    """SYNTHETIC gate: REVIEW decision, made-up rubric, zero binding hash."""
    path = tmp_path / "fake_gate.json"
    path.write_text(json.dumps({"approvals": [{
        "parameter": PARAMETER,
        "decision": "REVIEW",
        "approved": approved,
        "approver": "synthetic-reviewer",
        "rubric_version": "made-up",
        "binding_sha256": "0" * 64,
        "timestamp": "2026-11-28T00:00:00Z",
        "note": "SYNTHETIC bypass reproduction; not a human approval",
    }]}), encoding="utf-8")
    return path


def test_registry_export_bypass_is_closed(tmp_path, capsys):
    """Reproduces the reported bug: 999 must not be exported through a fake gate."""
    _init(tmp_path)
    registry = _tampered_registry(tmp_path)
    gate = _fake_gate(tmp_path)
    out = tmp_path / "params.py"

    result = main([*_config(tmp_path), "--json", "export",
                   "--format", "pybamm", "--from", str(registry),
                   "--gate", str(gate), "--output", str(out)])

    assert result == 2, _envelope(capsys)["diagnostics"]
    assert not out.exists(), "a synthetic/mismatched gate must not write an export"
    diagnostics = _envelope(capsys)["diagnostics"]
    text = json.dumps(diagnostics)
    assert any(word in text for word in ("binding", "decision", "rubric", "verif"))


def test_raw_registry_refused_without_gate(tmp_path, capsys):
    """A raw registry cannot be verified without assembled decisions."""
    _init(tmp_path)
    registry = _tampered_registry(tmp_path)
    out = tmp_path / "params.py"
    result = main([*_config(tmp_path), "--json", "export",
                   "--format", "pybamm", "--from", str(registry),
                   "--output", str(out)])
    assert result == 2
    assert not out.exists()
    text = json.dumps(_envelope(capsys)["diagnostics"])
    assert "assembled decisions" in text


def _assembly_with_synthetic_gate(tmp_path: Path, gate: Path) -> Path:
    """Build an assembly folder using a clearly labelled SYNTHETIC gate file."""
    out = tmp_path / "assembly"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(REGISTRY), "--out", str(out),
                 "--gate", str(gate)]) == 0
    return out


def _dossier_approval(tmp_path: Path) -> tuple[Path, dict]:
    """Assemble once without a gate, then derive a valid synthetic approval."""
    from pybamm_closed_loop.assembly.gate import binding_sha256

    draft = tmp_path / "draft"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(REGISTRY), "--out", str(draft)]) == 0
    report = json.loads((draft / "report.json").read_text(encoding="utf-8"))
    dossier = next(d for d in report["parameters"]
                   if d["parameter"] == "ambient_temperature")
    approval = {
        "parameter": "ambient_temperature",
        "decision": dossier["decision"],
        "approved": True,
        "approver": "synthetic-reviewer",
        "rubric_version": dossier["rubric_version"],
        "binding_sha256": binding_sha256(dossier),
        "timestamp": "2026-11-28T00:00:00Z",
        "note": "SYNTHETIC approval for a regression test; not a human decision",
    }
    gate = tmp_path / "synthetic_gate.json"
    gate.write_text(json.dumps({"approvals": [approval]}), encoding="utf-8")
    return gate, approval


def test_assembly_reverifies_bindings_not_only_file_hashes(tmp_path, capsys):
    """An assembly gate with a zero binding hash must not export a value."""
    _init(tmp_path)
    gate, approval = _dossier_approval(tmp_path)
    approval["binding_sha256"] = "0" * 64
    gate.write_text(json.dumps({"approvals": [approval]}), encoding="utf-8")
    source = _assembly_with_synthetic_gate(tmp_path, gate)
    out = tmp_path / "params.py"
    assert main([*_config(tmp_path), "--json", "export", "--format", "pybamm",
                 "--from", str(source), "--output", str(out)]) == 2
    assert not out.exists()
    text = json.dumps(_envelope(capsys)["diagnostics"])
    assert "binding mismatch" in text


def test_assembly_rejects_review_decision(tmp_path, capsys):
    """A REVIEW decision is not exportable even with a matching value hash."""
    _init(tmp_path)
    gate, approval = _dossier_approval(tmp_path)
    approval["decision"] = "REVIEW"
    gate.write_text(json.dumps({"approvals": [approval]}), encoding="utf-8")
    source = _assembly_with_synthetic_gate(tmp_path, gate)
    out = tmp_path / "params.py"
    assert main([*_config(tmp_path), "--json", "export", "--format", "pybamm",
                 "--from", str(source), "--output", str(out)]) == 2
    assert not out.exists()
    text = json.dumps(_envelope(capsys)["diagnostics"])
    assert "not exportable" in text


def test_shared_verifier_detects_exported_value_change():
    """The shared verifier checks the exported value, not just the gate record."""
    from pybamm_closed_loop.assembly import ApprovalGate
    from pybamm_closed_loop.assembly.gate import binding_sha256, verify_gate_bindings

    dossier = {
        "parameter": "p", "decision": "USE", "rubric_version": "rubric-v3",
        "selected": {"value": 298.15, "unit": "K"},
        "evidence": {"source_id": "synthetic", "locator": "test"},
    }
    gate = ApprovalGate()
    gate.approve("p", "USE", "synthetic-reviewer", "rubric-v3", binding_sha256(dossier))
    assert verify_gate_bindings(gate, {"p": dossier}, exported_values={"p": 298.15}).approved == {"p"}
    result = verify_gate_bindings(gate, {"p": dossier}, exported_values={"p": 999})
    assert result.approved == set()
    assert "exported value mismatch" in result.reasons["p"]


def test_honest_assembly_export_remains_attested(tmp_path, capsys):
    """A real approval bound to the assembled decision still exports."""
    _init(tmp_path)
    gate, _ = _dossier_approval(tmp_path)
    source = _assembly_with_synthetic_gate(tmp_path, gate)
    assert main([*_config(tmp_path), "--json", "export", "--format", "pybamm",
                 "--from", str(source), "--output", str(tmp_path / "params.py")]) == 0
    envelope = _envelope(capsys)
    assert envelope["data"]["attestation"]["level"] == "ATTESTED"
    assert "Ambient temperature [K]" in (tmp_path / "params.py").read_text(encoding="utf-8")
