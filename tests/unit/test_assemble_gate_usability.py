"""Phase 2 regression: assemble must produce a usable, fail-closed gate.

The review found three defects:
1. `assemble` never writes a binding hash anywhere a CLI user can use it, so
   a valid gate cannot be created from CLI output alone.
2. Parameters blocked from export are silently dropped; no reason is shown.
3. The legacy gate error points to a regeneration step that does not exist.

These tests reproduce all three using only public CLI commands.  Synthetic
gate files are clearly labelled; no human approval is simulated implicitly.
"""

from __future__ import annotations

import json
from pathlib import Path

from pybamm_closed_loop.cli import main

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data" / "registry" / "registry.json"
TARGET = ROOT / "configs" / "v2" / "target_lgm50.yaml"


def _config(tmp_path: Path) -> list[str]:
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path: Path) -> None:
    assert main([*_config(tmp_path), "init", "--workspace",
                 str(tmp_path / "ws"), "--non-interactive"]) == 0


def _envelope(capsys) -> dict:
    output = capsys.readouterr().out
    return json.loads(output[output.index("{"):])


def _assemble(tmp_path: Path, out: str, gate: Path | None = None,
              *extra: str) -> int:
    args = [*_config(tmp_path), "assemble", "--target", str(TARGET),
            "--registry", str(REGISTRY), "--out", str(tmp_path / out), *extra]
    if gate is not None:
        args += ["--gate", str(gate)]
    return main(args)


def test_assemble_writes_pending_gate_with_bindings(tmp_path, capsys):
    """assemble must emit a pending gate with unapproved, hash-bound entries."""
    _init(tmp_path)
    assert _assemble(tmp_path, "assembly") == 0
    capsys.readouterr()

    pending = tmp_path / "assembly" / "gate.pending.json"
    assert pending.is_file(), "assemble did not write a pending gate file"
    payload = json.loads(pending.read_text(encoding="utf-8"))
    approvals = payload.get("approvals")
    assert isinstance(approvals, list) and approvals, "no pending approvals were written"
    for record in approvals:
        assert record["approved"] is False, "pending gate must approve nothing"
        assert len(record["binding_sha256"]) == 64
        assert record["decision"] in ("USE", "FIX"), "only exportable decisions belong here"
        assert record["rubric_version"]
        assert record["parameter"]


def test_pending_gate_is_not_read_as_an_approval(tmp_path, capsys):
    """An unedited pending gate exports nothing from the assembly folder."""
    _init(tmp_path)
    assert _assemble(tmp_path, "assembly") == 0
    capsys.readouterr()
    pending = tmp_path / "assembly" / "gate.pending.json"

    assert _assemble(tmp_path, "reassembly", gate=pending) == 0
    capsys.readouterr()
    # The pending gate has every entry unapproved, so no parameter is approved.
    assert not json.loads(
        (tmp_path / "reassembly" / "pybamm_export.json").read_text(encoding="utf-8")
    )


def test_assemble_reports_each_block_reason(tmp_path, capsys):
    """Blocked-from-export parameters must carry a reason in text and JSON."""
    _init(tmp_path)
    gate = tmp_path / "synthetic_bad_gate.json"
    gate.write_text(json.dumps({"approvals": [{
        "parameter": "ambient_temperature", "decision": "USE", "approved": True,
        "approver": "synthetic-reviewer", "rubric_version": "rubric-v4",
        "timestamp": "2026-11-28T00:00:00Z",
        "binding_sha256": "0" * 64,
        "note": "SYNTHETIC gate with a deliberately wrong binding",
    }]}), encoding="utf-8")

    args = [*_config(tmp_path), "--json", "assemble", "--target", str(TARGET),
            "--registry", str(REGISTRY), "--out", str(tmp_path / "assembly"),
            "--gate", str(gate)]
    assert main(args) == 0
    envelope = _envelope(capsys)
    blocked = envelope["data"].get("blocked")
    assert isinstance(blocked, dict) and blocked, "JSON output has no block reasons"
    assert "ambient_temperature" in blocked
    assert "binding" in blocked["ambient_temperature"].lower()


def test_assemble_shows_block_reasons_in_text(tmp_path, capsys):
    """Text output must show each block reason, not just a count."""
    _init(tmp_path)
    gate = tmp_path / "synthetic_bad_gate.json"
    gate.write_text(json.dumps({"approvals": [{
        "parameter": "ambient_temperature", "decision": "USE", "approved": True,
        "approver": "synthetic-reviewer", "rubric_version": "rubric-v4",
        "timestamp": "2026-11-28T00:00:00Z",
        "binding_sha256": "0" * 64,
        "note": "SYNTHETIC gate with a deliberately wrong binding",
    }]}), encoding="utf-8")

    assert _assemble(tmp_path, "assembly", gate=gate) == 0
    text = capsys.readouterr().out
    assert "BLOCKED" in text, "no blocked-from-export section in text output"
    assert "ambient_temperature" in text
    assert "binding" in text.lower()


def test_legacy_gate_error_points_to_pending_gate(tmp_path, capsys):
    """The missing-binding error must name the real regeneration artefact."""
    _init(tmp_path)
    legacy = tmp_path / "synthetic_legacy_gate.json"
    legacy.write_text(json.dumps({"approvals": [{
        "parameter": "ambient_temperature", "decision": "USE", "approved": True,
        "approver": "synthetic-reviewer", "rubric_version": "rubric-v4",
        "timestamp": "2026-11-28T00:00:00Z",
        "note": "SYNTHETIC legacy gate without a binding hash",
    }]}), encoding="utf-8")

    args = [*_config(tmp_path), "--json", "assemble", "--target", str(TARGET),
            "--registry", str(REGISTRY), "--out", str(tmp_path / "assembly"),
            "--gate", str(legacy)]
    assert main(args) == 2
    diagnostic = _envelope(capsys)["diagnostics"][0]
    assert "gate.pending.json" in str(diagnostic["why"])
