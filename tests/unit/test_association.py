"""Unit tests for the deterministic association discipline (V2.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pybamm_closed_loop.eval.association import (
    AssociationScope,
    apply_association_discipline,
    association_support,
    build_scope,
    enforce_association,
    _protocol_supported,
    _strip_protocol_context,
)
from pybamm_closed_loop.eval.benchmark_v4 import (
    _context_slice,
    load_items,
    score_with_discipline,
)

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "data/private_v4/fixture/benchmark_v4.jsonl"
)

TABLE_EVIDENCE = (
    "Table VI. Overview of parameters that have been adjusted for the "
    "simulation. All parameters that are not included have not been changed.\n"
    "High energy (HE): INR21700 -50E High power (HP): INR21700 -30T\n"
    "Parameter Symbol Unit Experiment Simulation Experiment Simulation\n"
    "Diffusion coefficient of anode Dn m2 s-1 9.61e-15 1.30e-14 1.10e-13 "
    "1.74e-14\n"
    "Diffusion coefficient of cathode Dp m2 s-1 1.75e-16 1.03e-14 1.34e-14 "
    "1.45e-15\n"
    "Stoichiometry at 100% SOC (anode) xn - 0.9884 0.999 0.8792 0.89\n"
    "Max. lithium concentration (anode) cs,max,n mol l-1 37.309 31.695\n"
)


def _candidate(**overrides):
    cand = {
        "parameter_name": "negative electrode solid diffusivity",
        "value": 9.61e-15,
        "unit": "m2 s-1",
        "material": None,
        "temperature": None,
        "cell_config": None,
        "measurement_method": None,
        "context": None,
        "source": {"quote": None},
    }
    cand.update(overrides)
    return cand


class TestScope:
    def test_table_row_scope_excludes_other_rows(self):
        quote = "Stoichiometry at 100% SOC (anode) xn - 0.9884 0.999"
        scope = build_scope(TABLE_EVIDENCE, quote)
        assert scope.kind == "table_row"
        assert "0.9884" in scope.table_row
        # the neighbouring row's value must not be in the local scope
        assert "9.61e-15" not in scope.text
        assert "37.309" not in scope.text

    def test_table_scope_keeps_header_and_caption(self):
        quote = "Diffusion coefficient of anode Dn m2 s-1 9.61e-15 1.30e-14"
        scope = build_scope(TABLE_EVIDENCE, quote)
        assert scope.kind == "table_row"
        assert "Experiment" in scope.text  # header kept
        assert "INR21700" in scope.text  # caption kept

    def test_sentence_scope_excludes_distant_condition(self):
        evidence = (
            "The exchange current density was 0.38 mA cm-2 at 50% full cell "
            "SOC.\n\n"
            "The GITT protocol used C/10 current pulses for 30 min.\n"
        )
        quote = "0.38 mA cm-2 at 50% full cell"
        scope = build_scope(evidence, quote)
        assert scope.kind == "sentence"
        assert "50%" in scope.text
        # blank-line-separated sentence is not adjacent
        assert "C/10" not in scope.text

    def test_sentence_scope_includes_adjacent_condition_sentence(self):
        evidence = (
            "Measured at 50% full cell SOC.\n"
            "The diffusion coefficient was determined by GITT.\n"
        )
        quote = "determined by GITT"
        scope = build_scope(evidence, quote)
        assert "GITT" in scope.text

    def test_missing_quote_falls_back(self):
        scope = build_scope(TABLE_EVIDENCE, "not in the evidence at all")
        assert scope.kind == "fallback"
        assert scope.rules == ("quote_unavailable",)

    def test_global_setup_text(self):
        evidence = (
            "The value is 1.1 Ah.\n"
            "EXPERIMENT CONDITIONS (document-level statements):\n"
            "- All experiments were performed at 25 degC.\n"
            "- GITT was performed by applying C/10 current pulses for 30 min.\n"
        )
        scope = build_scope(evidence, "1.1 Ah")
        assert "25 degC" in scope.global_text
        assert "C/10" in scope.global_text

    def test_table_header_region_is_document_level(self):
        scope = build_scope(TABLE_EVIDENCE, "Stoichiometry at 100% SOC (anode) xn - 0.9884")
        assert "INR21700" in scope.global_text
        assert "High energy (HE)" in scope.global_text


class TestAssociationSupport:
    def test_column_label_method_rejected(self):
        scope = AssociationScope(
            text="Parameter Symbol Unit Experiment Simulation", kind="table_row",
            quote=None,
        )
        result = association_support(scope, "method", "Experiment")
        assert not result.supported
        assert result.rule == "column_label_not_method"

    def test_simulation_label_allowed(self):
        scope = AssociationScope(
            text="Parameter Unit Experiment Simulation", kind="table_row",
            quote=None,
        )
        result = association_support(scope, "method", "Simulation")
        assert result.supported

    def test_method_keyword_equivalence(self):
        scope = AssociationScope(text="the impedance spectra were fitted", kind="sentence", quote=None)
        result = association_support(scope, "method", "EIS")
        assert result.supported

    def test_unrecognised_method_rejected(self):
        scope = AssociationScope(text="postmortem techniques were used", kind="sentence", quote=None)
        result = association_support(scope, "method", "postmortem")
        assert not result.supported

    def test_soc_local_only(self):
        scope = AssociationScope(
            text="the value is 0.8792",
            kind="table_row",
            quote=None,
            global_text="All experiments were performed at 100% SOC.",
        )
        result = association_support(scope, "soc", "100")
        assert not result.supported
        assert result.scope == "local"

    def test_temperature_global_cue_fallback(self):
        scope = AssociationScope(
            text="the value is 0.8792",
            kind="table_row",
            quote=None,
            global_text="All experiments were performed at 25 degC.",
        )
        result = association_support(scope, "temperature_k", 298.15)
        assert result.supported
        assert result.scope == "document"
        assert result.rule == "global_cue"

    def test_cell_global_fallback_from_table_header(self):
        scope = AssociationScope(
            text="the value is 0.38 mA cm-2",
            kind="sentence",
            quote=None,
            global_text=(
                "High energy (HE): INR21700 -50E High power (HP): INR21700 -30T"
            ),
        )
        result = association_support(scope, "cell", "INR21700-50E")
        assert result.supported
        assert result.scope == "document"

    def test_temperature_all_stated_values_accepted(self):
        scope = AssociationScope(
            text="measured at 10, 25, and 40 degC", kind="sentence", quote=None
        )
        result = association_support(scope, "temperature_k", 298.15)
        assert result.supported

    def test_temperature_absent_rejected(self):
        scope = AssociationScope(
            text="the value is 1.1 Ah",
            kind="sentence",
            quote=None,
            global_text="Experiments were performed in a climate chamber.",
        )
        result = association_support(scope, "temperature_k", 298.15)
        assert not result.supported

    def test_protocol_global_requires_same_gitt_method(self):
        global_text = (
            "GITT was performed by applying C/10 current pulses for 30 min."
        )
        scope = AssociationScope(
            text="the activation energy is 25.3 kJ mol-1",
            kind="sentence",
            quote=None,
            global_text=global_text,
        )
        hit = association_support(scope, "protocol", "C/10", method="GITT")
        assert hit.supported
        assert hit.rule == "global_protocol_same_gitt_method"
        miss = association_support(scope, "protocol", "C/10", method="EIS")
        assert not miss.supported

    def test_protocol_numbers_must_match(self):
        scope = AssociationScope(
            text="GITT at C/10 current pulses", kind="sentence", quote=None
        )
        assert _protocol_supported(scope.text, "C/10")
        assert not _protocol_supported(scope.text, "C/20")

    def test_protocol_duration_required_when_stated(self):
        text = "applying C/10 current pulses for 30 min"
        assert _protocol_supported(text, "C/10+30 min")
        assert not _protocol_supported(text, "C/10+4 h")

    def test_fallback_scope_uses_trace_rules(self):
        scope = AssociationScope(
            text="the GITT protocol used C/10", kind="fallback", quote=None
        )
        result = association_support(scope, "protocol", "C/10")
        assert result.supported
        assert result.scope == "fallback"


class TestProtocolStripping:
    def test_strip_keeps_soc_statement(self):
        context = "SOC 50%, measured at 1C"
        cleaned = _strip_protocol_context(context)
        assert "50%" in cleaned
        assert _context_slice(cleaned, "protocol") is None

    def test_strip_reports_abstention(self):
        assert "not stated" in _strip_protocol_context("measured by EIS at 1C")

    def test_supported_protocol_kept(self):
        context = "measured by GITT at C/10 for 30 min"
        cand = _candidate(context=context, measurement_method="GITT")
        cleaned, removed, transcript = enforce_association(
            "The protocol was GITT at C/10 for 30 min. The value is 1.0.", cand
        )
        assert "protocol" not in removed
        assert _context_slice(cleaned["context"], "protocol") is not None


class TestEnforceAssociation:
    def test_invented_method_from_column_label_removed(self):
        cand = _candidate(
            measurement_method="Experiment",
            source={"quote": "Stoichiometry at 100% SOC (anode) xn - 0.9884"},
        )
        cleaned, removed, transcript = enforce_association(TABLE_EVIDENCE, cand)
        assert "method" in removed
        assert cleaned["measurement_method"] is None

    def test_supported_cell_config_kept(self):
        cand = _candidate(
            cell_config="INR21700-30T 21700",
            source={"quote": "Diffusion coefficient of cathode Dp m2 s-1 1.75e-16"},
        )
        cleaned, removed, transcript = enforce_association(TABLE_EVIDENCE, cand)
        assert "cell" not in removed
        assert "format" not in removed
        assert cleaned["cell_config"] is not None

    def test_both_cell_and_format_unsupported_removed(self):
        cand = _candidate(
            cell_config="18650 coin cell",
            source={"quote": "Diffusion coefficient of cathode Dp m2 s-1 1.75e-16"},
        )
        cleaned, removed, transcript = enforce_association(TABLE_EVIDENCE, cand)
        assert "cell" in removed
        assert "format" in removed
        assert cleaned["cell_config"] is None

    def test_unsupported_soc_removed_from_context(self):
        cand = _candidate(
            context="SOC 50%, the parameter was 0.9884",
            source={"quote": "Stoichiometry at 100% SOC (anode) xn - 0.9884"},
        )
        cleaned, removed, transcript = enforce_association(TABLE_EVIDENCE, cand)
        assert "soc" in removed
        assert _context_slice(cleaned["context"], "soc") is None

    def test_transcript_records_scope_and_rule(self):
        cand = _candidate(
            temperature=298.15,
            source={"quote": "Diffusion coefficient of anode Dn m2 s-1 9.61e-15"},
        )
        cleaned, removed, transcript = enforce_association(TABLE_EVIDENCE, cand)
        entry = {t["field"]: t for t in transcript}["temperature_k"]
        assert entry["supported"] is False
        assert entry["scope"] == "local"
        assert entry["removed"] is True


class TestApplyAssociationDiscipline:
    def test_stats(self):
        cand = _candidate(
            measurement_method="Experiment",
            source={"quote": "Diffusion coefficient of anode Dn m2 s-1 9.61e-15"},
        )
        cleaned, stats = apply_association_discipline(TABLE_EVIDENCE, [cand])
        assert stats["n_quote_not_in_evidence"] == 0
        assert stats["association_fallback_rate"] == 0.0
        assert stats["n_dropped_conditions"] >= 1
        assert "column_label_not_method" in stats["association_rule_counts"]
        assert cleaned[0]["_quote_in_evidence"] is True

    def test_unverified_quote_falls_back(self):
        cand = _candidate(source={"quote": "this quote does not exist anywhere"})
        cleaned, stats = apply_association_discipline(TABLE_EVIDENCE, [cand])
        assert stats["n_quote_not_in_evidence"] == 1
        assert stats["association_fallback_rate"] == 1.0
        assert cleaned[0]["_quote_in_evidence"] is False

    def test_empty_candidates(self):
        cleaned, stats = apply_association_discipline(TABLE_EVIDENCE, [])
        assert cleaned == []
        assert stats["quote_in_evidence_rate"] is None
        assert stats["association_fallback_rate"] is None

    def test_explicit_protocol_abstention_is_not_a_claim(self):
        cand = _candidate(
            context=(
                "SOC window, pulse current, pulse duration, rest time, "
                "C-rate, and cutoff voltages are not stated in the evidence."
            ),
            source={"quote": "Diffusion coefficient of anode Dn m2 s-1 9.61e-15"},
        )
        cleaned, stats = apply_association_discipline(TABLE_EVIDENCE, [cand])
        assert _context_slice(cleaned[0].get("context"), "protocol") is None
        assert "explicit_abstention" in stats["association_rule_counts"]

    def test_value_local_abstention_wins_over_document_level_gitt(self):
        cand = _candidate(
            context=(
                "SOC and cutoff voltages for this value are not stated in the "
                "evidence; document-level tests used GITT at C/10 but the link "
                "to this entry is not stated."
            ),
            source={"quote": "Diffusion coefficient of anode Dn m2 s-1 9.61e-15"},
        )
        cleaned, stats = apply_association_discipline(TABLE_EVIDENCE, [cand])
        assert _context_slice(cleaned[0].get("context"), "protocol") is None
        assert "explicit_abstention" in stats["association_rule_counts"]

    def test_stated_protocol_survives_a_partial_abstention(self):
        cand = _candidate(
            context="GITT at C/10 pulses; rest time not stated in the evidence.",
            source={"quote": "Diffusion coefficient of anode Dn m2 s-1 9.61e-15"},
        )
        cleaned, stats = apply_association_discipline(TABLE_EVIDENCE, [cand])
        # The existing local-scope rule strips this claim; our new abstention
        # rule must not be the reason (a real C/10 + GITT claim was present).
        assert _context_slice(cleaned[0].get("context"), "protocol") is None
        assert "explicit_abstention" not in stats["association_rule_counts"]


class TestScoreIntegration:
    def _items(self):
        try:
            return load_items(FIXTURE)
        except FileNotFoundError:
            pytest.skip("private v4 fixture not available")

    def test_discipline_dispatch(self):
        item = self._items()[0]
        row = score_with_discipline(
            item, "evidence", [], False, 0, discipline="association"
        )
        assert row["discipline"] == "association"

    def test_unknown_discipline_rejected(self):
        item = self._items()[0]
        with pytest.raises(ValueError):
            score_with_discipline(
                item, "evidence", [], False, 0, discipline="bogus"
            )

    def test_association_reduces_invented_method(self):
        item = self._items()[0]
        candidates = [
            _candidate(
                value=item.parameter["value"],
                measurement_method="Experiment",
                source={"quote": item.probe},
            )
        ]
        trace = score_with_discipline(
            item, item.probe, candidates, False, 0, discipline="trace"
        )
        assoc = score_with_discipline(
            item, item.probe, candidates, False, 0, discipline="association"
        )
        assert (
            len(assoc["invented_conditions"]) <= len(trace["invented_conditions"])
        )
