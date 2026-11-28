"""PHASE 2: decision-rubric trust fixes.

Failing tests written before the implementation. No live LLM, no network.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from pybamm_closed_loop.assembly import (
    CandidateValue,
    Decision,
    MethodClass,
    ObservabilityAssessment,
    Rubric,
    TargetSpecification,
    assemble,
    resolve_parameter,
)
from pybamm_closed_loop.assembly.observability import (
    ACTION_CALIBRATE,
    STATUS_OBSERVABLE,
)

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data/registry/registry.json"
LFP_TARGET_CONFIG = ROOT / "configs/v3/target_lfp_graphite_prada2013.yaml"

LG_M50 = TargetSpecification(
    target_id="lgm50_chen2020_dfn",
    cell_product="LG M50",
    chemistry_families=("NMC", "graphite"),
    format="21700",
    temperature_k=298.15,
    soc="50%",
    parameter_set="Chen2020",
)


def _records() -> list[dict]:
    return json.loads(REGISTRY.read_text())


def _report(target=LG_M50, version="rubric-v2", observability=None):
    return assemble(copy.deepcopy(_records()), target, Rubric(version),
                    observability=observability)


def _chem_specific_ids() -> set[str]:
    """The list approved by the project owner (22 electrode/SEI parameters)."""
    return {
        "pos_electrode_ocp", "pos_entropic_change", "pos_exchange_current_density",
        "pos_particle_diffusivity", "pos_particle_radius", "pos_bruggeman_electrode",
        "positive_electrode_density", "positive_electrode_double_layer_capacity",
        "positive_electrode_reaction_driven_lam_factor",
        "neg_electrode_ocp", "neg_entropic_change", "neg_exchange_current_density",
        "neg_particle_diffusivity", "neg_particle_radius", "neg_bruggeman_electrode",
        "negative_electrode_density", "negative_electrode_double_layer_capacity",
        "negative_electrode_reaction_driven_lam_factor",
        "sei_open_circuit_potential", "sei_reaction_exchange_current_density",
        "sei_lithium_interstitial_diffusivity", "sei_solvent_diffusivity",
    }


class TestPhase2Bugs:
    def test_2a_selected_unresolved_is_review(self):
        """A selected UNRESOLVED value must go to REVIEW, never FIX."""
        report = _report()
        unresolved_ids = {r["canonical_id"] for r in _records()
                          if r.get("status") == "UNRESOLVED"}
        decisions = {d["parameter"]: d["decision"] for d in report.dossiers}
        selected_unresolved = [
            d for d in report.dossiers
            if d["parameter"] in unresolved_ids and d.get("selected", {}).get("value") is not None
        ]
        assert selected_unresolved, "expected selected UNRESOLVED values"
        for d in selected_unresolved:
            assert decisions[d["parameter"]] == "REVIEW", (
                f"{d['parameter']}: UNRESOLVED selected value was not escalated"
            )

    def test_2b_no_credit_for_unstated_conditions(self):
        """Unstated temperature/SOC/format must not earn target-match credit."""
        from pybamm_closed_loop.assembly.schema import CandidateValue

        cand = CandidateValue(canonical_id="neg_particle_radius", value=1.0, unit="m",
                              method_class=MethodClass.MEASURED)
        rubric = Rubric("rubric-v2")
        outcome = rubric.evaluate(cand, LG_M50)
        # No conditions stated => no dimension may score a full "match".
        for dim in ("temperature", "soc", "format", "cell_product", "electrolyte"):
            assert outcome.dimension_scores[dim] < 1.0, dim
            rule = next(f for f in outcome.fired if f["dimension"] == dim)
            assert rule["score"] < 1.0, dim

    def test_2c_lfp_target_decision_counts(self):
        """The v3 LFP target must not silently adopt NMC-cell defaults."""
        from pybamm_closed_loop.cli_app.inputs import read_target

        target = read_target(LFP_TARGET_CONFIG)
        report = _report(target)
        counts: dict[str, int] = {}
        for d in report.dossiers:
            counts[d["decision"]] = counts.get(d["decision"], 0) + 1
        assert counts.get("USE", 0) < 25 or counts.get("CALIBRATE", 0) >= 4
        # A cathode parameter measured on an NMC cell cannot be adopted for an
        # LFP cathode. Anode parameters measured on graphite may legitimately
        # transfer to another graphite anode, so only cathode values are
        # required to escalate here.
        cathode_ids = [c for c in _chem_specific_ids()
                       if c.startswith(("pos_", "positive_"))]
        for cid in sorted(cathode_ids):
            d = next(x for x in report.dossiers if x["parameter"] == cid)
            assert d["decision"] in ("REVIEW", "REJECT"), (
                f"{cid}: NMC-cathode value adopted for an LFP target"
            )

    def test_2d_unknown_chemistry_specific_is_review(self):
        cand = CandidateValue(canonical_id="pos_electrode_ocp", value=3.0, unit="V",
                              method_class=MethodClass.MEASURED,
                              quote="123", quote_verified=True, source_locator="Table I")
        rubric = Rubric("rubric-v2")
        res = resolve_parameter("pos_electrode_ocp", [cand], LG_M50, rubric)
        assert res.decision is Decision.REVIEW

    def test_2e_mismatched_chemistry_is_reject(self):
        from pybamm_closed_loop.assembly.schema import ConditionFacts

        cand = CandidateValue(canonical_id="pos_electrode_ocp", value=3.0, unit="V",
                              method_class=MethodClass.MEASURED,
                              conditions=ConditionFacts.from_mapping({"chemistry": "LFP"}))
        rubric = Rubric("rubric-v2")
        res = resolve_parameter("pos_electrode_ocp", [cand], LG_M50, rubric)
        assert res.decision is Decision.REJECT

    def test_2f_observability_never_upgrades_review_or_reject(self):
        from pybamm_closed_loop.assembly.report import _apply_observability_upgrade

        d = {"parameter": "p", "decision": "REVIEW",
             "recommendation": {"decision": "REVIEW", "rationale": [], "next_step": ""}}
        res = resolve_parameter("p", [], LG_M50, Rubric("rubric-v2"))
        assess = ObservabilityAssessment(
            canonical_id="p", pybamm_names=(), status=STATUS_OBSERVABLE,
            action=ACTION_CALIBRATE, protocols=("1C",))
        _apply_observability_upgrade(d, res, assess)
        assert d["decision"] == "REVIEW"

    def test_2g_observability_not_applied_across_cells(self):
        """Results recorded for a Chen2020 cell cannot upgrade LFP decisions."""
        from pybamm_closed_loop.cli_app.inputs import read_target
        from pybamm_closed_loop.assembly.observability import load_observability

        target = read_target(LFP_TARGET_CONFIG)
        records = _records()
        obs = load_observability(ROOT / "results/p2", records, set())
        assert obs, "expected recorded P2 assessments for the LG M50/Chen2020 cell"
        assert all(a.parameter_set == "Chen2020" for a in obs.values()), (
            "recorded P2 artifacts must declare their source parameter set"
        )
        # The LFP assembly must not carry those Chen2020 assessments into any
        # dossier field or observability-driven decision.
        report = _report(target, observability=obs)
        for d in report.dossiers:
            ident = d.get("identifiability") or {}
            if ident.get("status") not in (None, "not_assessed"):
                assert d["parameter"] not in obs, (
                    f"{d['parameter']}: Chen2020 assessment leaked into LFP target"
                )
