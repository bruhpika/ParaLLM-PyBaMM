"""Phase 3 (approved design): a human resolves REVIEW decisions with reason/evidence.

Only public CLI commands are used.  Reviewer names and reasons are clearly
labelled SYNTHETIC; no human approval is simulated implicitly.
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
    out = capsys.readouterr().out
    return json.loads(out[out.index("{"):])


def _assemble(tmp_path: Path, out: str, *extra: str) -> Path:
    directory = tmp_path / out
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(REGISTRY), "--out", str(directory), *extra]) == 0
    return directory


def _review_parameter(tmp_path: Path) -> tuple[Path, dict]:
    source = _assemble(tmp_path, "initial")
    report = json.loads((source / "report.json").read_text(encoding="utf-8"))
    dossier = next(d for d in report["parameters"] if d["decision"] == "REVIEW")
    return source, dossier


def test_resolve_writes_bound_review_record(tmp_path, capsys):
    """A REVIEW can be resolved by a human with reason and evidence recorded."""
    _init(tmp_path)
    _, dossier = _review_parameter(tmp_path)
    out = tmp_path / "resolution.json"
    assert main([*_config(tmp_path), "--json", "resolve", "--assembly", str(tmp_path / "initial"),
                 "--parameter", dossier["parameter"], "--decision", "USE",
                 "--reason", "SYNTHETIC human judgement: applicability confirmed",
                 "--evidence", "SYNTHETIC locator Table I",
                 "--reviewer", "SYNTHETIC-OWNER", "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    record = payload["decisions"][0]
    assert record["original_decision"] == "REVIEW"
    assert record["resolved_decision"] == "USE"
    assert len(record["binding_sha256"]) == 64
    assert "SYNTHETIC human judgement" in record["reason"]
    assert _envelope(capsys)["data"]["binding_sha256"] == record["binding_sha256"]


def test_resolve_refuses_non_review_decision(tmp_path, capsys):
    """Only REVIEW decisions may be resolved."""
    _init(tmp_path)
    source = _assemble(tmp_path, "initial")
    report = json.loads((source / "report.json").read_text(encoding="utf-8"))
    dossier = next(d for d in report["parameters"] if d["decision"] in ("USE", "FIX"))
    assert main([*_config(tmp_path), "--json", "resolve", "--assembly", str(source),
                 "--parameter", dossier["parameter"], "--decision", "USE",
                 "--reason", "SYNTHETIC", "--evidence", "SYNTHETIC",
                 "--reviewer", "SYNTHETIC-OWNER", "--out", str(tmp_path / "r.json")]) == 2
    assert "only a REVIEW decision" in str(_envelope(capsys)["diagnostics"][0]["why"])


def test_resolution_enables_export_with_recorded_reason(tmp_path, capsys):
    """A resolved parameter can be approved and exported, with rationale stored."""
    _init(tmp_path)
    _, dossier = _review_parameter(tmp_path)
    resolution = tmp_path / "resolution.json"
    assert main([*_config(tmp_path), "--quiet", "resolve", "--assembly", str(tmp_path / "initial"),
                 "--parameter", dossier["parameter"], "--decision", "USE",
                 "--reason", "SYNTHETIC reason: cell-specific value accepted",
                 "--evidence", "SYNTHETIC evidence Table I",
                 "--reviewer", "SYNTHETIC-OWNER", "--out", str(resolution)]) == 0

    rebuilt = tmp_path / "rebuilt"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(REGISTRY), "--out", str(rebuilt),
                 "--resolution", str(resolution)]) == 0
    report = json.loads((rebuilt / "report.json").read_text(encoding="utf-8"))
    resolved = next(d for d in report["parameters"] if d["parameter"] == dossier["parameter"])
    assert resolved["decision"] == "USE"
    assert resolved["resolution"]["reason"] == "SYNTHETIC reason: cell-specific value accepted"

    # Approve the resolved dossier through a labelled synthetic gate.
    from pybamm_closed_loop.assembly.gate import binding_sha256

    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"approvals": [{
        "parameter": resolved["parameter"], "decision": "USE", "approved": True,
        "approver": "SYNTHETIC-OWNER", "rubric_version": resolved["rubric_version"],
        "binding_sha256": binding_sha256(resolved),
        "timestamp": "2026-11-28T00:00:00Z", "note": "SYNTHETIC approval",
    }]}))
    final = tmp_path / "final"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(REGISTRY), "--out", str(final),
                 "--resolution", str(resolution), "--gate", str(gate)]) == 0
    exported = json.loads((final / "pybamm_export.json").read_text(encoding="utf-8"))
    assert dossier["parameter"] in exported


def test_modified_resolution_file_is_refused_on_export(tmp_path, capsys):
    """Export fails if the recorded human resolution is edited after assembly."""
    _init(tmp_path)
    _, dossier = _review_parameter(tmp_path)
    resolution = tmp_path / "resolution.json"
    assert main([*_config(tmp_path), "--quiet", "resolve", "--assembly", str(tmp_path / "initial"),
                 "--parameter", dossier["parameter"], "--decision", "USE",
                 "--reason", "SYNTHETIC reason", "--evidence", "SYNTHETIC evidence",
                 "--reviewer", "SYNTHETIC-OWNER", "--out", str(resolution)]) == 0
    rebuilt = _assemble_from_resolution(tmp_path, resolution)

    payload = json.loads(resolution.read_text(encoding="utf-8"))
    payload["decisions"][0]["reason"] = "EDITED AFTER ASSEMBLY"
    resolution.write_text(json.dumps(payload), encoding="utf-8")

    assert main([*_config(tmp_path), "--json", "export", "--from", str(rebuilt),
                 "--output", str(tmp_path / "out.json")]) == 2
    text = json.dumps(_envelope(capsys)["diagnostics"])
    assert "resolution file was modified" in text


def _assemble_from_resolution(tmp_path: Path, resolution: Path) -> Path:
    directory = tmp_path / "rebuilt2"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(REGISTRY), "--out", str(directory),
                 "--resolution", str(resolution)]) == 0
    return directory
