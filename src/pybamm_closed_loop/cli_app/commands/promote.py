"""Promote a validated, reviewed extraction candidate into a NEW registry file.

Nothing is written unless all three gates pass:
1. deterministic validation ACCEPTED the candidate,
2. the source quote verifies verbatim against the supplied document store,
3. an explicit human review record approves that exact candidate hash.

Conflicting values are preserved as conflicts; an existing base registry is
never modified. The output is always a new file chosen with ``--out``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import typer

from ..context import State
from ..errors import InputError
from ..inputs import load_json, sha256
from ..render import kv, notice, section
from ...registry.model import (
    ParameterRecord, ParameterStatus, ReviewState, SourceRef,
    ValueEntry, sha256_text, validate_extraction_schema,
)


def _state(ctx: typer.Context) -> State:
    state = ctx.obj
    if not isinstance(state, State):
        raise InputError("CLI state was not initialised.", action="Report this as a CLI bug.")
    return state


def _candidate_hash(payload: dict[str, Any]) -> str:
    return sha256_text(json.dumps(payload, sort_keys=True, default=str))


def promote(
    ctx: typer.Context,
    validated: Path = typer.Argument(
        ..., help="Validation report JSON emitted by `parallm validate --json`."
    ),
    review: Path = typer.Option(
        ..., "--review", help="Human review record JSON with an explicit APPROVED decision."
    ),
    out: Path = typer.Option(..., "--out", help="NEW registry file to write (never overwrites)."),
    documents: Path | None = typer.Option(
        None, "--documents", help="Document store used for verbatim quote verification."
    ),
    base: Path | None = typer.Option(
        None, "--base", help="Existing registry to copy (never modified)."
    ),
) -> int:
    """Add a reviewed candidate to a new registry file; keep conflicts."""
    from ...literature.evidence import verify_quote_in_evidence
    from ..inputs import load_doc_texts

    state = _state(ctx)
    vpath = validated.expanduser().resolve()
    rpath = review.expanduser().resolve()
    out_path = out.expanduser().resolve()
    if out_path.exists():
        raise InputError(
            "Promotion output already exists.",
            why=f"Refusing to overwrite: {out_path}",
            action="Choose a new --out path; a base registry is never modified.",
        )

    report = load_json(vpath, description="validation report")
    if not isinstance(report, dict) or not isinstance(report.get("results"), list):
        raise InputError(
            "Validation report is missing 'results'.",
            action="Pass the JSON emitted by `parallm validate --json`.",
        )
    review_data = load_json(rpath, description="human review record")
    if not isinstance(review_data, dict) or not isinstance(review_data.get("reviews"), list):
        raise InputError(
            "Review record is missing 'reviews'.",
            action="Provide an explicit human review file with a reviews list.",
        )

    candidates = report.get("candidates") or []
    if not isinstance(candidates, list) or not candidates:
        raise InputError(
            "Validation report has no candidate payloads.",
            action="Re-run validate with --include-candidates on the extract output.",
        )
    payloads = [
        c.get("payload") if isinstance(c, dict) and "payload" in c else c
        for c in candidates
    ]
    reviews = {str(r.get("parameter")): r for r in review_data["reviews"]
               if isinstance(r, dict)}

    doc_texts = load_doc_texts(documents.expanduser().resolve()) if documents else {}

    records: list[dict[str, Any]] = []
    if base is not None:
        base_path = base.expanduser().resolve()
        loaded = load_json(base_path, description="base registry")
        if isinstance(loaded, list):
            records = copy.deepcopy(loaded)

    promoted: list[str] = []
    skipped: list[dict[str, str]] = []
    for index, (payload, result) in enumerate(zip(payloads, report["results"])):
        if not isinstance(payload, dict) or not isinstance(result, dict):
            skipped.append({"index": str(index), "reason": "malformed candidate"})
            continue
        name = str(payload.get("parameter_name") or result.get("parameter") or "")
        if result.get("state") not in ("ACCEPTED", "NEEDS_REVIEW"):
            skipped.append({
                "parameter": name,
                "reason": f"validation state {result.get('state')} blocks promotion",
            })
            continue
        ok, why = validate_extraction_schema(payload)
        if not ok:
            skipped.append({"parameter": name, "reason": f"schema: {why}"})
            continue

        review = reviews.get(name)
        if not review or review.get("decision") != "APPROVED" or not str(review.get("reviewer") or "").strip():
            skipped.append({"parameter": name, "reason": "no explicit APPROVED human review"})
            continue
        if str(review.get("candidate_hash") or "") not in ("", _candidate_hash(payload)):
            skipped.append({"parameter": name, "reason": "review does not match this candidate hash"})
            continue

        src = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        quote = src.get("quote")
        if not quote:
            skipped.append({"parameter": name, "reason": "no source quote to verify"})
            continue
        doc_id = src.get("document_id")
        text = doc_texts.get(str(doc_id)) if doc_id else None
        if not text or not verify_quote_in_evidence(str(quote), text):
            skipped.append({"parameter": name, "reason": "quote not verified against --documents"})
            continue

        canonical = name
        status = {
            "measured": ParameterStatus.LITERATURE_DERIVED,
            "fitted": ParameterStatus.CALIBRATED,
            "calculated": ParameterStatus.CALCULATED,
            "assumed": ParameterStatus.ASSUMED,
        }.get(str(payload.get("qualifier")), ParameterStatus.UNRESOLVED)
        entry = ValueEntry(
            value=payload.get("value"), unit=payload.get("unit"),
            source=SourceRef(
                document_id=str(doc_id or "UNRESOLVED"),
                doi_or_url=src.get("doi_or_url"),
                locator=src.get("locator"), page=src.get("page"),
                quote=str(quote),
            ),
            kind=status,
            reported_uncertainty=payload.get("reported_uncertainty"),
            conditions={"cell": payload.get("cell_config"),
                        "temperature_k": payload.get("temperature"),
                        "chemistry": payload.get("material")},
            method=payload.get("measurement_method"),
            context=payload.get("context"),
            review_state=ReviewState.ACCEPTED,
            review_reason=f"promoted after human review by {review['reviewer']}",
        )
        existing = next((r for r in records if r.get("canonical_id") == canonical), None)
        if existing is None:
            from ...registry.units import to_canonical
            try:
                canon_value, factor = to_canonical(str(payload.get("unit")))
            except KeyError:
                canon_value, factor = str(payload.get("unit")), 1.0
            record = ParameterRecord(
                canonical_id=canonical,
                pybamm_names=[],
                pybop_mapping=None,
                definition=str(payload.get("definition") or "UNRESOLVED"),
                value=payload.get("value"),
                value_unit=payload.get("unit"),
                normalized_value=float(payload["value"]) * factor,
                normalized_value_unit=canon_value,
                status=status,
                source_id=str(doc_id or "UNRESOLVED"),
                source_location=src.get("locator"),
                evidence=entry,
                conditions=entry.conditions,
                method=payload.get("measurement_method"),
                reported_uncertainty=payload.get("reported_uncertainty"),
                validation_state=ReviewState.ACCEPTED,
                compatibility={},
                notes=[f"promoted by human review: {review['reviewer']}"],
            )
            records.append(record.to_dict())
        else:
            # Keep conflicting values; never silently overwrite the operative one.
            existing.setdefault("conflicts", []).append(entry.to_dict())
            existing.setdefault("notes", []).append(
                f"additional value preserved after review by {review['reviewer']}"
            )
        promoted.append(canonical)

    if not promoted:
        raise InputError(
            "No candidate was promoted; nothing was written.",
            why="; ".join(f"{s['parameter']}: {s['reason']}" for s in skipped),
            action="Fix validation, quote verification or the human review record.",
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = {
        "output": str(out_path), "promoted": promoted,
        "skipped": skipped, "n_records": len(records),
        "output_sha256": sha256(out_path),
    }
    if not state.quiet and not state.json_mode:
        section(state.console, "PROMOTION")
        kv(state.console, (
            ("Output", str(out_path)), ("Promoted", ", ".join(promoted)),
            ("Skipped", len(skipped)), ("Records", len(records)),
        ))
        for s in skipped:
            notice(state.console, f"{s.get('parameter', s.get('index'))}: {s['reason']}", "warn")
    state.emit(result)
    return 0
