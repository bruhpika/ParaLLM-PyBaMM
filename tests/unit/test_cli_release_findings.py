"""Regression tests for the six HIGH release-audit findings (H1-H6)."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

from pybamm_closed_loop.cli import main
from pybamm_closed_loop.cli_app.commands.science import calibration_state

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "examples" / "candidate_archived.json"
REGISTRY = ROOT / "data" / "registry" / "registry.json"


def _config(tmp_path: Path) -> list[str]:
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path: Path) -> None:
    assert main([*_config(tmp_path), "init",
                 "--workspace", str(tmp_path / "battery-research"),
                 "--non-interactive"]) == 0


def _envelope(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


# --- H1 -------------------------------------------------------------------
def test_invalid_arguments_are_usage_errors_not_internal_bugs(capsys):
    assert main(["--no-color", "validate"]) == 2
    err = capsys.readouterr().err
    assert "Missing argument" in err
    assert "E199" not in err and "Unexpected CLI failure" not in err

    assert main(["--json", "--badflag"]) == 2
    payload = _envelope(capsys)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["code"] == "E100"
    assert "No such option" in payload["diagnostics"][0]["what"]


def test_version_callback_still_exits_cleanly(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip().startswith("parallm ")


# --- H2 -------------------------------------------------------------------
def test_documented_json_examples_execute_and_emit_valid_json(capsys):
    assert main(["--json", "doctor"]) == 0
    doctor = _envelope(capsys)
    assert doctor["command"] == "doctor"
    assert set(("schema_version", "command", "status", "data", "diagnostics")) <= set(doctor)
    assert capsys.readouterr().err == ""

    assert main(["--json", "validate", str(FIXTURE), "--strict"]) == 1
    validation = _envelope(capsys)
    assert validation["command"] == "validate"
    assert validation["status"] == "failed"
    assert validation["diagnostics"] == []

    doc = (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8")
    for command in re.findall(r"^parallm\s+(.+)$", doc, flags=re.MULTILINE):
        tokens = command.split()
        if any(token in ("--json", "--quiet", "--debug", "--no-color") for token in tokens):
            assert tokens[0].startswith("-"), f"global option after subcommand: parallm {command}"


# --- H3 -------------------------------------------------------------------
def test_pybamm_export_refuses_missing_registry_without_writing(tmp_path, capsys):
    _init(tmp_path)
    source = tmp_path / "assembly"
    source.mkdir()
    (source / "pybamm_export.json").write_text(
        json.dumps({"ambient_temperature": 298.15}), encoding="utf-8"
    )
    output = tmp_path / "parameters.py"

    assert main([*_config(tmp_path), "--no-color", "export", "--format", "pybamm",
                 "--from", str(source), "--output", str(output)]) == 2
    err = capsys.readouterr().err
    assert "E404" in err and "registry is required" in err
    assert not output.exists()


def test_pybamm_export_refuses_empty_mapping_without_writing(tmp_path, capsys):
    _init(tmp_path)
    source = tmp_path / "assembly"
    source.mkdir()
    (source / "pybamm_export.json").write_text(
        json.dumps({"ambient_temperature": 298.15}), encoding="utf-8"
    )
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([
        {"canonical_id": "unmapped_parameter", "value": 1.0, "value_unit": "dimensionless"}
    ]), encoding="utf-8")
    output = tmp_path / "parameters.py"

    assert main([*_config(tmp_path), "--no-color", "export", "--format", "pybamm",
                 "--from", str(source), "--output", str(output),
                 "--registry", str(registry)]) == 2
    assert "E404" in capsys.readouterr().err
    assert not output.exists()


def test_pybamm_export_uses_manifest_registry_and_marks_partial(tmp_path, capsys):
    _init(tmp_path)
    source = tmp_path / "assembly"
    source.mkdir()
    (source / "pybamm_export.json").write_text(
        json.dumps({"ambient_temperature": 298.15, "not_mapped": 1.0}), encoding="utf-8"
    )
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([
        {"canonical_id": "ambient_temperature", "value": 298.15, "value_unit": "K",
         "pybamm_names": ["Ambient temperature [K]"]}
    ]), encoding="utf-8")
    (source / "manifest.json").write_text(
        json.dumps({"registry": {"path": str(registry)}}), encoding="utf-8"
    )
    output = tmp_path / "parameters.py"
    capsys.readouterr()

    assert main([*_config(tmp_path), "--json", "export", "--format", "pybamm",
                 "--from", str(source), "--output", str(output)]) == 0
    payload = _envelope(capsys)
    data = payload["data"]
    assert "Ambient temperature [K]" in data["parameters"]
    assert data["n_exported"] == 1 and data["skipped"] == 1
    assert data["complete"] is False
    assert "Ambient temperature [K]" in output.read_text(encoding="utf-8")


# --- H4 -------------------------------------------------------------------
def test_calibration_state_is_identical_in_explain_and_evidence_inspect(capsys):
    assert main(["--no-color", "explain", "neg_particle_diffusivity",
                 "--registry", str(REGISTRY)]) == 0
    explain_out = capsys.readouterr().out
    assert "LITERATURE FIT REPORTED" in explain_out
    assert "NOT CALIBRATED" not in explain_out

    assert main(["--no-color", "evidence", "inspect", "neg_particle_diffusivity",
                 "--registry", str(REGISTRY)]) == 0
    inspect_out = capsys.readouterr().out
    assert "LITERATURE FIT REPORTED" in inspect_out
    assert "NOT CALIBRATED" not in inspect_out

    assert main(["--json", "explain", "neg_particle_diffusivity",
                 "--registry", str(REGISTRY)]) == 0
    explain_payload = _envelope(capsys)["data"]["calibration"]["status"]
    assert main(["--json", "evidence", "inspect", "neg_particle_diffusivity",
                 "--registry", str(REGISTRY)]) == 0
    inspect_payload = _envelope(capsys)["data"]["calibration"]["status"]
    assert explain_payload == inspect_payload == "LITERATURE FIT REPORTED"


def test_calibration_state_helper_distinguishes_origin_from_recorded_fit():
    assert calibration_state({"status": "CALIBRATED"}, None) == "LITERATURE FIT REPORTED"
    assert calibration_state({"status": "ASSUMED"}, None) == "NOT CALIBRATED"
    fit = {"recovery": {"p": {"estimate": 1.0, "truth": 1.0}}}
    assert calibration_state({"status": "CALIBRATED"}, fit) == "SYNTHETIC FIT RECORDED"
    assert calibration_state({"status": "LITERATURE_DERIVED"}, fit) == "SYNTHETIC FIT RECORDED"


# --- H5 -------------------------------------------------------------------
def test_missing_pypdf_maps_to_e301(monkeypatch, tmp_path, capsys):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    real_find_spec = importlib.util.find_spec

    def _find_spec(name, *args, **kwargs):
        return None if name == "pypdf" else real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", _find_spec)
    assert main(["--no-color", "extract", str(pdf), "--out", str(tmp_path / "out"),
                 "--parameter", "porosity"]) == 3
    err = capsys.readouterr().err
    assert "E301" in err and "pypdf" in err
    assert "E199" not in err


# --- H6 -------------------------------------------------------------------
def test_quickstart_commands_reference_real_files_and_clean_init(tmp_path, capsys):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quickstart = (ROOT / "docs" / "QUICKSTART.md").read_text(encoding="utf-8")
    docs = readme + quickstart
    for stale in ("recovery_single.yaml", "recovery_multi.yaml", "configs/p3/",
                  "reports/gate.json", ".venv/bin/parallm"):
        assert stale not in docs, f"stale quick-start reference: {stale}"
    for rel in ("configs/p2/recovery_single_1C.yaml",
                "configs/p2/recovery_multi_0p5_1_2C.yaml",
                "configs/v2/target_lgm50.yaml",
                "data/registry/registry.json",
                "scripts/run_baseline.py"):
        assert rel in docs
        assert (ROOT / rel).exists(), f"missing documented path: {rel}"

    _init(tmp_path)
    workspace = tmp_path / "battery-research"
    for subdir in ("data/registry", "data/raw_documents", "results", "projects"):
        assert (workspace / subdir).is_dir()
    assert (tmp_path / "config.toml").is_file()
    assert main([*_config(tmp_path), "status"]) == 0
    capsys.readouterr()


# --- archived fixture must keep its genuine failure ------------------------
def test_archived_fixture_still_fails_its_unit_check(capsys):
    assert main(["--json", "validate", str(FIXTURE)]) == 1
    payload = _envelope(capsys)
    checks = {c["name"]: c["level"] for c in payload["data"]["results"][0]["checks"]}
    assert checks["physical_plausibility"] == "FAILED"
