"""Step 2 regressions: dimensionless and function-valued exports.

Only a clearly labelled fake approver is used; no data/ or results/ edits and
no live model calls.
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


def _all_approved_assembly(tmp_path: Path, out: str = "assembly") -> Path:
    first = tmp_path / f"{out}_first"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(REGISTRY), "--out", str(first)]) == 0
    pending = json.loads((first / "gate.pending.json").read_text(encoding="utf-8"))
    for entry in pending["approvals"]:
        entry.update(approved=True, approver="FAKE-APPROVER",
                     timestamp="2026-11-28T00:00:00Z", note="SYNTHETIC fake approval")
    gate = tmp_path / f"{out}_gate.json"
    gate.write_text(json.dumps({"approvals": pending["approvals"]}), encoding="utf-8")
    final = tmp_path / out
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(REGISTRY), "--out", str(final),
                 "--gate", str(gate)]) == 0
    return final


def test_dimensionless_parameters_export_to_pybamm(tmp_path):
    """A PyBaMM name without a bracketed unit is dimensionless, not an error."""
    _init(tmp_path)
    source = _all_approved_assembly(tmp_path)
    out = tmp_path / "params.py"
    assert main([*_config(tmp_path), "--quiet", "export", "--format", "pybamm",
                 "--from", str(source), "--output", str(out)]) == 0
    exported = out.read_text(encoding="utf-8")
    for name in ("Negative electrode porosity", "Cation transference number",
                 "Thermodynamic factor", "Negative electrode Bruggeman coefficient (electrode)"):
        assert name in exported, name


def test_function_valued_parameters_in_pybamm_export(tmp_path):
    """Function names survive in pybamm_export.json as in the previous commit."""
    _init(tmp_path)
    source = _all_approved_assembly(tmp_path, out="assembly_functions")
    exported = json.loads((source / "pybamm_export.json").read_text(encoding="utf-8"))
    for name in ("neg_electrode_ocp", "pos_electrode_ocp", "electrolyte_conductivity"):
        assert name in exported, name
        assert isinstance(exported[name], str) and exported[name], (name, exported[name])


def test_dimensionless_unit_mismatch_still_refused(tmp_path):
    """A non-dimensionless unit is refused for a dimensionless PyBaMM name."""
    _init(tmp_path)
    source = tmp_path / "assembly"
    source.mkdir()
    (source / "pybamm_export.json").write_text(
        json.dumps({"neg_electrode_porosity": {"value": 0.25, "unit": "m",
                    "pybamm_names": ["Negative electrode porosity"]}}),
        encoding="utf-8",
    )
    out = tmp_path / "params.py"
    assert main([*_config(tmp_path), "--quiet", "export", "--format", "pybamm",
                 "--from", str(source), "--output", str(out)]) == 2
    assert not out.exists()
