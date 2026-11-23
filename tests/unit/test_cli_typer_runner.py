"""Tests using Typer's CliRunner against the real application object."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pybamm_closed_loop import __version__
from pybamm_closed_loop.cli import main
from pybamm_closed_loop.cli_app.app import app
from pybamm_closed_loop.cli_app.errors import ConfigError

ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


def test_runner_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("doctor", "evidence", "validate", "export", "calibrate"):
        assert name in result.stdout


def test_runner_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"parallm {__version__}"


def test_runner_doctor_json():
    result = runner.invoke(app, ["--json", "doctor"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "doctor"
    assert payload["data"]["summary"]["failed"] == 0


def test_runner_validate_json_marks_unavailable_checks(tmp_path):
    payload_file = tmp_path / "candidate.json"
    payload_file.write_text(json.dumps({
        "parameter_name": "particle radius",
        "value": 5.86,
        "unit": "um",
        "definition": "particle radius",
        "material": "graphite",
        "temperature": None,
        "cell_config": "LG M50",
        "measurement_method": "SEM",
        "qualifier": "measured",
        "context": "measurement",
        "source": {"document_id": "paper", "quote": "measurement"},
        "reported_uncertainty": None,
    }), encoding="utf-8")
    result = runner.invoke(app, ["--json", "validate", str(payload_file)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    levels = {c["name"]: c["level"] for c in payload["data"]["results"][0]["checks"]}
    assert levels["check_provenance"] == "NOT CHECKED"
    assert levels["conflicting_evidence"] == "NOT CHECKED"


def test_runner_evidence_inspect_uses_real_registry():
    result = runner.invoke(app, [
        "evidence", "inspect", "ambient_temperature",
        "--registry", str(ROOT / "data" / "registry" / "registry.json"),
    ])
    assert result.exit_code == 0
    assert "ambient_temperature" in result.stdout
    assert "NOT CALIBRATED" in result.stdout
    assert "298.15" in result.stdout


def test_runner_structured_error_and_quiet_mode(tmp_path):
    config = tmp_path / "config.toml"
    args = ["--config", str(config), "--json", "status"]
    with pytest.raises(ConfigError):
        runner.invoke(app, args, catch_exceptions=False)
    assert main(args) == 2

    assert runner.invoke(app, [
        "--config", str(config), "init",
        "--workspace", str(tmp_path / "ws"), "--non-interactive",
    ]).exit_code == 0
    result = runner.invoke(app, ["--config", str(config), "--quiet", "status"])
    assert result.exit_code == 0
    assert "ParaLLM-PyBaMM" not in result.stdout
    assert "workspace=" in result.stdout
