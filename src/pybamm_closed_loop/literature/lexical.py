"""Cheap lexical retrieval improvements (no new dependencies).

Only declared, non-gold information is used: the query built from parameter
name / unit / declared facets, the public registry parameter names, the
existing retrieval synonym table, and segment headings/text. The gold probe,
gold conditions and target document id never enter these functions.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .index import SYNONYMS, expand_query, tokenize
from ..registry.units import to_canonical

TABLE_BOOST = 1.5
UNIT_BOOST = 1.25

# Notation aliases keyed by the *existing* SYNONYMS group names. These are
# query spellings only, not electrochemical values or parameter definitions.
SYMBOL_VARIANTS: dict[str, tuple[str, ...]] = {
    "diffusivity": ("D_s", "Ds"),
    "conductivity": ("sigma", "kappa"),
    "exchange_current": ("j0", "i0"),
    "porosity": ("epsilon",),
    "volume_fraction": ("epsilon",),
    "transference": ("t+",),
}


def unit_query_terms(unit: str | None) -> list[str]:
    """Declared-unit spellings only; never reads a gold value."""
    if not unit:
        return []
    raw = str(unit).strip()
    if not raw or raw in {"dimensionless", "-", "--"}:
        return []
    variants = [raw, raw.replace(".", " "), raw.replace(" ", ".")]
    try:
        canonical = to_canonical(raw)[0]
        variants += [canonical, canonical.replace(".", " "), canonical.replace(".", "")]
    except (KeyError, ValueError):
        pass
    if raw == "%":
        variants.append("percent")
    out: list[str] = []
    for variant in variants:
        for token in tokenize(variant):
            if token not in out:
                out.append(token)
    return out


def registry_aliases(query: str, records: Sequence[Mapping[str, Any]]) -> list[str]:
    """Public PyBaMM names for a matched registry record (never fixture gold)."""
    tokens = set(tokenize(query))
    out: list[str] = []
    for record in records:
        canonical = str(record.get("canonical_id") or "")
        names = [str(n) for n in (record.get("pybamm_names") or [])]
        alias_text = " ".join([canonical.replace("_", " "), *names])
        overlap = {t for t in tokenize(alias_text) if len(t) > 3} & tokens
        if len(overlap) < 2:
            continue
        for term in tokenize(canonical.replace("_", " ")):
            if term not in out:
                out.append(term)
        for name in names:
            for term in tokenize(name):
                if term not in out:
                    out.append(term)
    return out


def symbol_terms(query: str) -> list[str]:
    tokens = set(tokenize(query))
    out: list[str] = []
    for group, aliases in SYMBOL_VARIANTS.items():
        if any(a in query.lower() or set(tokenize(a)) & tokens for a in SYNONYMS[group]):
            for alias in aliases:
                for term in tokenize(alias):
                    if term not in out:
                        out.append(term)
    return out


def lexical_terms(
    base_query: str,
    *,
    unit: str | None = None,
    registry_records: Sequence[Mapping[str, Any]] | None = None,
    use_registry: bool = True,
    use_unit: bool = True,
    use_symbols: bool = True,
) -> list[str]:
    """Append declared-only aliases to an already-leak-safe base query."""
    terms = expand_query(base_query)
    additions: list[str] = []
    if use_registry and registry_records:
        additions.extend(registry_aliases(base_query, registry_records))
    if use_unit:
        additions.extend(unit_query_terms(unit))
    if use_symbols:
        additions.extend(symbol_terms(base_query))
    for term in additions:
        if term not in terms:
            terms.append(term)
    return terms


def lexical_search(
    index: Any,
    terms: Sequence[str],
    *,
    k: int,
    boost_tables: bool = False,
    unit_terms: Sequence[str] = (),
    boost_units: bool = False,
) -> list[tuple[Any, float]]:
    """BM25 with optional table/caption and number+unit segment multipliers."""
    scores = index.score_terms(list(terms))
    if boost_tables:
        for i, segment in enumerate(index.segments):
            heading = (segment.heading or "").lower()
            if "table" in heading or "figure" in heading:
                scores[i] *= TABLE_BOOST
    if boost_units and unit_terms:
        wanted = set(unit_terms)
        for i, segment in enumerate(index.segments):
            text = segment.text.lower()
            if any(term in text for term in wanted) and any(ch.isdigit() for ch in text):
                scores[i] *= UNIT_BOOST
    ranked = sorted(range(len(index.segments)), key=lambda i: scores[i], reverse=True)
    return [(index.segments[i], scores[i]) for i in ranked[:k] if scores[i] > 0]
