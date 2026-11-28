"""Integration test: assemble the real registry into dossiers (v0.2).

Uses the committed parameter registry (96 records, 7 preserved conflicts) and
the committed literature store. Deterministic; no network.
"""

from __future__ import annotations

import json
from pathlib import Path

from pybamm_closed_loop.assembly import (
    ApprovalGate,
    Rubric,
    TargetSpecification,
    assemble,
)
from pybamm_closed_loop.assembly.dossier import DOSSIER_FIELDS
from pybamm_closed_loop.assembly.gate import binding_sha256

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data/registry/registry.json"

TARGET = TargetSpecification(
    target_id="lgm50_chen2020_dfn",
    cell_product="LG M50",
    chemistry_families=("NMC", "graphite"),
    format="21700",
    temperature_k=298.15,
    soc="50%",
)


def _records() -> list[dict]:
    return json.loads(REGISTRY.read_text())


def _report():
    return assemble(_records(), TARGET, Rubric("rubric-v2"))


class TestAssemblyOverRealRegistry:
    def test_every_record_produces_a_dossier(self):
        records = _records()
        report = _report()
        assert len(report.dossiers) == len(records)

    def test_all_nine_fields_present_in_every_dossier(self):
        report = _report()
        for d in report.dossiers:
            for field in DOSSIER_FIELDS:
                assert field in d, f"{d['parameter']} missing {field}"

    def test_same_source_conflicts_adopt_the_operative_value(self):
        report = _report()
        conflicts = [d for d in report.dossiers if d["conflict"]]
        assert len(conflicts) == 7
        for d in conflicts:
            assert d["conflict_class"] == "same_source"
            assert d["selected"]["value"] is not None
            assert len(d["alternatives"]) == 1  # the alternative is preserved

    def test_bruggeman_conflict_keeps_the_measured_value_visible(self):
        report = _report()
        d = next(x for x in report.dossiers if x["parameter"] == "neg_bruggeman_electrolyte")
        assert d["selected"]["value"] == 1.5
        assert any(str(a["value"]) == "2.91" for a in d["alternatives"])

    def test_no_unapproved_parameter_is_exported(self):
        report = _report()
        gate = ApprovalGate()
        exported = report.pybamm_export(gate)
        assert exported == {}
        d = next(x for x in report.dossiers if x["parameter"] == "neg_bruggeman_electrolyte")
        gate.approve("neg_bruggeman_electrolyte", d["decision"], "owner",
                     d["rubric_version"], binding_sha256(d))
        exported = report.pybamm_export(gate)
        assert exported == {"neg_bruggeman_electrolyte": 1.5}

    def test_summary_is_consistent(self):
        summary = _report().summary()
        assert summary["n_parameters"] == 96
        assert summary["n_conflicts"] == 7
        assert summary["same_source_conflicts"] == 7
        assert sum(summary["decisions"].values()) == 96

    def test_markdown_renders(self):
        text = _report().to_markdown()
        assert "PARALLM parameter assembly" in text
        assert "neg_bruggeman_electrolyte" in text


def test_cli_over_real_registry(tmp_path):
    """The CLI runs over the real registry and its traceability gate is honest:
    every recorded quote verifies against the archive, and values carried
    without a quote or an explicit status flag are flagged as failures."""
    import pytest

    from pybamm_closed_loop.cli import main
    from pybamm_closed_loop.literature.availability import (
        ARTICLE_MISSING_REASON,
        article_source_text_available,
    )

    if not article_source_text_available():
        pytest.skip(f"SKIP: {ARTICLE_MISSING_REASON}")
    out = tmp_path / "out"
    rc = main(
        [
            "assemble",
            "--target", str(ROOT / "configs/v2/target_lgm50.yaml"),
            "--registry", str(REGISTRY),
            "--out", str(out),
            "--documents", str(ROOT / "data/raw_documents"),
        ]
    )
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["registry"]["n_records"] == 96
    assert manifest["documents"]["quote_verification"]["n_checked"] > 0
    assert manifest["documents"]["quote_verification"]["n_failed"] == 0
    report = json.loads((out / "report.json").read_text())
    levels = [t["level"] for t in report["traceability"]]
    assert len(levels) == 96
    assert rc == (1 if "fail" in levels else 0)
    for t in report["traceability"]:
        if t["level"] == "fail":
            assert any("explicit status flag" in m for m in t["messages"])


def test_p2_finding_reproduced_in_report():
    """V2.3 acceptance: the report reproduces the P2 finding — the negative
    particle diffusivity is unobservable under the studied protocols
    (0.5C/1C/2C) — and upgrades decisions via the observability join."""
    from pybamm_closed_loop.assembly import load_observability

    obs = load_observability(
        ROOT / "results/p2", _records(), accuracy_critical={"neg_particle_diffusivity"}
    )
    report = assemble(_records(), TARGET, Rubric("rubric-v2"), observability=obs)
    by_id = {d["parameter"]: d for d in report.dossiers}

    d = by_id["neg_particle_diffusivity"]
    ident = d["identifiability"]
    assert ident["status"] == "UNOBSERVABLE"
    assert set(ident["protocols"]) == {"0.5C", "1C", "2C"}
    sens = ident["metrics"]["mean_abs_normalized_sensitivity"]
    assert all(v < 0.05 for v in sens.values())
    assert "0.5C/1C/2C" in ident["note"]
    # accuracy-critical + unobservable -> MEASURE
    assert d["decision"] == "MEASURE"
    assert any("observability" in r for r in d["recommendation"]["rationale"])

    v = by_id["neg_electrode_active_material_volume_fraction"]
    assert v["identifiability"]["status"] == "OBSERVABLE"
    assert v["decision"] == "CALIBRATE"

    matrix = report.summary()["action_matrix"]
    # 7 parameters assessed: 6 observable (CALIBRATE), 1 accuracy-critical
    # unobservable (MEASURE); the rest are explicitly not_assessed
    assert matrix["MEASURE"] == 1
    assert matrix["CALIBRATE"] == 6
    assert matrix["not_assessed"] == 96 - 7
    text = report.to_markdown()
    assert "UNOBSERVABLE" in text and "CALIBRATE" in text
