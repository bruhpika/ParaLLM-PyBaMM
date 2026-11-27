"""Integration test: v0.3 artifact names/values vs pinned installed PyBaMM.

This exercises the real introspection path in ``pybamm_engine`` against the
installed PyBaMM 26.8.0.0. No name or value is assumed from another version and
no parameter set is registered or modified.
"""

from __future__ import annotations

import json
from pathlib import Path

from pybamm_closed_loop.pybamm_engine import (
    installed_pybamm_version,
    installed_scalar_values,
    verify_parameter_names,
)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "results/v03/param_set/parallm_chen2020_ext.json"


def test_all_artifact_names_exist_in_installed_chen2020():
    artifact = json.loads(ARTIFACT.read_text())
    names = [name for f in artifact["parameters"] for name in f["pybamm_names"]]
    assert installed_pybamm_version() == "26.8.0.0"
    result = verify_parameter_names(names, "Chen2020")
    assert result["all_present"] is True
    assert result["missing"] == []
    assert result["n_requested"] == 27
    assert result["pybamm_version"] == "26.8.0.0"


def test_all_copied_values_match_installed_defaults():
    artifact = json.loads(ARTIFACT.read_text())
    installed = installed_scalar_values("Chen2020")
    for field in artifact["parameters"]:
        for name in field["pybamm_names"]:
            assert name in installed
            assert installed[name] == field["operative"]["value"]


def test_builder_end_to_end_into_temporary_output(tmp_path: Path):
    """Run the real script with pinned PyBaMM; writes only under tmp_path."""
    import importlib.util

    script = ROOT / "scripts/v03/build_param_set.py"
    spec = importlib.util.spec_from_file_location("build_param_set_v03_e2e", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--out-dir", str(tmp_path)]) == 0
    artifact_path = tmp_path / "results/v03/param_set/parallm_chen2020_ext.json"
    produced = json.loads(artifact_path.read_text())
    committed = json.loads(ARTIFACT.read_text())
    assert produced["content_sha256"] == committed["content_sha256"]
    assert produced["parameters"] == committed["parameters"]
    assert (tmp_path / "results/v03/param_set/manifest.json").is_file()
