"""Phase 4 regression: rubric-v4 stops NMC values being used for LFP.

The review found that six positive-electrode parameters were adopted as USE
for an LFP target from the NMC LG M50 cell, and that PyBaMM-default records
were given the demonstrator's cell/chemistry/temperature conditions even
though no source states them. Weights are not tuned here; only classification
and the decision path change.
"""

from __future__ import annotations

import json
from pathlib import Path

from pybamm_closed_loop.assembly import Rubric, assemble
from pybamm_closed_loop.assembly.lexicon import (
    is_cell_specific, is_chemistry_specific,
)
from pybamm_closed_loop.cli_app.inputs import read_target

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data" / "registry" / "registry.json"
NMC_TARGET = ROOT / "configs" / "v2" / "target_lgm50.yaml"
LFP_TARGET = ROOT / "configs" / "v3" / "target_lfp_graphite_prada2013.yaml"
SIX = (
    "pos_electrode_porosity", "pos_electrode_thickness",
    "pos_electrode_conductivity", "pos_electrode_active_material_volume_fraction",
    "pos_initial_concentration", "pos_current_collector_thickness",
)


def _records() -> list[dict]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _decisions(target: Path, version: str) -> dict[str, str]:
    report = assemble(_records(), read_target(target.resolve()), Rubric(version))
    return {d["parameter"]: d["decision"] for d in report.dossiers}


def test_six_parameters_are_classified_as_cell_or_chemistry_specific():
    """All six mis-used parameters must be in a specific class."""
    for name in SIX:
        assert is_cell_specific(name) or is_chemistry_specific(name), name
    assert is_cell_specific("cell_electrode_width")
    assert is_cell_specific("cell_electrode_height")
    assert is_chemistry_specific("pos_max_concentration")
    assert is_chemistry_specific("neg_activation_energy")


def test_lfp_no_longer_uses_the_nmc_values():
    """rubric-v4 escalates the six NMC values to REVIEW for the LFP target."""
    decisions = _decisions(LFP_TARGET, "rubric-v4")
    for name in SIX:
        assert decisions[name] == "REVIEW", (name, decisions[name])


def test_nmc_target_still_uses_stated_lg_m50_values():
    """A stated target match still allows USE on the demonstrator's own cell."""
    decisions = _decisions(NMC_TARGET, "rubric-v4")
    for name in SIX:
        if name == "pos_initial_concentration":
            # Chemistry was never stated for this default: REVIEW is correct.
            assert decisions[name] == "REVIEW"
        else:
            assert decisions[name] == "USE", (name, decisions[name])


def test_rubric_version_bumped_and_weights_unchanged():
    from pybamm_closed_loop.assembly.rubric import DEFAULT_WEIGHTS

    assert DEFAULT_WEIGHTS == {
        "chemistry": 0.22, "temperature": 0.12, "method": 0.16,
        "evidence": 0.12, "soc": 0.08, "format": 0.04, "agreement": 0.04,
        "model": 0.05, "cell_product": 0.12, "electrolyte": 0.05,
    }
    rubric = Rubric("rubric-v4")
    assert rubric.require_stated_transfer_match is True
    assert Rubric("rubric-v3").require_stated_transfer_match is False


def test_pybamm_defaults_have_no_unstated_conditions():
    """A default with no source may not inherit cell/chemistry/temperature.

    Regenerate records from the read-only registry values and archived text;
    the committed registry itself is never edited by this test.
    """
    from pybamm_closed_loop.registry.seed import build_records

    params: dict[str, object] = {}
    for record in _records():
        for name in record.get("pybamm_names") or []:
            value = record.get("value")
            params[name] = value if isinstance(value, (int, float)) else 0.0
    text = (
        ROOT / "data" / "raw_documents" / "chen2020_jes_167_080534"
        / "chen2020_jes_167_080534_fulltext.txt"
    ).read_text(encoding="utf-8")
    built = build_records(params, text)
    defaults = [
        r for r in built if str(r.source_id).startswith("pybamm-")
    ]
    assert defaults, "expected PyBaMM-default records"
    for record in defaults:
        conditions = dict(record.conditions or {})
        assert not conditions.get("cell"), (record.canonical_id, conditions)
        assert not conditions.get("chemistry"), (record.canonical_id, conditions)
        assert conditions.get("temperature_k") is None, (record.canonical_id, conditions)


def test_before_after_tables():
    """Document the behaviour change for both targets."""
    before_nmc = _decisions(NMC_TARGET, "rubric-v3")
    before_lfp = _decisions(LFP_TARGET, "rubric-v3")
    after_nmc = _decisions(NMC_TARGET, "rubric-v4")
    after_lfp = _decisions(LFP_TARGET, "rubric-v4")
    assert {p: before_nmc[p] for p in SIX} == {
        "pos_electrode_porosity": "USE", "pos_electrode_thickness": "USE",
        "pos_electrode_conductivity": "USE",
        "pos_electrode_active_material_volume_fraction": "USE",
        "pos_initial_concentration": "REVIEW",
        "pos_current_collector_thickness": "USE",
    }
    # The original rubric-v3 gave USE for all six on LFP; after adding the
    # chemistry classification, pos_initial_concentration is already REVIEW
    # under v3 because no chemistry was stated for that default.
    assert all(before_lfp[p] == "USE" for p in SIX if p != "pos_initial_concentration")
    assert before_lfp["pos_initial_concentration"] == "REVIEW"
    assert all(after_lfp[p] == "REVIEW" for p in SIX)
    assert {p: after_nmc[p] for p in SIX} == {p: before_nmc[p] for p in SIX}
