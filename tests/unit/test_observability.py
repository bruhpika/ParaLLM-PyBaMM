"""Unit tests: observability join (V2.3) — P2 artifacts -> decisions."""

from __future__ import annotations

import json

from pybamm_closed_loop.assembly import (
    ObservabilityAssessment,
    Rubric,
    TargetSpecification,
    assemble,
    load_observability,
    not_assessed,
)
from pybamm_closed_loop.assembly.observability import (
    ACTION_CALIBRATE,
    ACTION_FIX,
    ACTION_MEASURE,
    BOOTSTRAP_REL_STD_OBSERVABILITY,
    SENSITIVITY_OBSERVABILITY_THRESHOLD,
)

TARGET = TargetSpecification(
    target_id="t",
    cell_product="LG M50",
    chemistry_families=("NMC", "graphite"),
    format="21700",
    temperature_k=298.15,
    soc="50%",
)

RECORDS = [
    {
        "canonical_id": "neg_particle_diffusivity",
        "definition": "D",
        "value": 3.3e-14,
        "value_unit": "m2.s-1",
        "normalized_value": 3.3e-14,
        "normalized_value_unit": "m2.s-1",
        "status": "CALIBRATED",
        "method": "tuned at 1C",
        "source_id": "doc1",
        "conditions": {"cell": "LG M50 21700", "chemistry": "NMC811 graphite",
                       "temperature_k": 298.15, "soc": "50%"},
        "evidence": {"source": {"document_id": "doc1", "locator": "Table VII",
                                "page": None, "quote": "D = 3.3e-14"}},
        "pybamm_names": ["Negative particle diffusivity [m2.s-1]"],
        "conflicts": [],
        "pybop_mapping": {"applicable": True, "notes": ""},
        "compatibility": {},
    },
    {
        "canonical_id": "neg_electrode_active_material_volume_fraction",
        "definition": "eps_s",
        "value": 0.75,
        "value_unit": "dimensionless",
        "normalized_value": 0.75,
        "normalized_value_unit": "dimensionless",
        "status": "LITERATURE_DERIVED",
        "method": "measured",
        "source_id": "doc1",
        "conditions": {"cell": "LG M50 21700", "chemistry": "NMC811 graphite",
                       "temperature_k": 298.15, "soc": "50%"},
        "evidence": {"source": {"document_id": "doc1", "locator": "Table II",
                                "page": None, "quote": "eps = 0.75"}},
        "pybamm_names": ["Negative electrode active material volume fraction"],
        "conflicts": [],
        "pybop_mapping": {"applicable": True, "notes": ""},
        "compatibility": {},
    },
]


def _p2_tree(tmp_path, sens: dict[str, float], boot_rel_std: float):
    """Minimal P2 artifact tree: sensitivity study + bootstrap study."""
    diff = tmp_path / "diffusivity_feasibility"
    diff.mkdir()
    name = "Negative particle diffusivity [m2.s-1]"
    per_condition = {
        cond: {"mean_abs_normalized_sensitivity": {name: value}}
        for cond, value in sens.items()
    }
    (diff / "report.json").write_text(
        json.dumps({"per_condition": per_condition})
    )
    ident = tmp_path / "identifiability_volume_fractions"
    ident.mkdir()
    vname = "Negative electrode active material volume fraction"
    mean = 0.75
    std = mean * boot_rel_std
    (ident / "report.json").write_text(
        json.dumps(
            {
                "bootstrap": {
                    "names": [vname],
                    "per_parameter": {
                        vname: {"mean": mean, "std": std, "truth": mean}
                    },
                },
                "fim_single": {"condition_number": 21.0},
                "fim_multi": {"condition_number": 35.0},
            }
        )
    )
    return tmp_path


def test_sensitivity_rule_classifies_and_actions(tmp_path):
    p2 = _p2_tree(
        tmp_path,
        {"0.5C": 0.011, "1C": 0.021, "2C": 0.048},  # P2 finding values
        boot_rel_std=0.007,
    )
    obs = load_observability(p2, RECORDS)
    d = obs["neg_particle_diffusivity"]
    assert d.status == "UNOBSERVABLE"
    assert d.action == ACTION_FIX
    assert set(d.protocols) == {"0.5C", "1C", "2C"}
    assert all(
        v < SENSITIVITY_OBSERVABILITY_THRESHOLD
        for v in d.metrics["mean_abs_normalized_sensitivity"].values()
    )
    assert d.rules_fired[0]["rule"] == "sensitivity_observability"
    v = obs["neg_electrode_active_material_volume_fraction"]
    assert v.status == "OBSERVABLE"
    assert v.action == ACTION_CALIBRATE
    assert v.metrics["bootstrap"]["rel_std"] <= BOOTSTRAP_REL_STD_OBSERVABILITY


def test_accuracy_critical_unobservable_becomes_measure(tmp_path):
    p2 = _p2_tree(
        tmp_path,
        {"0.5C": 0.011, "1C": 0.021, "2C": 0.048},
        boot_rel_std=0.007,
    )
    obs = load_observability(
        p2, RECORDS, accuracy_critical={"neg_particle_diffusivity"}
    )
    assert obs["neg_particle_diffusivity"].action == ACTION_MEASURE


def test_missing_artifacts_yield_no_assessments(tmp_path):
    assert load_observability(tmp_path, RECORDS) == {}


def test_not_assessed_filler_is_explicit():
    a = not_assessed("some_param", ["Some [m]"])
    assert a.status == "not_assessed"
    assert a.action is None
    field = a.to_dossier_field()
    assert field["status"] == "not_assessed"
    assert field["note"]


def test_assemble_upgrades_decisions_by_observability():
    obs = {
        "neg_particle_diffusivity": ObservabilityAssessment(
            canonical_id="neg_particle_diffusivity",
            pybamm_names=("Negative particle diffusivity [m2.s-1]",),
            status="UNOBSERVABLE",
            action=ACTION_FIX,
            protocols=("0.5C", "1C", "2C"),
            rules_fired=({"rule": "sensitivity_observability"},),
            note="unobservable",
        ),
        "neg_electrode_active_material_volume_fraction": ObservabilityAssessment(
            canonical_id="neg_electrode_active_material_volume_fraction",
            pybamm_names=("Negative electrode active material volume fraction",),
            status="OBSERVABLE",
            action=ACTION_CALIBRATE,
            protocols=("1C",),
            rules_fired=({"rule": "bootstrap_observability"},),
            note="observable",
        ),
    }
    report = assemble(RECORDS, TARGET, Rubric("rubric-v2"), observability=obs)
    by_id = {d["parameter"]: d for d in report.dossiers}
    d0 = by_id["neg_particle_diffusivity"]
    assert d0["decision"] == "FIX"
    assert d0["identifiability"]["status"] == "UNOBSERVABLE"
    assert any("observability" in r for r in d0["recommendation"]["rationale"])
    d1 = by_id["neg_electrode_active_material_volume_fraction"]
    assert d1["decision"] == "CALIBRATE"
    assert d1["identifiability"]["action"] == ACTION_CALIBRATE
    matrix = report.summary()["action_matrix"]
    assert matrix[ACTION_FIX] == 1
    assert matrix[ACTION_CALIBRATE] == 1
    assert matrix["not_assessed"] == 0


def test_assemble_without_observability_is_unchanged():
    report = assemble(RECORDS, TARGET, Rubric("rubric-v2"))
    for d in report.dossiers:
        assert d["identifiability"]["status"] == "not_assessed"
        assert d["decision"] in ("USE", "FIX")
    assert report.summary()["action_matrix"]["not_assessed"] == 2
