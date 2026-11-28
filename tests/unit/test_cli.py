"""Unit tests: parallm assemble CLI + dossier traceability (V2.2)."""

from __future__ import annotations

import json

import pytest

from pybamm_closed_loop.assembly.dossier import check_traceability
from pybamm_closed_loop.cli import load_target, main

from tests._gate_helpers import binding_for_record

TARGET_YAML = """\
target:
  target_id: lgm50_test
  cell_product: LG M50
  chemistry_families: [NMC, graphite]
  format: "21700"
  temperature_k: 298.15
  soc: "50%"
  model: DFN
  parameter_set: Chen2020
"""

DOC_ID = "minidoc"
QUOTE = "the mean particle radius is 5.86 um by SEM"


def _record(
    canonical_id: str = "neg_particle_radius",
    quote: str = QUOTE,
    status: str = "LITERATURE_DERIVED",
    value: float = 5.86e-6,
) -> dict:
    return {
        "canonical_id": canonical_id,
        "definition": "negative particle radius",
        "value": value,
        "value_unit": "m",
        "normalized_value": value,
        "normalized_value_unit": "m",
        "status": status,
        "method": "SEM measurement",
        "source_id": DOC_ID,
        "conditions": {
            "cell": "LG M50 21700",
            "chemistry": "NMC811 graphite",
            "temperature_k": 298.15,
            "soc": "50%",
        },
        "evidence": {
            "source": {
                "document_id": DOC_ID,
                "locator": "Table II",
                "page": None,
                "quote": quote,
            }
        },
        "conflicts": [],
        "pybop_mapping": {"applicable": True, "notes": ""},
        "compatibility": {},
    }


def _write_inputs(tmp_path, records: list[dict] | None = None):
    target = tmp_path / "target.yaml"
    target.write_text(TARGET_YAML)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps(records if records is not None else [_record()]))
    docs = tmp_path / "documents"
    (docs / DOC_ID).mkdir(parents=True)
    (docs / DOC_ID / f"{DOC_ID}_fulltext.txt").write_text(
        f"Table II. Geometrical measurements. {QUOTE}. End of table."
    )
    return target, registry, docs, tmp_path / "out"


def _run(target, registry, docs, out, *extra: str) -> int:
    return main(
        [
            "assemble",
            "--target", str(target),
            "--registry", str(registry),
            "--out", str(out),
            "--documents", str(docs),
            *extra,
        ]
    )


def test_assemble_writes_all_outputs(tmp_path):
    rc = _run(*_write_inputs(tmp_path))
    assert rc == 0
    out = tmp_path / "out"
    for name in ("report.json", "report.md", "pybamm_export.json", "manifest.json"):
        assert (out / name).exists(), name
    report = json.loads((out / "report.json").read_text())
    assert report["summary"]["n_parameters"] == 1
    assert len(report["parameters"]) == 1
    assert report["traceability"][0]["level"] == "ok"
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["rubric_version"] == "rubric-v3"
    assert manifest["registry"]["n_records"] == 1
    assert manifest["registry"]["sha256"]
    assert manifest["documents"]["quote_verification"]["n_verified"] == 1
    assert manifest["n_exported"] == 0  # no gate -> empty export (D6)
    assert json.loads((out / "pybamm_export.json").read_text()) == {}


def test_export_contains_only_approved_parameters(tmp_path):
    target, registry, docs, out = _write_inputs(tmp_path)
    gate = tmp_path / "gate.json"
    gate.write_text(
        json.dumps(
            {
                "approvals": [
                    {
                        "parameter": "neg_particle_radius",
                        "decision": "USE",
                        "approved": True,
                        "approver": "owner",
                        "rubric_version": "rubric-v3",
                        "binding_sha256": binding_for_record(_record()),
                    },
                    {
                        "parameter": "not_in_registry",
                        "decision": "USE",
                        "approved": True,
                        "approver": "owner",
                        "rubric_version": "rubric-v3",
                        "binding_sha256": "0" * 64,
                    },
                ]
            }
        )
    )
    rc = _run(target, registry, docs, out, "--gate", str(gate))
    assert rc == 0
    exported = json.loads((out / "pybamm_export.json").read_text())
    assert set(exported) == {"neg_particle_radius"}
    assert exported["neg_particle_radius"] == pytest.approx(5.86e-6)


def test_failed_quote_is_rejected_not_carried(tmp_path):
    rec = _record(quote="a quote that appears nowhere in the document")
    target, registry, docs, out = _write_inputs(tmp_path, records=[rec])
    rc = _run(target, registry, docs, out)
    # the fabrication is caught and nothing is carried: the decision is
    # REVIEW (no usable value), and the failed verification is visible
    assert rc == 0
    report = json.loads((out / "report.json").read_text())
    param = report["parameters"][0]
    assert param["decision"] == "REVIEW"
    assert param["selected"]["value"] is None
    assert "could not be verified" in json.dumps(report)
    assert report["traceability"][0]["level"] == "ok"


def test_unchecked_quote_warns_but_passes(tmp_path):
    target, registry, docs, out = _write_inputs(tmp_path)
    rc = main(
        [
            "assemble",
            "--target", str(target),
            "--registry", str(registry),
            "--out", str(out),
        ]
    )
    assert rc == 0
    report = json.loads((out / "report.json").read_text())
    trace = report["traceability"][0]
    assert trace["level"] == "warn"
    assert any("not re-verified" in m for m in trace["messages"])
    assert report["parameters"][0]["evidence"]["quote_verified"] is None


def test_explicit_status_flag_without_quote_passes(tmp_path):
    rec = _record(quote="", status="CALCULATED")
    rec["evidence"]["source"] = {}
    target, registry, docs, out = _write_inputs(tmp_path, records=[rec])
    rc = _run(target, registry, docs, out)
    assert rc == 0
    assert json.loads((out / "report.json").read_text())["traceability"][0]["level"] == "ok"


def test_check_traceability_missing_fields_fails():
    level, messages = check_traceability({"parameter": "x"})
    assert level == "fail"
    assert any("missing dossier fields" in m for m in messages)


def test_check_traceability_flags_silent_values():
    d = {
        "parameter": "x",
        "selected": {"value": 1.0, "unit": "m"},
        "literature_value": {"status": "LITERATURE_DERIVED"},
        "evidence": {"quote_present": False, "quote_verified": None},
        "conditions": {},
        "alternatives": [],
        "rejected": [],
        "applicability": {},
        "identifiability": {"status": "not_assessed"},
        "recommendation": {"rationale": ["r"]},
        "approval": {"status": "pending"},
    }
    level, messages = check_traceability(d)
    assert level == "fail"
    assert any("no quote and no explicit status flag" in m for m in messages)


def test_check_traceability_flags_failed_verification():
    d = {
        "parameter": "x",
        "selected": {"value": 1.0, "unit": "m"},
        "literature_value": {"status": "LITERATURE_DERIVED"},
        "evidence": {"quote_present": True, "quote_verified": False},
        "conditions": {},
        "alternatives": [],
        "rejected": [],
        "applicability": {},
        "identifiability": {"status": "not_assessed"},
        "recommendation": {"rationale": ["r"]},
        "approval": {"status": "pending"},
    }
    level, messages = check_traceability(d)
    assert level == "fail"
    assert any("failed quote verification" in m for m in messages)


def test_load_target_requires_keys(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("target:\n  target_id: x\n")
    with pytest.raises(SystemExit, match="missing required key"):
        load_target(bad)
