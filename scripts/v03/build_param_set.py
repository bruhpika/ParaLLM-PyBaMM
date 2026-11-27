#!/usr/bin/env python
"""Build the first-party candidate parameter set ``ParaLLM-Chen2020-ext``.

This is a deterministic, read-only transformation of two committed inputs:

* ``data/registry/chen2020_discrepancies.json`` (11 numeric discrepancy
  families + 16 set-extension families);
* ``data/registry/registry.json`` (96 provenance-first records).

Every numeric value and every source string is copied from those inputs; the
script authors no electrochemical value, quote, locator or PyBaMM name. All
names are verified by introspection of the pinned PyBaMM installation through
``pybamm_engine``. Fields with no literature source keep their registry status
(``UNRESOLVED`` / ``ASSUMED``) and carry explicit ``NOT_RECORDED`` sentinels —
never an invented literature citation.

The output is a *candidate* artifact with per-field provenance, not an approved
PyBaMM set: no gate file is created, no registry is written, and no PyBaMM
parameter set is registered (AGENTS.md rule 10). An optional human gate file can
only annotate approvals that already exist; it cannot make this artifact
exportable or registered.

Usage:
    .venv/bin/python scripts/v03/build_param_set.py \
        --config configs/v03/param_set.yaml
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import yaml  # noqa: E402

from pybamm_closed_loop import __version__ as package_version  # noqa: E402
from pybamm_closed_loop.assembly.gate import (  # noqa: E402
    ApprovalGate,
    GateValidationError,
)
from pybamm_closed_loop.pybamm_engine import (  # noqa: E402
    installed_scalar_values,
    verify_parameter_names,
)

DEFAULT_CONFIG = REPO_ROOT / "configs/v03/param_set.yaml"
SCHEMA_VERSION = 1
NOT_RECORDED = "NOT_RECORDED"
NOT_APPLICABLE = "NOT_APPLICABLE"
PENDING_APPROVAL = "PENDING_HUMAN_APPROVAL"
UNSOURCED_STATUSES = frozenset({"UNRESOLVED", "ASSUMED"})


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r} is not allowed")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def load_json(path: Path) -> Any:
    """Strict JSON load: no duplicate keys, no NaN/Infinity."""
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_no_duplicate_keys,
        parse_constant=_reject_constant,
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    """Repo-relative path when possible, absolute path otherwise."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def _canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _sentinel(value: Any) -> Any:
    return NOT_RECORDED if value is None else value


def _source(evidence: Mapping[str, Any] | None, record: Mapping[str, Any]) -> dict[str, Any]:
    """Build a complete source block; absent literature evidence stays a sentinel."""
    evidence = evidence or {}
    src = evidence.get("source") or {}
    has_literature = bool(src.get("document_id"))
    return {
        "kind": "literature" if has_literature else "installed_pybamm_default",
        "document_id": _sentinel(src.get("document_id")),
        "doi_or_url": _sentinel(src.get("doi_or_url")),
        "locator": _sentinel(src.get("locator") or record.get("source_location")),
        "quote": _sentinel(src.get("quote")),
        "char_start": _sentinel(src.get("char_start")),
        "char_end": _sentinel(src.get("char_end")),
        "review_state": _sentinel(evidence.get("review_state")),
        "method": _sentinel(evidence.get("method")),
        "registry_source_location": _sentinel(record.get("source_location")),
        "has_literature_source": has_literature,
    }


def _approval(cid: str, gate_records: dict[str, Any]) -> dict[str, Any]:
    rec = gate_records.get(cid)
    if rec is None:
        return {
            "status": NOT_RECORDED,
            "decision": NOT_RECORDED,
            "approver": NOT_RECORDED,
            "rubric_version": NOT_RECORDED,
            "timestamp": NOT_RECORDED,
            "note": NOT_RECORDED,
        }
    return {
        "status": "APPROVED" if rec.approved else "REJECTED",
        "decision": rec.decision,
        "approver": rec.approver,
        "rubric_version": rec.rubric_version,
        "timestamp": _sentinel(rec.timestamp),
        "note": _sentinel(rec.note),
    }


def _discrepancy_field(
    item: Mapping[str, Any],
    record: Mapping[str, Any],
    gate_records: dict[str, Any],
) -> dict[str, Any]:
    pybamm_side = item["pybamm"]
    names = list(pybamm_side["pybamm_names"])
    if names != list(record.get("pybamm_names") or []):
        raise ValueError(
            f"PyBaMM names for {item['canonical_id']} disagree between the "
            "discrepancy artifact and the registry"
        )
    value = record["normalized_value"]
    if value != pybamm_side["value"]:
        raise ValueError(
            f"operative value for {item['canonical_id']} disagrees between the "
            "registry and the discrepancy artifact"
        )
    src = _source(record.get("evidence"), record)
    if not src["has_literature_source"]:
        raise ValueError(f"discrepancy family {item['canonical_id']} has no literature source")
    return {
        "canonical_id": item["canonical_id"],
        "family": "numeric_discrepancy",
        "pybamm_names": names,
        "causes": list(item["causes"]),
        "operative": {
            "value": value,
            "unit": record["normalized_value_unit"],
            "status": record["status"],
            "validation_state": record["validation_state"],
        },
        "paper_evidence": dict(item["paper"]),
        "preserved_conflicts": list(record.get("conflicts") or []),
        "provenance": {
            "status": record["status"],
            "source": src,
            "locator": src["locator"],
            "notes": list(record.get("notes") or []),
        },
        "analysis": {
            "ratio": item.get("ratio"),
            "registry_notes": list(item.get("registry_notes") or []),
        },
        "cell_conditions": record.get("conditions") or {},
        "approval": _approval(item["canonical_id"], gate_records),
    }


def _set_extension_field(
    item: Mapping[str, Any],
    record: Mapping[str, Any],
    gate_records: dict[str, Any],
) -> dict[str, Any]:
    cid = item["canonical_id"]
    names = list(item["pybamm_names"])
    if names != list(record.get("pybamm_names") or []):
        raise ValueError(
            f"PyBaMM names for {cid} disagree between the discrepancy artifact "
            "and the registry"
        )
    status = record["status"]
    if status not in UNSOURCED_STATUSES:
        raise ValueError(
            f"set-extension family {cid} has status {status!r}, expected "
            "UNRESOLVED or ASSUMED (no literature source)"
        )
    src = _source(record.get("evidence"), record)
    if src["has_literature_source"]:
        raise ValueError(f"set-extension family {cid} unexpectedly has literature evidence")
    return {
        "canonical_id": cid,
        "family": "set_extension",
        "pybamm_names": names,
        "causes": ["set_extension"],
        "operative": {
            # Installed PyBaMM default, NOT a literature-derived value.
            "value": record["normalized_value"],
            "unit": record["normalized_value_unit"],
            "status": status,
            "validation_state": record["validation_state"],
        },
        "paper_evidence": {
            "status": NOT_APPLICABLE,
            "reason": "Chen2020 does not parameterize this family; value is an "
            "installed PyBaMM default carried in the registry",
        },
        "preserved_conflicts": list(record.get("conflicts") or []),
        "provenance": {
            "status": status,
            "source": src,
            "locator": src["locator"],
            "notes": list(record.get("notes") or []),
        },
        "analysis": {"note": item.get("note") or ""},
        "cell_conditions": record.get("conditions") or {},
        "approval": _approval(cid, gate_records),
    }


def build(config_path: Path = DEFAULT_CONFIG) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build (artifact, manifest) from a config file. No file is written here."""
    cfg = load_json(config_path) if config_path.suffix == ".json" else yaml.safe_load(
        config_path.read_text(encoding="utf-8")
    )
    if cfg.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported config schema_version: {cfg.get('schema_version')!r}")
    meta = cfg["artifact"]
    inputs = cfg["inputs"]
    outputs = cfg["outputs"]
    pybamm_cfg = cfg["pybamm"]

    discrepancy_path = REPO_ROOT / inputs["discrepancies"]
    registry_path = REPO_ROOT / inputs["registry"]
    gate_rel = inputs.get("gate")
    gate_path = REPO_ROOT / gate_rel if gate_rel else None
    discrepancies = load_json(discrepancy_path)
    records = load_json(registry_path)
    registry = {r["canonical_id"]: r for r in records}
    if len(registry) != len(records):
        raise ValueError("registry contains duplicate canonical ids")

    gate_records: dict[str, Any] = {}
    if gate_path is not None:
        try:
            gate = ApprovalGate.from_dict(load_json(gate_path))
        except GateValidationError as exc:
            raise ValueError(f"invalid human gate file: {exc}") from exc
        gate_records = {r.parameter: r for r in gate.records}

    fields: list[dict[str, Any]] = []
    for item in discrepancies["discrepancies"]:
        cid = item["canonical_id"]
        fields.append(_discrepancy_field(item, registry[cid], gate_records))
    for item in discrepancies["set_extensions"]["families"]:
        cid = item["canonical_id"]
        fields.append(_set_extension_field(item, registry[cid], gate_records))
    ids = [f["canonical_id"] for f in fields]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate canonical ids in the assembled field list")

    all_names = [name for f in fields for name in f["pybamm_names"]]
    verification = verify_parameter_names(all_names, pybamm_cfg["parameter_set"])
    if not verification["all_present"]:
        raise ValueError(
            "PyBaMM name verification FAILED (no name invented or substituted): "
            f"{verification['missing']}"
        )
    version = verification["pybamm_version"]
    if version != pybamm_cfg["required_version"]:
        raise ValueError(
            f"installed PyBaMM {version} != pinned {pybamm_cfg['required_version']}; "
            "refusing to build against an unverified version"
        )

    installed_values = installed_scalar_values(pybamm_cfg["parameter_set"])
    mismatches = [
        f["canonical_id"]
        for f in fields
        if any(
            name in installed_values and installed_values[name] != f["operative"]["value"]
            for name in f["pybamm_names"]
        )
    ]
    if mismatches:
        raise ValueError(
            "operative values disagree with the installed PyBaMM set "
            f"(no value is invented or substituted): {mismatches}"
        )
    value_verification = {
        "n_checked": len(fields),
        "n_matched": len(fields),
        "mismatches": [],
        "note": "internal consistency of copied values against installed "
        "PyBaMM defaults; NOT independent literature validation",
    }

    statuses: dict[str, int] = {}
    for f in fields:
        key = f["provenance"]["status"]
        statuses[key] = statuses.get(key, 0) + 1
    n_literature = sum(1 for f in fields if f["provenance"]["source"]["has_literature_source"])
    n_approved = sum(1 for f in fields if f["approval"]["status"] == "APPROVED")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": meta["artifact_id"],
        "artifact_version": meta["artifact_version"],
        "status": {
            "kind": "candidate_provenance_artifact",
            "approval": PENDING_APPROVAL if n_approved == 0 else "PARTIALLY_APPROVED",
            "n_approved_fields": n_approved,
            "exportable": False,
            "pybamm_set_registered": False,
            "registration_note": "This artifact is NOT a named PyBaMM parameter "
            "set; registration requires a human gate decision and a separate "
            "explicit action (AGENTS.md rule 10).",
        },
        "counts": {
            "fields": len(fields),
            "numeric_discrepancy_families": len(discrepancies["discrepancies"]),
            "set_extension_families": len(discrepancies["set_extensions"]["families"]),
            "fields_with_literature_source": n_literature,
            "fields_without_literature_source": len(fields) - n_literature,
            "statuses": dict(sorted(statuses.items())),
        },
        "limitations": [
            "11 numeric discrepancy families are separate from the 16 "
            "set-extension families; only the former have a paper-side value.",
            "Operative values are PyBaMM/Chen2020 values, including paper-tuned "
            "values; preserving them is not evidence of electrochemical truth.",
            "Set-extension values are installed PyBaMM defaults (UNRESOLVED or "
            "ASSUMED), not literature-derived; do not calibrate them without "
            "tracing their primary sources.",
            "No human approval is created by this builder; no parameter is "
            "exportable or registered from this artifact alone.",
            "This is not independent experimental validation; no optimization "
            "result is implied by a successful build.",
        ],
        "parameters": fields,
    }
    content_sha256 = hashlib.sha256(
        _canonical_bytes(
            {
                "schema_version": SCHEMA_VERSION,
                "artifact_id": meta["artifact_id"],
                "artifact_version": meta["artifact_version"],
                "parameters": fields,
            }
        )
    ).hexdigest()
    payload["content_sha256"] = content_sha256

    gate_hash = sha256_file(gate_path) if gate_path is not None else None
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": meta["artifact_id"],
        "artifact_version": meta["artifact_version"],
        "generator": {
            "script": "scripts/v03/build_param_set.py",
            "package_version": package_version,
            "python": sys.version.split()[0],
            "pybamm_version": version,
        },
        "inputs": {
            "discrepancies": {
                "path": inputs["discrepancies"],
                "sha256": sha256_file(discrepancy_path),
            },
            "registry": {
                "path": inputs["registry"],
                "sha256": sha256_file(registry_path),
            },
            "gate": {
                "path": gate_rel,
                "sha256": gate_hash,
                "n_approvals": len(gate_records),
            },
        },
        "config": {"path": _rel(config_path), "sha256": sha256_file(config_path)},
        "name_verification": verification,
        "value_verification": value_verification,
        "output": {
            "path": outputs["artifact"],
            "content_sha256": content_sha256,
            "counts": payload["counts"],
        },
        "approval": payload["status"],
    }
    payload["manifest"] = manifest
    return payload, manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument(
        "--out-dir",
        default=None,
        help="write the two outputs into this directory instead of the configured one",
    )
    args = ap.parse_args(argv)
    config_path = Path(args.config).resolve()
    payload, manifest = build(config_path)
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir).resolve() if args.out_dir else REPO_ROOT
    artifact_path = out_dir / cfg["outputs"]["artifact"]
    manifest_path = out_dir / cfg["outputs"]["manifest"]
    for path, data in ((artifact_path, payload), (manifest_path, manifest)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_canonical_bytes(data))
    print(f"wrote {artifact_path.relative_to(out_dir)}")
    print(f"wrote {manifest_path.relative_to(out_dir)}")
    print(f"  fields: {payload['counts']['fields']} "
          f"({payload['counts']['numeric_discrepancy_families']} discrepancies + "
          f"{payload['counts']['set_extension_families']} set extensions)")
    print(f"  content_sha256: {payload['content_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
