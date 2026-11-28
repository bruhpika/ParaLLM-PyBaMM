"""Shared helpers for building valid approval-gate fixtures.

These helpers only provide the binding that the production gate now requires;
the assertions in the tests that use them are unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pybamm_closed_loop.assembly.gate import binding_sha256 as _binding_sha256

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "registry" / "registry.json"


def binding_for_record(record: dict[str, Any], source_id: str | None = None) -> str:
    """Compute the approval binding from a registry record's selected value."""
    source = (record.get("evidence") or {}).get("source") or {}
    return _binding_sha256({
        "parameter": record.get("canonical_id"),
        "selected": {
            "value": record.get("value"),
            "unit": record.get("value_unit"),
            "canonical_value": record.get("normalized_value"),
            "canonical_unit": record.get("normalized_value_unit"),
        },
        "evidence": {
            "source_id": record.get("source_id") or source_id,
            "document": source.get("document_id"),
            "locator": source.get("locator"),
            "page": source.get("page"),
            "quote": source.get("quote"),
        },
    })


def binding_for_registry_id(name: str, registry: Path = REGISTRY) -> str:
    records = json.loads(registry.read_text())
    record = next((r for r in records if r.get("canonical_id") == name), None)
    if record is None:
        # Synthetic fixture ids: a syntactically valid binding is enough for
        # trust tests that never assert on approval matching.
        return "0" * 64
    return binding_for_record(record)


def decision_for_registry_id(name: str, registry: Path = REGISTRY) -> str:
    """The decision the v2 rubric produces for one registry parameter."""
    from pybamm_closed_loop.assembly import (
        Rubric, TargetSpecification, assemble,
    )

    records = json.loads(registry.read_text())
    target = TargetSpecification(
        target_id="lgm50_chen2020_dfn",
        cell_product="LG M50",
        chemistry_families=("NMC", "graphite"),
        format="21700",
        temperature_k=298.15,
        soc="50%",
    )
    report = assemble(records, target, Rubric("rubric-v2"))
    decisions = {d["parameter"]: d["decision"] for d in report.dossiers}
    # Synthetic fixture parameters are not in the committed registry; the
    # trust tests that use them do not assert on the rubric decision.
    return decisions.get(name, "USE")
