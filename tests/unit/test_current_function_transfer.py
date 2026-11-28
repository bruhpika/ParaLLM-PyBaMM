"""Step 4: LG M50 current must not transfer to the LFP target.

`current_function` is a cell/protocol-specific current profile. The same
value on the LG M50 target is unchanged; on the LFP target it must escalate
to REVIEW. Graphite/graphite-SiOx matching is deliberately not changed here.
"""

from __future__ import annotations

import json
from pathlib import Path

from pybamm_closed_loop.assembly import Rubric, assemble
from pybamm_closed_loop.assembly.lexicon import is_cell_specific
from pybamm_closed_loop.cli_app.inputs import read_target

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data" / "registry" / "registry.json"
NMC = ROOT / "configs" / "v2" / "target_lgm50.yaml"
LFP = ROOT / "configs" / "v3" / "target_lfp_graphite_prada2013.yaml"


def _assemble(target: Path, version: str = "rubric-v5"):
    return assemble(
        json.loads(REGISTRY.read_text(encoding="utf-8")),
        read_target(target.resolve()), Rubric(version),
    )


def test_current_function_is_cell_specific():
    assert is_cell_specific("current_function")


def test_current_function_review_for_lfp_unchanged_for_nmc():
    nmc = {d["parameter"]: d for d in _assemble(NMC).dossiers}
    lfp = {d["parameter"]: d for d in _assemble(LFP).dossiers}
    assert nmc["current_function"]["decision"] == "USE"
    assert lfp["current_function"]["decision"] == "REVIEW"


def test_decision_counts_for_both_targets():
    """Counts are recorded so a rubric change is visible, not hidden."""
    nmc = _assemble(NMC)
    lfp = _assemble(LFP)
    assert nmc.summary()["decisions"] == {"FIX": 19, "REVIEW": 52, "USE": 25}
    assert lfp.summary()["decisions"] == {"FIX": 14, "REJECT": 9, "REVIEW": 66, "USE": 7}


def test_rubric_version_bumped_for_transfer_change():
    assert Rubric("rubric-v5").require_stated_transfer_match is True
