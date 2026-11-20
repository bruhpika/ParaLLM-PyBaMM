"""v4a applicability mini-benchmark case construction.

Builds a public case set (no gold answers) and a private answer key from the
committed parameter registry. No parameter value is invented: every candidate
is copied verbatim from a registry record, including preserved same-source
conflict alternatives.

Gold answers follow the documented deterministic rule ``GOLD_RULE`` below. The
answers are drafted by the assistant and are not published; they live under
``data/private_v4/`` until the project owner reviews them.
"""

from __future__ import annotations

from typing import Any

TARGET_ID = "lgm50_chen2020_dfn"
GOLD_RULE_VERSION = "v4a-gold-1"
GOLD_RULE = (
    "For a same-source conflict, adopt the source's operative (parameterized) "
    "value and preserve the competing value with its method. The decision is "
    "FIX when the operative value is ASSUMED or CALIBRATED and USE otherwise."
)


def _method_class(kind: str | None, method: str | None) -> str:
    if kind == "ASSUMED":
        return "assumed"
    if kind == "CALIBRATED":
        return "calibrated"
    if kind == "CALCULATED":
        return "calculated"
    text = (method or "").lower()
    if "measured" in text or "vernier" in text or "sem" in text:
        return "measured"
    if "fit" in text:
        return "fitted"
    if "calculated" in text or "computed" in text:
        return "calculated"
    return "unknown"


def _candidate(record: dict[str, Any], is_operative: bool, alt: dict | None = None) -> dict:
    """Candidate copied verbatim from a registry record or its conflict entry."""
    if is_operative:
        evidence = record.get("evidence") or {}
        source = evidence.get("source") or {}
        return {
            "value": record.get("value"),
            "unit": record.get("value_unit"),
            "canonical_value": record.get("normalized_value"),
            "canonical_unit": record.get("normalized_value_unit"),
            "method_class": _method_class(record.get("status"), record.get("method")),
            "method": record.get("method"),
            "status": record.get("status"),
            "conditions": record.get("conditions"),
            "source_id": record.get("source_id"),
            "source_document": source.get("document_id") or record.get("source_id"),
            "source_locator": source.get("locator"),
            "page": source.get("page"),
            "quote": source.get("quote"),
            "quote_verified": None,
            "is_operative": True,
            "model_applicable": (record.get("pybop_mapping") or {}).get("applicable", True),
        }
    entry = alt or {}
    source = entry.get("source") or {}
    return {
        "value": entry.get("value"),
        "unit": entry.get("unit"),
        "canonical_value": entry.get("normalized_value"),
        "canonical_unit": entry.get("normalized_value_unit"),
        "method_class": _method_class(entry.get("kind"), entry.get("method")),
        "method": entry.get("method"),
        "status": entry.get("kind"),
        "conditions": entry.get("conditions"),
        "source_id": source.get("document_id"),
        "source_document": source.get("document_id"),
        "source_locator": source.get("locator"),
        "page": source.get("page"),
        "quote": source.get("quote"),
        "quote_verified": None,
        "is_operative": False,
        "model_applicable": True,
    }


def _public_case(record: dict[str, Any], alt: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": f"V4A-{record['canonical_id']}",
        "target_id": TARGET_ID,
        "parameter": record["canonical_id"],
        "candidates": [
            _candidate(record, is_operative=True),
            _candidate(record, is_operative=False, alt=alt),
        ],
        "case_class": "conflict",
    }


def _answer(record: dict[str, Any]) -> dict[str, Any]:
    operative = _candidate(record, is_operative=True)
    decision = (
        "FIX"
        if operative["method_class"] in ("assumed", "calibrated")
        else "USE"
    )
    return {
        "case_id": f"V4A-{record['canonical_id']}",
        "expert_decision": decision,
        "expert_choice": 0,
        "expert_rationale": (
            "Same-source conflict: adopt the source's operative (parameterized) "
            "value; the competing value is preserved with its method."
        ),
        "ambiguous": False,
        "label_status": "drafted",
        "reviewed_by": None,
    }


def build_dataset(records: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Return ``(public_cases, private_answers)`` for the v4a mini-benchmark."""
    public: list[dict] = []
    answers: list[dict] = []
    for record in sorted(records, key=lambda r: str(r.get("canonical_id"))):
        conflicts = record.get("conflicts") or []
        if not conflicts:
            continue
        for alt in conflicts:
            public.append(_public_case(record, alt))
            answers.append(_answer(record))
    return public, answers
