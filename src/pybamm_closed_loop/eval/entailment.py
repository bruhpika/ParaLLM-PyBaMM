"""Opt-in, label-free deterministic entailment checks on v4 candidates.

This is a post-processing pass over *existing* candidate JSON. It uses only the
candidate and the evidence text shown to the extractor — never the fixture gold
or item ID — so it cannot leak labels. Three checks are implemented:

1. **Value-in-quote** — the candidate's numeric value must be readable from
   the quote span it cites. If not, the candidate is a definitive contradiction
   and is dropped.
2. **Material role-only** — a material that is just an electrode role
   (``anode``, ``HE cathode``, ...) is not a chemical composition; clear it
   rather than substituting a guessed composition.
3. **Cell identity** — a cell_config whose tokens do not occur in the evidence
   is cleared rather than trusted as an imported product name.

The pass never repairs a field with a value from anywhere else: a failed check
either drops the candidate or reports the field as missing. That is the
scientific boundary of this module.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ..literature.evidence import verify_quote_in_evidence
from ..registry.textnorm import ascii_fold

_MISSING = frozenset(
    {"", "unresolved", "not stated", "not_stated", "unknown", "n/a", "none"}
)

_ROLE_ONLY_RE = re.compile(
    r"^(?:(?:he|hp|high\s+energy|high\s+power)\s+)?"
    r"(?:anode|cathode|negative\s+electrode|positive\s+electrode)"
    r"(?:\s+cell)?$",
    re.IGNORECASE,
)

_VALUE_TOKEN_RE = re.compile(
    r"[-+]?\d+(?:[.,]\d+)?"
    r"(?:\s*\*\s*10\s*\^?\s*[-+]?\d+|\s*[eE]\s*[-+]?\d+)?"
)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").replace("−", "-").split()).lower()


def _is_missing(value: Any) -> bool:
    return value is None or _norm(value) in _MISSING


def _quote_numbers(text: str) -> list[float]:
    """Numeric values printed in a quote, including ``9.61·10−15`` forms."""
    # Replace before ascii_fold: ascii_fold maps '·' to '.', which would break
    # the exponent separator ("9.61·10−15" must stay one number).
    raw = (
        str(text or "")
        .replace("·", "*")
        .replace("×", "*")
        .replace("∗", "*")
        .replace("−", "-")
        .replace("–", "-")
    )
    folded = ascii_fold(raw)
    out: list[float] = []
    for match in _VALUE_TOKEN_RE.finditer(folded):
        token = re.sub(r"\s+", "", match.group(0)).replace(",", ".")
        try:
            if "*" in token:
                mantissa, exponent = token.split("*", 1)
                exponent = exponent.strip()
                if exponent.startswith("10"):
                    exponent = exponent[2:]
                exponent = exponent.lstrip("^")
                out.append(float(mantissa) * (10 ** int(exponent)))
            else:
                out.append(float(token))
        except (ValueError, OverflowError):
            continue
    return out


def _value_supported_by_quote(value: Any, quote: str) -> bool:
    from .benchmark_v4 import _same_magnitude

    try:
        target = float(value)
    except (TypeError, ValueError):
        return False
    return any(_same_magnitude(number, target) for number in _quote_numbers(quote))


def _cell_supported(cell_config: Any, evidence_text: str) -> bool:
    if _is_missing(cell_config):
        return True
    evidence = ascii_fold(evidence_text).lower()
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", ascii_fold(cell_config).lower())
        if len(token) >= 3 or token.isdigit()
    ]
    return bool(tokens) and all(token in evidence for token in tokens)


def verify_candidate(
    evidence_text: str, candidate: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Return ``(cleaned_candidate, reasons)`` for one candidate."""
    reasons: list[str] = []
    cleaned = dict(candidate)

    quote = (candidate.get("source") or {}).get("quote")
    if quote and not verify_quote_in_evidence(quote, evidence_text):
        reasons.append("quote_not_verbatim")
    if quote and not _value_supported_by_quote(candidate.get("value"), quote):
        # A cited quote that does not contain the value is a definitive error.
        reasons.append("value_not_in_quote")

    material = candidate.get("material")
    if not _is_missing(material) and _ROLE_ONLY_RE.match(_norm(material).strip()):
        cleaned["material"] = None
        reasons.append("role_only_material")

    if not _cell_supported(candidate.get("cell_config"), evidence_text):
        cleaned["cell_config"] = None
        reasons.append("cell_not_in_evidence")

    return cleaned, reasons


def apply_entailment(
    evidence_text: str, candidates: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply the deterministic checks to every candidate (no model calls)."""
    kept: list[dict[str, Any]] = []
    reason_counts: dict[str, int] = {}
    for candidate in candidates:
        cleaned, reasons = verify_candidate(evidence_text, candidate)
        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if "value_not_in_quote" in reasons:
            continue
        kept.append(cleaned)
    stats = {
        "n_entailment_candidates": len(candidates),
        "n_entailment_dropped": len(candidates) - len(kept),
        "entailment_rule_counts": reason_counts,
    }
    return kept, stats
