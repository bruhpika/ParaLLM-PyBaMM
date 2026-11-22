"""Deterministic value-local association for v4 condition scoring (V2.5).

The trace check in :func:`pybamm_closed_loop.eval.benchmark_v4.evidence_support`
asks only whether a condition's trace occurs *somewhere* in the evidence. That
is necessary but not sufficient: a number or keyword that occurs in a different
table row, a different sentence, or the document-level setup can be attached to
a value it does not belong to.

This module builds a deterministic *local scope* around the candidate's
verified quote and checks the condition there. The scope is:

- the table row containing the quote, plus the table caption, header and
  footnotes, when the quote lies inside a detected table; otherwise
- the sentence containing the quote, plus an adjacent condition-bearing
  sentence (a sentence that ends in ``:`` before the quote, or a sentence with
  a condition cue after it).

Conditions that are explicitly global in the source may fall back to the
document-level setup text, but only for temperature, cell, chemistry and
format. SOC and protocol are always local: a value's SOC/protocol cannot be
inferred from a document-level statement about a different value. A protocol
may use the global setup only when the candidate's method is GITT and the
global statement also names GITT (e.g. the GITT C/10 pulses); this supports the
GITT-derived values without letting the same C/10 statement leak into EIS
values.

The method field has an extra rule: a bare ``Experiment`` column label is not a
measurement method, and only recognised method families (EIS/impedance, GITT,
Arrhenius, CIM, simulation/model, DVA, ICA, CV, pulse, fit) are accepted. The
``Simulation`` label is allowed because simulation/model is a gold method for
the simulation-column values.

Everything is deterministic and auditable: each decision records the scope kind
and the rule that fired.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..literature.evidence import (
    _CUE_RE,
    _TABLE_CAPTION_RE,
    _split_sentences,
    condition_in_text,
    detect_table_blocks,
    verify_quote_in_evidence,
)
from ..registry.textnorm import ascii_fold

# Fields that may be stated once for the whole experiment and are therefore
# allowed to fall back to the explicit document-level setup. SOC and protocol
# are deliberately excluded: they are value-local (protocol has a narrow,
# method-matched exception below).
_GLOBAL_FALLBACK_FIELDS = frozenset(
    {"temperature_k", "cell", "chemistry", "format"}
)

_GLOBAL_CUE_RE = re.compile(
    r"\b(?:all|every|each)\s+(?:experiments?|measurements?|tests?|cells?|samples?)\b"
    r"|\bthroughout\b"
    r"|\b(?:experiments?|measurements?|tests?)\s+(?:were|are)\s+"
    r"(?:performed|conducted|carried\s+out|made|run)\b"
    r"|\b(?:unless\s+otherwise|generally|typically)\b"
    r"|\bthe\s+(?:cell|cells)\s+(?:was|were)\s+"
    r"(?:maintained|held|kept|tested|cycled)\s+at\b",
    re.IGNORECASE,
)

# Protocol claim vocabulary (same families as the scorer's context slicer).
_PROTOCOL_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("eis", ("eis", "impedance", "peis")),
    ("gitt", ("gitt",)),
    ("pulse", ("pulse", "pulses")),
    ("rest", ("rest", "resting")),
    ("cc-cv", ("cc-cv", "cccv", "cc cv")),
    ("galvanostatic", ("galvanostatic",)),
    ("potentiostatic", ("potentiostatic",)),
    ("ocv", ("ocv",)),
    ("cutoff", ("cutoff", "cut-off")),
    ("formation", ("formation",)),
    ("current interrupt", ("current interrupt",)),
)

_PROTOCOL_PATTERN = "|".join(
    re.escape(keyword)
    for _name, group in _PROTOCOL_GROUPS
    for keyword in group
)
_SCOPE_CUE_RE = re.compile(
    _CUE_RE.pattern + r"|\b(?:" + _PROTOCOL_PATTERN + r")\b",
    re.IGNORECASE,
)

_METHOD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("eis", ("eis", "impedance", "peis")),
    ("gitt", ("gitt",)),
    ("arrhenius", ("arrhenius",)),
    ("cim", ("cim",)),
    ("simulation", ("simulation", "simulations", "model", "models")),
    ("dva", ("dva",)),
    ("ica", ("ica",)),
    ("cv", ("cyclic voltammetry", "cv")),
    ("pulse", ("pulse", "pulses")),
    ("fit", ("fit", "fitting")),
)

# "Experiment" is a column label, not a method. "Simulation" is deliberately
# not rejected: simulation/model is the gold method for simulation-column
# values (B1/B5), and the table header is the evidence for it.
_COLUMN_LABELS = frozenset(
    {"experiment", "experiments", "experimental", "exp"}
)

_MISSING_VALUES = frozenset(
    {"", "unresolved", "not stated", "not_stated", "unknown", "n/a", "none"}
)

_CRATE_FRACTION_RE = re.compile(r"c\s*/\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_CRATE_NUM_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*c\b", re.IGNORECASE)
_DURATION_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(min(?:ute)?s?|h(?:our)?s?)\b", re.IGNORECASE
)
# "10, 25, and 40 degC" / "10/25/40 °C" — every listed number carries the
# trailing unit
_TEMPERATURE_LIST_RE = re.compile(
    r"(-?\d+(?:[.,]\d+)?"
    r"(?:(?:\s*[,/]\s*|\s*[-–~]\s*|\s*,?\s*and\s+)-?\d+(?:[.,]\d+)?)*)"
    r"\s*(?:°|deg\s*|degrees?\s*)?\s*(k\b|c\b|celsius|kelvin)",
    re.IGNORECASE,
)
_SIMPLE_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


@dataclass(frozen=True)
class AssociationScope:
    """The deterministic local (or fallback) text used to check conditions."""

    text: str
    kind: str
    quote: str | None
    global_text: str = ""
    table_caption: str | None = None
    table_header: tuple[str, ...] = ()
    table_row: str | None = None
    rules: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "quote": self.quote,
            "global_chars": len(self.global_text),
            "table_caption": self.table_caption,
            "table_header": list(self.table_header),
            "table_row": self.table_row,
            "rules": list(self.rules),
        }


@dataclass(frozen=True)
class AssociationResult:
    """One field's association verdict."""

    supported: bool
    scope: str
    rule: str


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("−", "-").split())


def _is_missing(value: Any) -> bool:
    return value is None or _norm_text(value) in _MISSING_VALUES


def _fold_lower(text: str) -> str:
    return ascii_fold(text).lower()


def _has_token(text: str, token: str) -> bool:
    return (
        re.search(rf"(?<![\w.]){re.escape(token)}(?![\w])", text) is not None
    )


def _contains_keyword(text: str, keyword: str) -> bool:
    return (
        re.search(
            rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text
        )
        is not None
    )


def _quote_span(text: str, quote: str | None) -> tuple[int, int] | None:
    if not quote or not quote.strip():
        return None
    folded_text = ascii_fold(text)
    tokens = ascii_fold(quote).split()
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    match = re.search(pattern, folded_text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.start(), match.end()


def _row_line_range(
    lines: list[str], body_start: int, quote: str
) -> tuple[int, int] | None:
    tokens = [token for token in _fold_lower(quote).split() if len(token) > 2]
    if not tokens or not lines:
        return None

    def score(line: str) -> int:
        folded = _fold_lower(line)
        return sum(1 for token in tokens if _has_token(folded, token))

    body_start = min(body_start, len(lines))
    body_scores = [score(line) for line in lines[body_start:]]
    if body_scores and max(body_scores) > 0:
        best_index = body_start + max(
            range(len(body_scores)), key=lambda index: body_scores[index]
        )
        best_score = body_scores[best_index - body_start]
        first = best_index
        last = best_index
        if best_index > body_start:
            previous = body_scores[best_index - body_start - 1]
            if previous >= max(1, best_score // 2):
                first = best_index - 1
        if best_index + 1 < len(lines):
            next_index = best_index - body_start + 1
            if next_index < len(body_scores):
                following = body_scores[next_index]
                if following >= max(1, best_score // 2):
                    last = best_index + 1
        return first, last

    all_scores = [score(line) for line in lines]
    if not all_scores or max(all_scores) == 0:
        return None
    best_index = max(range(len(all_scores)), key=lambda index: all_scores[index])
    return best_index, best_index


def _locate_row_lines(
    full_lines: list[str], row_lines: list[str], start_hint: int
) -> tuple[int, int] | None:
    """Map the row lines of a table block back onto the full evidence text."""
    if not row_lines:
        return None
    target = _fold_lower(row_lines[0].strip())
    start_index = None
    for index in range(start_hint, len(full_lines)):
        if _fold_lower(full_lines[index].strip()) == target:
            start_index = index
            break
    if start_index is None:
        return None
    for offset, raw in enumerate(row_lines[1:], start=1):
        if start_index + offset >= len(full_lines):
            return None
        if _fold_lower(full_lines[start_index + offset].strip()) != _fold_lower(
            raw.strip()
        ):
            return None
    return start_index, start_index + len(row_lines) - 1


def _line_index_at(full_lines: list[str], evidence_text: str, offset: int) -> int:
    position = 0
    for index, line in enumerate(evidence_text.splitlines(keepends=True)):
        if position >= offset:
            return index
        position += len(line)
    return len(full_lines) - 1


def _extend_upward(
    full_lines: list[str], first_index: int, block_rows: list[str]
) -> int:
    """Walk up into the caption / column-header lines above a table body row.

    Stops at other body rows (lines ending in a value), at prose lines that end
    a sentence, and at blank lines; at most three lines are added.
    """
    extension = 0
    while first_index > 0 and extension < 3:
        previous = full_lines[first_index - 1].strip()
        if not previous:
            break
        in_block_rows = any(
            _fold_lower(previous) == _fold_lower(row.strip())
            for row in block_rows
        )
        ends_with_value = bool(re.search(r"\d\s*$", previous))
        caption_line = bool(_TABLE_CAPTION_RE.match(previous))
        prose_end = bool(re.search(r"[.!?]\s*$", previous))
        if in_block_rows or ends_with_value or (prose_end and not caption_line):
            break
        first_index -= 1
        extension += 1
    return first_index


def _table_header_regions(evidence_text: str) -> list[str]:
    """Caption / column-header lines of every detected table.

    These lines describe the whole table (which cells, which columns), not a
    single row: they are document-level facts that may legitimately fall back
    to a value quoted outside the table body.
    """
    out: list[str] = []
    full_lines = evidence_text.splitlines()
    for block in detect_table_blocks(evidence_text):
        if block.caption:
            out.append(block.caption)
        out.extend(block.header)
        if not block.caption and not block.header and block.rows:
            hint = _line_index_at(full_lines, evidence_text, block.start)
            located = _locate_row_lines(full_lines, [block.rows[0]], hint)
            if located is not None:
                first_index, _last_index = located
                header_start = _extend_upward(
                    full_lines, first_index, block.rows
                )
                if header_start < first_index:
                    out.extend(full_lines[header_start:first_index])
    return out


def _table_scope(
    evidence_text: str, span: tuple[int, int], quote: str
) -> AssociationScope | None:
    start, end = span
    full_lines = evidence_text.splitlines()
    for block in detect_table_blocks(evidence_text):
        if not (block.start <= start < block.end or block.start < end <= block.end):
            continue
        block_lines = block.text.splitlines()
        body_start = (1 if block.caption else 0) + len(block.header)
        row_range = _row_line_range(block_lines, body_start, quote)
        if row_range is None:
            continue
        first_line, last_line = row_range
        row_lines = block_lines[first_line : last_line + 1]

        scope_lines: list[str] = []
        if block.caption:
            # caption-anchored block: caption + header already describe the
            # table region; row lines come from the block itself
            if block.caption:
                scope_lines.append(block.caption)
            scope_lines.extend(block.header)
            scope_lines.extend(row_lines)
            scope_lines.extend(block.footnotes)
        else:
            # numeric-run block: recover the caption / column-header lines
            # that sit directly above the rows (the cell product line, the
            # "Parameter Symbol Unit ..." line, the "Table N" caption)
            hint = _line_index_at(full_lines, evidence_text, block.start)
            located = _locate_row_lines(full_lines, row_lines, hint)
            if located is None:
                scope_lines = list(row_lines)
                scope_lines.extend(block.footnotes)
            else:
                first_index, last_index = located
                first_index = _extend_upward(full_lines, first_index, block.rows)
                scope_lines = full_lines[first_index : last_index + 1]
                scope_lines.extend(block.footnotes)
        return AssociationScope(
            text="\n".join(scope_lines),
            kind="table_row",
            quote=quote,
            table_caption=block.caption or None,
            table_header=tuple(block.header),
            table_row=" ".join(row_lines),
            rules=("table_row_scope",),
        )
    return None


def _sentence_scope(
    evidence_text: str, span: tuple[int, int], quote: str
) -> AssociationScope | None:
    spans = _split_sentences(evidence_text)
    if not spans:
        return None
    start, end = span
    start_index = next(
        (index for index, (lo, hi) in enumerate(spans) if lo <= start < hi),
        None,
    )
    end_index = next(
        (index for index, (lo, hi) in enumerate(spans) if lo < end <= hi),
        start_index,
    )
    if start_index is None or end_index is None:
        return None
    lo = spans[start_index][0]
    hi = spans[end_index][1]
    if start_index > 0:
        previous_lo, previous_hi = spans[start_index - 1]
        between = evidence_text[previous_hi:lo]
        previous = evidence_text[previous_lo:previous_hi]
        if "\n" not in between and (
            _SCOPE_CUE_RE.search(previous) or previous.rstrip().endswith(":")
        ):
            lo = previous_lo
    if end_index + 1 < len(spans):
        next_lo, next_hi = spans[end_index + 1]
        between = evidence_text[hi:next_lo]
        following = evidence_text[next_lo:next_hi]
        if "\n" not in between and _SCOPE_CUE_RE.search(following):
            hi = next_hi
    return AssociationScope(
        text=evidence_text[lo:hi],
        kind="sentence",
        quote=quote,
        rules=("sentence_scope",),
    )


def _setup_bullets(evidence_text: str) -> list[str]:
    marker = re.search(r"EXPERIMENT\s+CONDITIONS", evidence_text, re.IGNORECASE)
    if not marker:
        return []
    bullets: list[str] = []
    current: list[str] = []
    for line in evidence_text[marker.end() :].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("-"):
            if current:
                bullets.append(" ".join(current))
            current = [stripped[1:].strip()]
        elif current:
            current.append(stripped)
        else:
            current.append(stripped)
    if current:
        bullets.append(" ".join(current))
    return [bullet for bullet in bullets if bullet]


def _global_setup_text(evidence_text: str) -> str:
    """Explicitly global setup text.

    Three sources are treated as document-level: the ``EXPERIMENT CONDITIONS``
    block (a document-level setup by construction), the caption / column-header
    region of detected tables (it names the cells and columns of the whole
    table), and — outside those — only sentences with an explicit global cue
    (``all experiments``, ``throughout``, ...).
    """
    headers = _table_header_regions(evidence_text)
    setup = _setup_bullets(evidence_text)
    global_sentences: list[str] = []
    for lo, hi in _split_sentences(evidence_text):
        sentence = evidence_text[lo:hi].strip()
        if sentence and _GLOBAL_CUE_RE.search(sentence):
            global_sentences.append(sentence)
    out: list[str] = []
    seen: set[str] = set()
    for candidate in headers + setup + global_sentences:
        if candidate in seen:
            continue
        out.append(candidate)
        seen.add(candidate)
    return "\n".join(out)


def build_scope(evidence_text: str, quote: str | None) -> AssociationScope:
    """Build the local scope around a candidate quote (deterministic)."""
    span = _quote_span(evidence_text, quote)
    global_text = _global_setup_text(evidence_text)
    if span is None:
        return AssociationScope(
            text=evidence_text,
            kind="fallback",
            quote=quote,
            global_text=global_text,
            rules=("quote_unavailable",),
        )
    table = _table_scope(evidence_text, span, quote or "")
    if table is not None:
        return AssociationScope(
            text=table.text,
            kind=table.kind,
            quote=table.quote,
            global_text=global_text,
            table_caption=table.table_caption,
            table_header=table.table_header,
            table_row=table.table_row,
            rules=table.rules,
        )
    sentence = _sentence_scope(evidence_text, span, quote or "")
    if sentence is not None:
        return AssociationScope(
            text=sentence.text,
            kind=sentence.kind,
            quote=sentence.quote,
            global_text=global_text,
            rules=sentence.rules,
        )
    return AssociationScope(
        text=evidence_text,
        kind="fallback",
        quote=quote,
        global_text=global_text,
        rules=("scope_unavailable",),
    )


def _temperature_supported(text: str, value: Any) -> bool:
    try:
        target = float(value)
    except (TypeError, ValueError):
        match = _SIMPLE_NUMBER_RE.search(_norm_text(value))
        if not match:
            return False
        target = float(match.group(0).replace(",", "."))
    for match in _TEMPERATURE_LIST_RE.finditer(text):
        unit = match.group(2).lower()
        kelvin_offset = 273.15 if unit.startswith("c") else 0.0
        for raw in _SIMPLE_NUMBER_RE.findall(match.group(1)):
            try:
                kelvin = float(raw.replace(",", ".")) + kelvin_offset
            except ValueError:
                continue
            if 200.0 <= kelvin <= 400.0 and abs(kelvin - target) <= 1.0:
                return True
    return False


def _method_supported(text: str, value: Any) -> bool:
    claim = _norm_text(value)
    scope = _norm_text(text)
    for _name, keywords in _METHOD_GROUPS:
        if any(_contains_keyword(claim, keyword) for keyword in keywords):
            if any(_contains_keyword(scope, keyword) for keyword in keywords):
                return True
    # An unrecognised method word is not a measurement method: do not let an
    # arbitrary local token ("postmortem", "unknown") become a method claim.
    return False


def _protocol_supported(text: str, value: Any) -> bool:
    claim = _norm_text(value)
    scope = _norm_text(text)
    if not claim or not scope:
        return False

    checks: list[str] = []
    for match in _CRATE_FRACTION_RE.finditer(claim):
        checks.append(rf"c\s*/\s*{re.escape(match.group(1))}")
    for match in _CRATE_NUM_RE.finditer(claim):
        checks.append(
            rf"(?<![\w.]){re.escape(match.group(1))}(?![\w])\s*c\b"
        )
    for match in _DURATION_RE.finditer(claim):
        number = match.group(1)
        unit = match.group(2).lower()
        unit_char = "h" if unit.startswith("h") else "m"
        checks.append(rf"{re.escape(number)}\s*{unit_char}")
    if checks:
        return all(re.search(pattern, scope) for pattern in checks)

    for _name, keywords in _PROTOCOL_GROUPS:
        if any(_contains_keyword(claim, keyword) for keyword in keywords):
            if any(_contains_keyword(scope, keyword) for keyword in keywords):
                return True
    return False


def _protocol_cue_present(text: str) -> bool:
    normalised = _norm_text(text)
    if _CRATE_FRACTION_RE.search(normalised) or _CRATE_NUM_RE.search(normalised):
        return True
    return any(
        _contains_keyword(normalised, keyword)
        for _name, keywords in _PROTOCOL_GROUPS
        for keyword in keywords
    )


# mirrors the scorer's two SOC detection forms ("50% SOC", "SOC ... 50") so a
# neutralised claim is invisible to _context_slice
_SOC_CLAIM_RE = re.compile(
    r"\d{1,3}(?:\.\d+)?\s*%\s*(?:soc|state[- ]of[- ]charge)"
    r"|soc[^0-9]{0,12}\d{1,3}(?:\.\d+)?",
    re.IGNORECASE,
)


def _strip_soc_context(context: Any) -> Any:
    """Remove unsupported SOC clauses from the free-text context."""
    text = str(context or "")
    if not text:
        return context
    parts = re.split(r"(?<=[.;,])\s+|\s+and\s+", text, flags=re.IGNORECASE)
    kept = [part for part in parts if part and not _SOC_CLAIM_RE.search(part)]
    if not kept:
        return "SOC not stated in the evidence."
    joined = " ".join(kept)
    if _SOC_CLAIM_RE.search(joined):
        joined += " SOC not stated in the evidence."
    return joined


def _strip_protocol_context(context: Any) -> Any:
    """Remove unsupported protocol clauses from the free-text context.

    SOC statements inside the same sentence are preserved: only the protocol
    clause is neutralised. If any protocol cue survives the clause split, an
    explicit abstention is appended so the scorer reports ``not_stated``.
    """
    text = str(context or "")
    if not text:
        return context
    parts = re.split(r"(?<=[.;,])\s+|\s+and\s+", text, flags=re.IGNORECASE)
    kept = [part for part in parts if part and not _protocol_cue_present(part)]
    joined = " ".join(kept) if kept else ""
    soc_match = re.search(
        r"\d{1,3}(?:\.\d+)?\s*%\s*(?:soc|state[- ]of[- ]charge)",
        text,
        re.IGNORECASE,
    )
    if soc_match and soc_match.group(0).lower() not in joined.lower():
        joined = f"{joined} {soc_match.group(0)}".strip()
    if not joined.strip():
        return "protocol not stated in the evidence."
    if _protocol_cue_present(joined):
        joined += " protocol not stated in the evidence."
    return joined


def association_support(
    scope: AssociationScope,
    field_name: str,
    value: Any,
    *,
    method: Any = None,
) -> AssociationResult:
    """Check one condition against the local scope (deterministic)."""
    if _is_missing(value):
        return AssociationResult(False, "local", "missing_value")

    if field_name == "method" and _norm_text(value).strip(" .,:;") in _COLUMN_LABELS:
        return AssociationResult(False, "local", "column_label_not_method")

    if scope.kind == "fallback":
        supported = _field_supported(scope.text, field_name, value, method=method)
        rule = (
            "quote_unavailable_trace"
            if supported
            else "quote_unavailable_unsupported"
        )
        return AssociationResult(supported, "fallback", rule)

    if _field_supported(scope.text, field_name, value, method=method):
        return AssociationResult(True, "local", f"local_{field_name}")

    if field_name in _GLOBAL_FALLBACK_FIELDS and scope.global_text:
        if _field_supported(
            scope.global_text, field_name, value, method=method
        ):
            return AssociationResult(True, "document", "global_cue")

    if field_name == "protocol" and scope.global_text:
        method_text = _norm_text(method)
        if "gitt" in method_text:
            for line in scope.global_text.splitlines():
                if "gitt" in _norm_text(line) and _protocol_supported(line, value):
                    return AssociationResult(
                        True, "document", "global_protocol_same_gitt_method"
                    )

    return AssociationResult(
        False, "local", f"not_in_local_scope_{field_name}"
    )


def _field_supported(
    text: str, field_name: str, value: Any, *, method: Any = None
) -> bool:
    if field_name == "temperature_k":
        return _temperature_supported(text, value)
    if field_name == "method":
        return _method_supported(text, value)
    if field_name == "protocol":
        return _protocol_supported(text, value)
    return condition_in_text(text, field_name, value)


def enforce_association(
    evidence_text: str,
    candidate: Mapping[str, Any],
    scope: AssociationScope | None = None,
) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    """Apply the association discipline to one candidate.

    Returns ``(cleaned_candidate, removed_fields, transcript)``. The transcript
    records every field's verdict, scope and rule for audit.
    """
    from .benchmark_v4 import (
        CONDITION_FIELDS,
        FIELD_SOURCE,
        _context_slice,
    )

    quote = (candidate.get("source") or {}).get("quote")
    if scope is None:
        scope = build_scope(evidence_text, quote)
    cleaned = dict(candidate)
    transcript: list[dict[str, Any]] = []
    results: dict[str, AssociationResult] = {}

    for field_name in CONDITION_FIELDS:
        source_field = FIELD_SOURCE[field_name]
        value = cleaned.get(source_field)
        if field_name in ("soc", "protocol"):
            value = _context_slice(cleaned.get("context"), field_name)
        if _is_missing(value):
            continue
        result = association_support(
            scope,
            field_name,
            value,
            method=cleaned.get("measurement_method"),
        )
        results[field_name] = result
        transcript.append(
            {
                "field": field_name,
                "value": str(value),
                "supported": result.supported,
                "scope": result.scope,
                "rule": result.rule,
            }
        )

    removed: list[str] = []
    for field_name in CONDITION_FIELDS:
        result = results.get(field_name)
        if result is None or result.supported:
            continue
        if field_name == "soc":
            cleaned["context"] = _strip_soc_context(cleaned.get("context"))
            removed.append(field_name)
        elif field_name == "protocol":
            cleaned["context"] = _strip_protocol_context(
                cleaned.get("context")
            )
            removed.append(field_name)
        elif field_name in ("cell", "format"):
            continue  # the shared cell_config field is decided below
        else:
            cleaned[FIELD_SOURCE[field_name]] = None
            removed.append(field_name)

    cell_result = results.get("cell")
    format_result = results.get("format")
    if not (
        (cell_result is not None and cell_result.supported)
        or (format_result is not None and format_result.supported)
    ):
        cleaned["cell_config"] = None
        for field_name in ("cell", "format"):
            result = results.get(field_name)
            if result is not None and not result.supported:
                removed.append(field_name)

    removed_set = set(removed)
    for entry in transcript:
        entry["removed"] = entry["field"] in removed_set
    return cleaned, removed, transcript


def apply_association_discipline(
    evidence_text: str, candidates: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Verification pass + association discipline over one item's candidates.

    Returns ``(cleaned_candidates, stats)``; the stats expose the scope
    fallback rate and the rule counts so the effect is auditable rather than
    hidden.
    """
    cleaned: list[dict[str, Any]] = []
    dropped_total = 0
    n_quote_unsupported = 0
    n_fallback = 0
    rule_counts: dict[str, int] = {}

    for candidate in candidates:
        quote = (candidate.get("source") or {}).get("quote")
        supported = (
            verify_quote_in_evidence(quote, evidence_text) if quote else False
        )
        c = dict(candidate)
        c["_quote_in_evidence"] = supported
        if not supported:
            n_quote_unsupported += 1
        scope = build_scope(evidence_text, quote)
        if scope.kind == "fallback":
            n_fallback += 1
        cleaned_candidate, removed, transcript = enforce_association(
            evidence_text, c, scope
        )
        cleaned_candidate["_dropped_conditions"] = removed
        cleaned_candidate["_association"] = transcript
        cleaned_candidate["_association_scope"] = scope.kind
        dropped_total += len(removed)
        for entry in transcript:
            if not entry["supported"]:
                rule = entry["rule"]
                rule_counts[rule] = rule_counts.get(rule, 0) + 1
        cleaned.append(cleaned_candidate)

    stats = {
        "n_dropped_conditions": dropped_total,
        "n_quote_not_in_evidence": n_quote_unsupported,
        "quote_in_evidence_rate": (
            1.0 - n_quote_unsupported / len(candidates)
            if candidates
            else None
        ),
        "association_fallback_rate": (
            n_fallback / len(candidates) if candidates else None
        ),
        "association_rule_counts": rule_counts,
    }
    return cleaned, stats
