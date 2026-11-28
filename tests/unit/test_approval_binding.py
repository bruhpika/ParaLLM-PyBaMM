"""PHASE 1: approvals must be bound to the exact decision they approve.

These tests reproduce the three trust bugs reported in the Phase 1 brief:
(a) an approval keyed only by parameter name survives a value change,
(b) an approval with decision REJECT / a made-up rubric version is accepted,
(c) ``AssemblyReport.pybamm_export()`` with no gate exports everything.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pybamm_closed_loop.assembly import (
    ApprovalGate,
    GateValidationError,
    Rubric,
    TargetSpecification,
    assemble,
)
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


def _report(records=None):
    return assemble(copy.deepcopy(records or _records()), TARGET, Rubric("rubric-v2"))


def _dossier(report, parameter="cell_electrode_width"):
    return next(d for d in report.dossiers if d["parameter"] == parameter)


def _approved_gate(report, parameter="cell_electrode_width"):
    d = _dossier(report, parameter)
    gate = ApprovalGate()
    gate.approve(
        parameter, d["decision"], "owner", d["rubric_version"],
        binding_sha256(d),
    )
    return gate


class TestPhase1Reproductions:
    def test_1a_changed_value_is_not_exported_by_old_gate(self):
        """A value changed in the registry invalidates the old approval."""
        report = _report()
        gate = _approved_gate(report)
        assert report.pybamm_export(gate).get("cell_electrode_width") is not None

        mutated = _records()
        for record in mutated:
            if record.get("canonical_id") == "cell_electrode_width":
                record["value"] = 999
                record["normalized_value"] = 999
        stale_report = _report(mutated)
        exported = stale_report.pybamm_export(gate)
        assert "cell_electrode_width" not in exported

    def test_1b_reject_decision_with_bogus_rubric_cannot_approve(self):
        """REJECT + made-up rubric version must not be usable as an approval."""
        report = _report()
        gate = ApprovalGate()
        with pytest.raises(GateValidationError, match="REJECT"):
            gate.approve(
                "cell_electrode_width", "REJECT", "owner", "rubric-v999-nonexistent",
                binding_sha256(_dossier(report)),
            )
        assert not gate.is_approved("cell_electrode_width")
        assert "cell_electrode_width" not in report.pybamm_export(gate)

    def test_1b_reject_flag_still_blocks_export(self):
        """An explicit rejection never exports, regardless of other fields."""
        report = _report()
        gate = ApprovalGate()
        gate.reject(
            "cell_electrode_width", "FIX", "owner", "rubric-v2",
            binding_sha256(_dossier(report)),
        )
        assert not gate.is_approved("cell_electrode_width")
        assert "cell_electrode_width" not in report.pybamm_export(gate)

    def test_1c_no_gate_exports_nothing(self):
        report = _report()
        assert report.pybamm_export() == {}

    def test_missing_binding_is_rejected_with_clear_message(self):
        """Old gate files fail loudly; they are never silently upgraded."""
        payload = {
            "approvals": [{
                "parameter": "cell_electrode_width",
                "decision": "FIX",
                "approved": True,
                "approver": "owner",
                "rubric_version": "rubric-v2",
                "timestamp": "2026-01-01T00:00:00Z",
                "note": "legacy gate",
            }]
        }
        with pytest.raises(GateValidationError, match="binding_sha256"):
            ApprovalGate.from_dict(payload)

    def test_wrong_rubric_version_blocks_parameter(self):
        report = _report()
        d = _dossier(report)
        gate = ApprovalGate()
        gate.approve(
            "cell_electrode_width", d["decision"], "owner", "rubric-v999",
            binding_sha256(d),
        )
        assert "cell_electrode_width" not in report.pybamm_export(gate)

    def test_wrong_decision_blocks_parameter(self):
        report = _report()
        d = _dossier(report)
        gate = ApprovalGate()
        gate.approve(
            "cell_electrode_width", "USE", "owner", d["rubric_version"],
            binding_sha256(d),
        )
        if d["decision"] != "USE":
            assert "cell_electrode_width" not in report.pybamm_export(gate)

    def test_mismatches_are_reported_with_reasons(self):
        report = _report()
        d = _dossier(report)
        gate = ApprovalGate()
        gate.approve(
            "cell_electrode_width", d["decision"], "owner", "rubric-v999",
            binding_sha256(d),
        )
        result = report.pybamm_export(gate, with_reasons=True)
        assert "cell_electrode_width" not in result["parameters"]
        reason = result["blocked"].get("cell_electrode_width", "")
        assert "cell_electrode_width" in reason and "rubric" in reason

    def test_roundtrip_preserves_binding(self):
        report = _report()
        gate = _approved_gate(report)
        restored = ApprovalGate.from_dict(gate.to_dict())
        assert report.pybamm_export(restored) == report.pybamm_export(gate)
