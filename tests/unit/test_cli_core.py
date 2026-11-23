"""Unit tests for the core `parallm` commands and automation modes."""

from __future__ import annotations

import json

from pybamm_closed_loop import __version__
from pybamm_closed_loop.cli import main


def _config(tmp_path):
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path):
    return main([*_config(tmp_path), "init", "--workspace", str(tmp_path / "ws"), "--non-interactive"])


def test_version_is_fast_and_exact(capsys):
    assert main(["--version"]) == 0
    out = capsys.readouterr().out
    assert out.strip() == f"parallm {__version__}"


def test_help_lists_workflow_commands(capsys):
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    for name in ("doctor", "init", "status", "extract", "validate", "evidence", "explain", "assemble", "calibrate", "export"):
        assert name in out


def test_doctor_json_envelope(capsys):
    assert main(["--json", "doctor"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["command"] == "doctor"
    assert payload["status"] == "completed"
    components = {c["component"] for c in payload["data"]["checks"]}
    assert {"Python", "ParaLLM", "PyBaMM", "Configuration"}.issubset(components)
    assert all(c["status"] for c in payload["data"]["checks"])


def test_doctor_deep_reports_installed_parameter_sets_via_engine(capsys):
    assert main(["--json", "doctor", "--deep"]) == 0
    payload = json.loads(capsys.readouterr().out)
    check = next(c for c in payload["data"]["checks"] if c["component"] == "Parameter sets")
    assert check["status"] == "PASSED"
    assert "Chen2020 present" in check["detail"]


def test_init_creates_workspace_and_config(tmp_path):
    assert _init(tmp_path) == 0
    config = tmp_path / "config.toml"
    assert config.is_file()
    text = config.read_text(encoding="utf-8")
    assert "schema_version = 1" in text
    assert "[paths]" in text
    for subdir in ("data/registry", "data/raw_documents", "results", "projects"):
        assert (tmp_path / "ws" / subdir).is_dir()


def test_init_refuses_to_overwrite_without_force(tmp_path, capsys):
    assert _init(tmp_path) == 0
    assert _init(tmp_path) == 2
    assert "already exists" in capsys.readouterr().err


def test_status_requires_config(tmp_path, capsys):
    assert main([*_config(tmp_path), "--json", "status"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["code"] == "E104"


def test_status_after_init(tmp_path):
    assert _init(tmp_path) == 0
    assert main([*_config(tmp_path), "status"]) == 0


def test_project_create_list_inspect(tmp_path, capsys):
    assert _init(tmp_path) == 0
    assert main([*_config(tmp_path), "project", "create", "cell-a"]) == 0
    assert main([*_config(tmp_path), "project", "list"]) == 0
    assert main([*_config(tmp_path), "project", "inspect", "cell-a"]) == 0
    assert main([*_config(tmp_path), "project", "inspect", "missing"]) == 2
    assert (tmp_path / "ws" / "projects" / "cell-a" / "project.toml").is_file()


def test_quiet_mode_prints_only_compact_data(tmp_path, capsys):
    assert _init(tmp_path) == 0
    capsys.readouterr()
    assert main([*_config(tmp_path), "--quiet", "status"]) == 0
    out = capsys.readouterr().out
    assert "ParaLLM-PyBaMM" not in out
    assert "workspace=" in out
    assert "\n" not in out.strip()


def test_json_errors_are_structured(capsys):
    assert main(["--json", "project", "inspect", "nope"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["action"]
