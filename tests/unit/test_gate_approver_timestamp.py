"""Step 2 regression: an approval needs a real approver and a valid timestamp.

Only clearly labelled SYNTHETIC gate files are used. No human is simulated
implicitly and no other intermediate output is edited.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    out = capsys.readouterr().out
    return json.loads(out[out.index("{"):])


def _assembly(tmp_path: Path, gate: Path, out: str = "assembly") -> int:
    return main([*_config(tmp_path), "--quiet", "--json", "assemble",
                 "--target", str(TARGET), "--registry", str(REGISTRY),
                 "--out", str(tmp_path / out), "--gate", str(gate)])


def _gate_from_pending(tmp_path: Path, **overrides) -> Path:
    """A gate copy of a real pending entry; only the listed fields are changed."""
    draft = tmp_path / "draft"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(REGISTRY), "--out", str(draft)]) == 0
    pending = json.loads((draft / "gate.pending.json").read_text(encoding="utf-8"))
    entry = pending["approvals"][0]
    entry.update(approved=True, approver="SYNTHETIC-OWNER",
                 timestamp="2026-11-28T00:00:00Z", note="SYNTHETIC approval")
    entry.update(overrides)
    path = tmp_path / "gate.json"
    path.write_text(json.dumps({"approvals": [entry]}), encoding="utf-8")
    return path


def test_pending_gate_with_only_approved_changed_is_refused(tmp_path, capsys):
    """Flipping only `approved` in gate.pending.json must not approve anything."""
    _init(tmp_path)
    draft = tmp_path / "draft"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(REGISTRY), "--out", str(draft)]) == 0
    pending = json.loads((draft / "gate.pending.json").read_text(encoding="utf-8"))
    entry = pending["approvals"][0]
    entry["approved"] = True  # the only change a user makes
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"approvals": [entry]}), encoding="utf-8")
    record = json.loads(gate.read_text())["approvals"][0]
    assert record["approver"] == "NOT_RECORDED"
    assert record["timestamp"] == "NOT_RECORDED"
    assert _assembly(tmp_path, gate) == 2
    text = json.dumps(_envelope(capsys)["diagnostics"])
    assert "approver" in text or "timestamp" in text


@pytest.mark.parametrize("approver", ["", "   ", "not_recorded", "Not_Recorded"])
def test_whitespace_or_placeholder_approver_refused(tmp_path, capsys, approver):
    """Empty, whitespace and NOT_RECORDED (any case) approvers are refused."""
    _init(tmp_path)
    gate = _gate_from_pending(tmp_path, approver=approver)
    assert _assembly(tmp_path, gate) == 2, approver
    assert "approver" in json.dumps(_envelope(capsys)["diagnostics"])


@pytest.mark.parametrize("timestamp", ["NOT_RECORDED", "yesterday", "2026-13-01T00:00:00Z", ""])
def test_invalid_timestamp_refused(tmp_path, capsys, timestamp):
    """A non-ISO-8601 timestamp cannot approve a parameter."""
    _init(tmp_path)
    gate = _gate_from_pending(tmp_path, timestamp=timestamp)
    assert _assembly(tmp_path, gate) == 2, timestamp
    assert "timestamp" in json.dumps(_envelope(capsys)["diagnostics"])


def test_valid_approval_still_exports(tmp_path, capsys):
    """A real approver name and an ISO timestamp still approve and export."""
    _init(tmp_path)
    gate = _gate_from_pending(tmp_path)
    assert _assembly(tmp_path, gate) == 0
    out = tmp_path / "export.json"
    assert main([*_config(tmp_path), "--json", "export", "--from", str(tmp_path / "assembly"),
                 "--output", str(out)]) == 0
    assert json.loads(out.read_text())["parameters"]


def test_export_reverification_refuses_bad_approver(tmp_path, capsys):
    """Export fails if the approved gate is edited to a placeholder approver."""
    _init(tmp_path)
    gate = _gate_from_pending(tmp_path)
    assert _assembly(tmp_path, gate, out="assembly") == 0
    out = tmp_path / "export.json"
    assert main([*_config(tmp_path), "--json", "export", "--from", str(tmp_path / "assembly"),
                 "--output", str(out)]) == 0

    record = json.loads(gate.read_text())
    record["approvals"][0]["approver"] = "NOT_RECORDED"
    gate.write_text(json.dumps(record), encoding="utf-8")
    capsys.readouterr()

    assert main([*_config(tmp_path), "--json", "export", "--from", str(tmp_path / "assembly"),
                 "--output", str(tmp_path / "export2.json")]) == 2
    text = json.dumps(_envelope(capsys)["diagnostics"])
    assert "gate file" in text.lower() or "approver" in text
    assert not (tmp_path / "export2.json").exists()
