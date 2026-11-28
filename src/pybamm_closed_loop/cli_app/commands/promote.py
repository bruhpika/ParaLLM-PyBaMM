"""Promote a validated, reviewed extraction candidate into a NEW registry file.

Nothing is written unless every gate passes:

1. deterministic validation is *re-run here* on the candidate payload; no
   state, check result or quote claim from the input report is trusted;
2. the source quote verifies verbatim against the supplied document store,
   contains the candidate's value and uses a compatible, known unit;
3. an explicit human review carries a non-empty candidate hash matching
   exactly one candidate, a reviewer and a recorded reason; and
4. the canonical id has an explicit, installed PyBaMM name mapping.

Conflicting values are preserved as conflicts; an existing base registry is
never modified. The output is always a new file chosen with ``--out``.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import typer

from ..context import State
from ..errors import InputError
from ..inputs import load_json, sha256
from ..render import kv, notice, section
from ...registry.model import (
    ParameterRecord, ParameterStatus, ReviewState, SourceRef,
    ValueEntry, candidate_sha256, validate_extraction_schema,
)


def _state(ctx: typer.Context) -> State:
    state = ctx.obj
    if not isinstance(state, State):
        raise InputError("CLI state was not initialised.", action="Report this as a CLI bug.")
    return state


def _candidate_hash(payload: dict[str, Any]) -> str:
    """The hash a human copies from `validate --json` into a review record."""
    return candidate_sha256(payload)


def _unwrap_report(raw: Any) -> dict[str, Any]:
    """Accept the exact JSON emitted by `validate --json` or its `data` block."""
    if not isinstance(raw, dict):
        return {}
    data = raw.get("data")
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data
    return raw


_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")

# A number followed by a unit-bearing token. Handles micro signs, scientific
# notation and compound units such as "m2 s-1" / "m2.s-1" / "mol m-3".
_VALUE_UNIT_RE = re.compile(
    r"(?P<value>[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
    r"(?:\s*[x\u00d7]\s*10\s*(?P<exp>[-\u2212+]?\d+))?"
    r"\s*(?P<unit>[A-Za-z\u00b5\u03bc][A-Za-z0-9.\u00b5\u03bc-]*(?:\s+[A-Za-z0-9.\u00b5\u03bc-]+){0,2})"
)

_POSITIVE_HINTS = ("positive", "cathode", "nmc", "lfp", "lco", "nca", "limetal")
_NEGATIVE_HINTS = ("negative", "anode", "graphite", "siox", "li-metal")


def _normalise_text(text: str) -> str:
    """Fold micro signs and unicode minus so paper typography still matches."""
    return (
        str(text).replace("\u00b5", "u").replace("\u03bc", "u")
        .replace("\u2212", "-").replace("\u2013", "-")
    )


def _canonical_unit_of(token: str) -> str | None:
    """Canonical unit name for a quoted unit token, or None if unrecognised."""
    from ...registry.units import to_canonical

    words = token.strip().split()
    if not words:
        return None
    # The regex may capture a few trailing prose words; try progressively
    # shorter leading prefixes so "um measured by" resolves as "um".
    for n in range(len(words), 0, -1):
        form = ".".join(words[:n])
        try:
            return to_canonical(form)[0]
        except KeyError:
            continue
    return None


def _quantity_terms(canonical_id: str) -> tuple[str, ...]:
    """Meaningful words of the quantity name (ignoring electrode prefixes)."""
    tokens = [
        t for t in re.split(r"[_\s]+", canonical_id.lower())
        if t and t not in ("pos", "neg", "positive", "negative")
    ]
    return tuple(tokens)


def _electrode_hint(canonical_id: str) -> str | None:
    name = canonical_id.lower()
    if name.startswith(("pos_", "positive_")):
        return "positive"
    if name.startswith(("neg_", "negative_")):
        return "negative"
    return None


def _quote_pairs(quote: str, expected_unit: str | None) -> list[tuple[float, int, int]]:
    """(value, start, end) for number+unit pairs with a compatible unit."""
    pairs: list[tuple[float, int, int]] = []
    for match in _VALUE_UNIT_RE.finditer(_normalise_text(quote)):
        unit = _canonical_unit_of(match.group("unit"))
        if expected_unit is not None and unit != expected_unit:
            continue
        value = float(match.group("value"))
        if match.group("exp"):
            value *= 10.0 ** int(match.group("exp"))
        pairs.append((value, match.start(), match.end()))
    return pairs


def _associated_values(quote: str, canonical_id: str,
                       expected_unit: str | None) -> tuple[list[float], str | None]:
    """Values in the quote that belong to the named quantity and electrode.

    Returns (values, ambiguity_reason). Refusing on ambiguity is intentional:
    a narrower quote is safer than guessing which number was meant.
    """
    folded = _normalise_text(quote).lower()
    hint = _electrode_hint(canonical_id)
    positive = any(word in folded for word in _POSITIVE_HINTS)
    negative = any(word in folded for word in _NEGATIVE_HINTS)
    if hint == "positive" and negative and not positive:
        return [], "quote names the negative electrode for a positive parameter"
    if hint == "negative" and positive and not negative:
        return [], "quote names the positive electrode for a negative parameter"
    if positive and negative:
        return [], "quote names both electrodes; use a narrower quote"

    terms = _quantity_terms(canonical_id)
    if not terms or not all(term in folded for term in terms):
        return [], "quote does not name the quantity"

    pairs = _quote_pairs(quote, expected_unit)
    if not pairs:
        return [], "quote has no number with a compatible unit near the quantity"
    # Only pairs whose local window names the quantity count as belonging to it.
    values = [
        value for value, start, end in pairs
        if all(term in folded[max(0, start - 60):min(len(folded), end + 60)] for term in terms)
    ]
    if not values:
        return [], "no number with a compatible unit is associated with the quantity"
    return values, None


def _revalidate(payload: dict[str, Any], doc_texts: dict[str, str],
                store: Any, installed_names: list[str] | None) -> tuple[str, list[dict[str, str]]]:
    """Run the deterministic checks again; never trust reported state."""
    from ...validation.checks import (
        ReviewReport, check_conditions, check_definition, check_plausibility,
        check_provenance, check_pybamm_mapping, check_qualifier,
        check_value_unit, detect_conflict,
    )
    from ...cli_app.render import status_text

    report = ReviewReport()
    schema_ok, schema_reason = validate_extraction_schema(payload)
    report.add("schema", "ok" if schema_ok else "fail", schema_reason)
    for fn in (check_definition, check_conditions, check_qualifier):
        level, detail = fn(payload)
        report.add(fn.__name__, level, detail)
    if doc_texts:
        level, detail = check_provenance(payload, doc_texts)
        report.add("check_provenance", level, detail)
    else:
        report.add("check_provenance", "not_checked", "no --documents store supplied")
    try:
        canonical, value, _ = check_value_unit(payload)
        report.add("unit_conversion", "ok", f"converted to {value:g} {canonical}")
    except (ValueError, KeyError) as exc:
        report.add("unit_conversion", "fail", str(exc))
    level, detail = check_plausibility(payload, None)
    report.add("physical_plausibility", level, detail)
    if store is not None:
        level, detail = detect_conflict(payload, store)
        report.add("conflicting_evidence", level, detail)
        level, detail = check_pybamm_mapping(payload, store, installed_names)
        report.add("pybamm_mapping", level, detail)
    else:
        report.add("conflicting_evidence", "not_checked", "no registry supplied")
        report.add("pybamm_mapping", "not_checked", "no registry supplied")
    levels = {c.level for c in report.checks}
    state = (
        "REJECTED" if "fail" in levels
        else "NEEDS_REVIEW" if "warn" in levels or "not_checked" in levels
        else "ACCEPTED"
    )
    checks = [
        {"name": c.name, "level": status_text(c.level).plain, "detail": c.detail}
        for c in report.checks
    ]
    return state, checks


def _expected_canonical_unit(payload: dict[str, Any], pybamm_names: list[str]) -> str | None:
    """Return the canonical unit implied by the parameter family / PyBaMM name."""
    from ...registry.units import pybamm_unit_suffix, to_canonical
    from ...validation.checks import PLAUSIBILITY_RANGES

    for name in pybamm_names:
        suffix = pybamm_unit_suffix(name)
        if suffix:
            try:
                return to_canonical(suffix)[0]
            except KeyError:
                continue
    probe = str(payload.get("parameter_name", "")).lower().replace(" ", "_")
    for key, (_, _, expected) in PLAUSIBILITY_RANGES.items():
        if key in probe:
            return expected
    return None


def _quote_supports(payload: dict[str, Any], doc_text: str,
                    expected_unit: str | None) -> tuple[bool, str]:
    """Check that the quote supports the value and a compatible known unit."""
    from ...literature.evidence import (
        table_header_context, verify_quote_in_evidence,
    )
    from ...registry.units import to_canonical

    quote = str((payload.get("source") or {}).get("quote") or "")
    if not quote or not verify_quote_in_evidence(quote, doc_text):
        return False, "quote not verified against --documents"
    try:
        canonical, _ = to_canonical(str(payload.get("unit")))
    except KeyError as exc:
        return False, f"unknown or incompatible unit: {exc}"
    if expected_unit is not None and canonical != expected_unit:
        return False, (
            f"unit mismatch: quote/parameter expects {expected_unit}, "
            f"candidate has {canonical}"
        )
    # A table row needs its own header/caption to be checkable. Refuse before
    # trying to associate numbers with the quantity: an unchecked table cannot
    # support a value/quantity claim.
    locator = str((payload.get("source") or {}).get("locator") or "")
    looks_like_table = (
        "\t" in quote
        or bool(re.search(r"\S {2,}\S", quote))
        or "table" in locator.lower()
    )
    numeric_tokens = _NUMBER_RE.findall(quote.replace(",", ""))
    if looks_like_table and len(numeric_tokens) >= 2:
        context = table_header_context(doc_text, quote)
        if not context:
            return False, "table quote cannot be checked: no header/context for this table"

    name = str(payload.get("parameter_name") or "")
    values, ambiguity = _associated_values(quote, name, canonical)
    if ambiguity:
        return False, ambiguity
    # A dimensionless quantity must be the only number that could be its value.
    if canonical == "dimensionless" and len(values) > 1:
        return False, "ambiguous quote: several dimensionless numbers could be the value"
    if len(values) > 1:
        return False, "ambiguous quote: several values with a compatible unit; use a narrower quote"
    try:
        candidate_value = float(payload.get("value"))
    except (TypeError, ValueError):
        return False, "candidate value is not numeric"
    if not values or values[0] != candidate_value:
        return False, "value is not supported by the recorded quote"
    return True, "quote, value and unit are consistent"


def _verified_pybamm_names(canonical: str, mapping: dict[str, list[str]],
                           installed: set[str]) -> tuple[list[str], str]:
    """Take names only from the explicit mapping and verify installation."""
    names = mapping.get(canonical) or []
    if not names:
        return [], f"parameter {canonical!r} is not in the explicit PyBaMM mapping"
    verified = [name for name in names if name in installed]
    if not verified:
        return [], f"no mapped PyBaMM name for {canonical!r} is installed"
    return verified, ""


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
    parameter_set: str = typer.Option("Chen2020", "--parameter-set"),
) -> int:
    """Add a reviewed candidate to a new registry file; keep conflicts."""
    from ...pybamm_engine import installed_parameter_names
    from ...registry.mapping import load_explicit_pybamm_mapping
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

    report = _unwrap_report(load_json(vpath, description="validation report"))
    if not isinstance(report.get("results"), list):
        raise InputError(
            "Validation report is missing 'results'.",
            action="Pass the JSON emitted by `parallm validate --json` (the whole object or its data block).",
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
    if len(payloads) != len(report["results"]):
        raise InputError(
            "Validation report candidates and results have different lengths.",
            action="Re-run validate so candidates and results come from the same invocation.",
        )

    doc_texts = load_doc_texts(documents.expanduser().resolve()) if documents else {}
    mapping = load_explicit_pybamm_mapping()
    installed = set(installed_parameter_names(parameter_set))

    # The mapping also provides PyBaMM names for unit compatibility. Registry
    # directory for the other checks: prefer the base file's directory, else
    # the committed registry directory (read-only).
    from ...registry.store import RegistryStore

    if base is not None:
        base_path = base.expanduser().resolve()
        store = RegistryStore(base_path.parent)
    else:
        store = RegistryStore(
            Path(__file__).resolve().parents[4] / "data" / "registry"
        )

    records: list[dict[str, Any]] = []
    if base is not None:
        loaded = load_json(base_path, description="base registry")
        if isinstance(loaded, list):
            records = copy.deepcopy(loaded)

    promoted: list[str] = []
    shown_hashes: dict[str, str] = {}
    skipped: list[dict[str, str]] = []
    for index, (payload, _reported) in enumerate(zip(payloads, report["results"])):
        if not isinstance(payload, dict):
            skipped.append({"index": str(index), "reason": "malformed candidate"})
            continue
        name = str(payload.get("parameter_name") or "")
        if not name:
            skipped.append({"index": str(index), "reason": "candidate has no parameter name"})
            continue

        state_name, checks = _revalidate(payload, doc_texts, store,
                                         sorted(installed) if installed else None)
        if state_name == "REJECTED":
            failed = [c["detail"] for c in checks if c["level"] == "FAILED"]
            skipped.append({
                "parameter": name,
                "reason": "re-validation REJECTED: " + "; ".join(failed),
            })
            continue

        digest = _candidate_hash(payload)
        matches = [r for r in review_data["reviews"]
                   if isinstance(r, dict)
                   and str(r.get("candidate_hash") or "").strip() == digest]
        if not str(digest):
            skipped.append({"parameter": name, "reason": "empty candidate hash"})
            continue
        if not matches:
            skipped.append({
                "parameter": name,
                "reason": "review requires a non-empty candidate_hash matching this candidate",
            })
            continue
        if len(matches) != 1:
            skipped.append({
                "parameter": name,
                "reason": "candidate_hash matches more than one review record",
            })
            continue
        human = matches[0]
        if human.get("decision") != "APPROVED" or not str(human.get("reviewer") or "").strip():
            skipped.append({"parameter": name, "reason": "no explicit APPROVED human review"})
            continue
        reason = str(human.get("reason") or "").strip()
        if not reason:
            skipped.append({"parameter": name, "reason": "human review has no recorded reason"})
            continue

        names, mapping_reason = _verified_pybamm_names(name, mapping, installed)
        if not names:
            skipped.append({"parameter": name, "reason": mapping_reason})
            continue
        expected_unit = _expected_canonical_unit(payload, names)
        src = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        doc_id = src.get("document_id")
        text = doc_texts.get(str(doc_id)) if doc_id else None
        if not text:
            skipped.append({"parameter": name, "reason": "source document not in --documents store"})
            continue
        ok, why = _quote_supports(payload, text, expected_unit)
        if not ok:
            skipped.append({"parameter": name, "reason": why})
            continue

        status = {
            "measured": ParameterStatus.LITERATURE_DERIVED,
            "fitted": ParameterStatus.CALIBRATED,
            "calculated": ParameterStatus.CALCULATED,
            "assumed": ParameterStatus.ASSUMED,
        }.get(str(payload.get("qualifier")), ParameterStatus.UNRESOLVED)

        # NEVER store NEEDS_REVIEW as ACCEPTED without the human's reason.
        validation_state = (
            ReviewState.NEEDS_REVIEW if state_name == "NEEDS_REVIEW"
            else ReviewState.ACCEPTED
        )
        review_reason = f"{reason} (reviewer: {human['reviewer']}, hash: {digest})"
        entry = ValueEntry(
            value=payload.get("value"), unit=payload.get("unit"),
            source=SourceRef(
                document_id=str(doc_id or "UNRESOLVED"),
                doi_or_url=src.get("doi_or_url"),
                locator=src.get("locator"), page=src.get("page"),
                quote=str(src.get("quote") or ""),
            ),
            kind=status,
            reported_uncertainty=payload.get("reported_uncertainty"),
            conditions={"cell": payload.get("cell_config"),
                        "temperature_k": payload.get("temperature"),
                        "chemistry": payload.get("material")},
            method=payload.get("measurement_method"),
            context=payload.get("context"),
            review_state=validation_state,
            review_reason=review_reason,
        )
        existing = next((r for r in records if r.get("canonical_id") == name), None)
        if existing is None:
            from ...registry.units import to_canonical
            try:
                canon_unit, factor = to_canonical(str(payload.get("unit")))
            except KeyError:
                canon_unit, factor = str(payload.get("unit")), 1.0
            record = ParameterRecord(
                canonical_id=name,
                pybamm_names=names,
                pybop_mapping=None,
                definition=str(payload.get("definition") or "UNRESOLVED"),
                value=payload.get("value"),
                value_unit=payload.get("unit"),
                normalized_value=float(payload["value"]) * factor,
                normalized_value_unit=canon_unit,
                status=status,
                source_id=str(doc_id or "UNRESOLVED"),
                source_location=src.get("locator"),
                evidence=entry,
                conditions=entry.conditions,
                method=payload.get("measurement_method"),
                reported_uncertainty=payload.get("reported_uncertainty"),
                validation_state=validation_state,
                compatibility={},
                notes=[f"promoted by human review: {human['reviewer']}", review_reason],
            )
            records.append(record.to_dict())
        else:
            existing.setdefault("conflicts", []).append(entry.to_dict())
            existing.setdefault("notes", []).append(
                f"additional value preserved after review by {human['reviewer']}: {reason}"
            )
        promoted.append(name)
        shown_hashes[name] = digest

    if not promoted:
        raise InputError(
            "No candidate was promoted; nothing was written.",
            why="; ".join(f"{s.get('parameter', s.get('index'))}: {s['reason']}" for s in skipped),
            action="Fix validation, quote/unit consistency, the human review or the PyBaMM mapping.",
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = {
        "output": str(out_path), "promoted": promoted,
        "candidate_hashes": shown_hashes,
        "skipped": skipped, "n_records": len(records),
        "output_sha256": sha256(out_path),
    }
    if not state.quiet and not state.json_mode:
        section(state.console, "PROMOTION")
        kv(state.console, (
            ("Output", str(out_path)), ("Promoted", ", ".join(promoted)),
            ("Skipped", len(skipped)), ("Records", len(records)),
        ))
        for name in promoted:
            notice(state.console, f"{name}: candidate_hash {shown_hashes[name]}", "info")
        for s in skipped:
            notice(state.console, f"{s.get('parameter', s.get('index'))}: {s['reason']}", "warn")
    state.emit(result)
    return 0
