"""Integration + regression tests for the CLI against the real scientific engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pybamm_closed_loop.cli import main

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data" / "registry" / "registry.json"
TARGET = ROOT / "configs" / "v2" / "target_lgm50.yaml"
DOCUMENTS = ROOT / "data" / "raw_documents"
P2 = ROOT / "results" / "p2"


def _config(tmp_path: Path):
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path: Path) -> None:
    assert main([*_config(tmp_path), "init", "--workspace", str(tmp_path / "ws"), "--non-interactive"]) == 0


def test_assemble_via_cli_preserves_outputs(tmp_path, capsys):
    _init(tmp_path)
    capsys.readouterr()
    out = tmp_path / "assembly"
    rc = main([
        *_config(tmp_path), "assemble",
        "--target", str(TARGET),
        "--registry", str(REGISTRY),
        "--out", str(out),
        "--documents", str(DOCUMENTS),
        "--p2-results", str(P2),
    ])
    assert rc == 0
    for name in ("report.json", "report.md", "pybamm_export.json", "manifest.json"):
        assert (out / name).is_file()
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["n_parameters"] == len(json.loads(REGISTRY.read_text(encoding="utf-8")))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["command"] == "parallm assemble"
    assert manifest["n_exported"] == 0
    assert json.loads((out / "pybamm_export.json").read_text(encoding="utf-8")) == {}


def test_export_with_gate_writes_installed_pybamm_names(tmp_path, capsys):
    _init(tmp_path)
    capsys.readouterr()
    source = tmp_path / "assembly"
    source.mkdir()
    (source / "pybamm_export.json").write_text(
        json.dumps({"ambient_temperature": 298.15}), encoding="utf-8"
    )
    (tmp_path / "registry.json").write_text(json.dumps([
        {
            "canonical_id": "ambient_temperature",
            "value": 298.15,
            "value_unit": "K",
            "pybamm_names": ["Ambient temperature [K]"],
        }
    ]), encoding="utf-8")
    output = tmp_path / "parameters.py"
    assert main([
        *_config(tmp_path), "--json", "export",
        "--from", str(source),
        "--output", str(output),
        "--format", "pybamm",
        "--registry", str(tmp_path / "registry.json"),
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "Ambient temperature [K]" in payload["data"]["parameters"]
    module = output.read_text(encoding="utf-8")
    assert module.startswith("PARAMETERS = {")
    assert "Ambient temperature [K]" in module


@pytest.mark.integration
def test_simulate_command_runs_pinned_engine(tmp_path):
    _init(tmp_path)
    output = tmp_path / "baseline"
    assert main([
        *_config(tmp_path), "simulate",
        "--config", str(ROOT / "configs" / "baseline_dfn.yaml"),
        "--out", str(output),
    ]) == 0
    assert (output / "run_manifest.json").is_file()
    assert (output / "parameter_snapshot.json").is_file()
    assert (output / "solution_arrays.npz").is_file()
