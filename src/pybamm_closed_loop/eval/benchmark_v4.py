"""Private v4 benchmark: condition-retrieval and condition-association scoring.

The v4 benchmark (private, see ``docs/ROADMAP_V0.2.md``) asks a different
question from v3: *given the retrieved evidence, does the system recover the
experimental conditions under which a literature value was reported?*

Design commitments:

- **Missing conditions are explicit.** A gold field is either a value or the
  string ``"not_stated"``. An extraction that invents a condition where the
  source states none scores **zero** for that field — it is never rewarded.
- **The schema is unchanged** (P0–P4 frozen): conditions are read from the
  existing fields — ``temperature`` → temperature, ``material`` → chemistry,
  ``cell_config`` → cell product / format, ``measurement_method`` → method,
  ``context`` → SOC and protocol.
- Scoring is deterministic, auditable and per-field, with every field's verdict
  reported so a mismatch can be traced.

The fixture itself is private (``data/private_v4/``); this module is public so
anybody can re-run the evaluation against their own private fixture.
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

NOT_STATED = "not_stated"

# gold condition field -> where the extracted value is read from
FIELD_SOURCE: dict[str, str] = {
    "chemistry": "material",
    "cell": "cell_config",
    "format": "cell_config",
    "temperature_k": "temperature",
    "soc": "context",
    "method": "measurement_method",
    "protocol": "context",
}

CONDITION_FIELDS: tuple[str, ...] = (
    "chemistry",
    "cell",
    "format",
    "temperature_k",
    "soc",
    "method",
    "protocol",
)


@dataclass
class V4Item:
    """One private v4 item (condition-focused)."""

    item_id: str
    category: str
    document_id: str
    probe: str
    parameter: Mapping[str, Any]
    gold_conditions: Mapping[str, str]
    not_stated_fields: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "category": self.category,
            "document_id": self.document_id,
            "probe": self.probe,
            "parameter": dict(self.parameter),
            "gold_conditions": dict(self.gold_conditions),
            "not_stated_fields": list(self.not_stated_fields),
            "evidence": dict(self.evidence),
            "notes": self.notes,
        }


def load_items(path: str | Path) -> list[V4Item]:
    """Load a v4 fixture (JSONL)."""
    items: list[V4Item] = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        items.append(
            V4Item(
                item_id=d["item_id"],
                category=d["category"],
                document_id=d["document_id"],
                probe=d["probe"],
                parameter=d["parameter"],
                gold_conditions=d["gold_conditions"],
                not_stated_fields=tuple(d.get("not_stated_fields", [])),
                evidence=d.get("evidence", {}),
                notes=d.get("notes", ""),
            )
        )
    return items


# ---------------------------------------------------------------------------
# field matching
# ---------------------------------------------------------------------------
_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _norm(text: Any) -> str:
    return " ".join(str(text or "").lower().replace("−", "-").split())


def _as_number(text: Any) -> float | None:
    if isinstance(text, (int, float)):
        return float(text)
    m = _NUM_RE.search(_norm(text).replace(",", "."))
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _keyword_hit(extracted: Any, gold: Any) -> bool:
    """True when the extracted text carries the gold keyword(s).

    Gold strings may list alternatives separated by ``|`` (any one is
    accepted) and may use ``*`` as a wildcard.
    """
    ext = _norm(extracted)
    if not ext:
        return False
    for alternative in str(gold).split("|"):
        alt = _norm(alternative)
        if not alt:
            continue
        # "+" separates tokens that must ALL be present ("nca+graphite")
        tokens = [t for t in alt.split("+") if t]
        if not tokens:
            continue
        ok = True
        for token in tokens:
            if "*" in token:
                pattern = "".join(re.escape(part) for part in token.split("*"))
                if not re.search(pattern, ext):
                    ok = False
                    break
            elif token not in ext:
                ok = False
                break
        if ok:
            return True
    return False


def match_field(name: str, gold: Any, extracted: Any) -> bool:
    """Compare one gold condition field with the extracted value.

    - gold ``not_stated``: the extraction must not supply a value.
    - temperature: numeric comparison (1 K tolerance).
    - soc: numeric comparison of the percentage when both are numeric, else
      keyword matching.
    - other fields: keyword matching against the gold alternatives.
    """
    gold_missing = (gold is None) or (str(gold).strip().lower() == NOT_STATED)
    extracted_missing = extracted is None or _norm(extracted) in (
        "",
        "unresolved",
        "not stated",
        "not_stated",
        "unknown",
    )
    if gold_missing:
        return extracted_missing
    if extracted_missing:
        return False
    if name == "temperature_k":
        g = _as_number(gold)
        e = _as_number(extracted)
        if g is None or e is None:
            return _keyword_hit(extracted, gold)
        return abs(g - e) <= 1.0
    if name == "soc":
        g = _as_number(gold)
        e = _as_number(extracted)
        if g is not None and e is not None:
            return abs(g - e) <= 2.0
        return _keyword_hit(extracted, gold)
    return _keyword_hit(extracted, gold)


def _gold_values(gold: Any) -> list[float]:
    """All numeric values a gold entry allows (a gold may list alternatives)."""
    if gold is None:
        return []
    if isinstance(gold, (int, float)) and not isinstance(gold, bool):
        return [float(gold)]
    text = str(gold)
    nums = re.findall(r"[-+]?\d+(?:[.,]\d+)?(?:\s*[eE]\s*[-+]?\d+)?", text)
    out: list[float] = []
    for n in nums:
        try:
            out.append(float(n.replace(",", ".").replace(" ", "")))
        except ValueError:
            continue
    return out


def _value_matches_gold(candidate: Mapping[str, Any], gold_values: Sequence[float]) -> bool:
    value = candidate.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    for gv in gold_values:
        if gv == 0:
            if abs(value) < 1e-30:
                return True
            continue
        rel = abs(value - gv) / abs(gv)
        if rel <= 1e-3:
            return True
        if _same_magnitude(float(value), gv):
            return True
    return False


def _name_overlap(candidate: Mapping[str, Any], gold_name: str) -> float:
    name = _norm(candidate.get("parameter_name", ""))
    gold_tokens = set(gold_name.split())
    if not gold_tokens:
        return 0.0
    return len(gold_tokens & set(name.split())) / len(gold_tokens)


def _candidate_fields(
    item: V4Item, candidate: Mapping[str, Any]
) -> dict[str, bool]:
    """Per-condition-field verdicts for one candidate."""
    fields: dict[str, bool] = {}
    for fname in CONDITION_FIELDS:
        gold = item.gold_conditions.get(fname, NOT_STATED)
        source_field = FIELD_SOURCE[fname]
        extracted = candidate.get(source_field)
        if fname in ("soc", "protocol"):
            extracted = _context_slice(candidate.get("context"), fname)
        fields[fname] = match_field(fname, gold, extracted)
    return fields


def score_item(
    item: V4Item,
    candidates: Sequence[Mapping[str, Any]],
    abstained: bool,
) -> dict[str, Any]:
    """Score one v4 item.

    The system is asked for the parameter(s) it can find; it is **not** told
    which value is the target. The scorer therefore looks for the candidate
    that carries a gold value **and** the best condition set, and reports that
    candidate's per-field verdicts. This measures condition *association*:
    a correct value with wrong (or invented) conditions still scores zero.
    """
    if not candidates:
        return {
            "item_id": item.item_id,
            "category": item.category,
            "abstained": abstained,
            "n_candidates": 0,
            "fields": {},
            "field_hits": 0,
            "field_total": len(CONDITION_FIELDS),
            "condition_score": 0.0,
            "parameter_value_ok": False,
            "parameter_unit_ok": False,
            "value_found": False,
            "invented_conditions": [],
        }

    gold_values = _gold_values(item.parameter.get("value"))
    gold_name = _norm(item.parameter.get("name", ""))

    scored = []
    for cand in candidates:
        fields = _candidate_fields(item, cand)
        scored.append(
            {
                "candidate": cand,
                "fields": fields,
                "hits": sum(1 for v in fields.values() if v),
                "name_overlap": _name_overlap(cand, gold_name),
                "value_match": _value_matches_gold(cand, gold_values),
            }
        )

    value_matched = [s for s in scored if s["value_match"]]
    pool = value_matched or scored
    best = max(pool, key=lambda s: (s["hits"], s["name_overlap"]))

    fields = best["fields"]
    hits = best["hits"]
    invented = [
        fname
        for fname, ok in fields.items()
        if not ok
        and str(item.gold_conditions.get(fname, NOT_STATED)).strip().lower() == NOT_STATED
        and not _is_missing(best["candidate"].get(FIELD_SOURCE[fname]))
    ]

    cand = best["candidate"]
    value_ok = best["value_match"]
    unit_ok = _unit_match(cand.get("unit"), item.parameter.get("unit"))

    return {
        "item_id": item.item_id,
        "category": item.category,
        "abstained": abstained,
        "n_candidates": len(candidates),
        "fields": fields,
        "field_hits": hits,
        "field_total": len(CONDITION_FIELDS),
        "condition_score": hits / len(CONDITION_FIELDS),
        "parameter_value_ok": value_ok,
        "parameter_unit_ok": unit_ok,
        "value_found": bool(value_matched),
        "invented_conditions": invented,
    }


def _is_missing(value: Any) -> bool:
    return value is None or _norm(value) in ("", "unresolved", "not stated", "not_stated", "unknown")


# A protocol claim in free-text context must be *stated*, not merely present
# as words: an abstention ("measurement protocol are not stated") or a
# context with no protocol cue at all (e.g. an SOC-only sentence) reports no
# protocol. Treating any non-empty context as a protocol claim counted the
# model's correct abstentions as invented conditions (measured scorer
# false-positive: 94 of 110 invented claims were of this kind).
_PROTOCOL_ABSTENTION_RE = re.compile(
    r"(protocol[^.;]{0,40}not\s+(?:stated|given|reported|provided|known"
    r"|available|mentioned)"
    r"|no\s+(?:measurement\s+)?protocol"
    r"|without\s+(?:a\s+)?(?:stated\s+)?protocol"
    r"|protocol\s+(?:is\s+)?unknown)",
    re.IGNORECASE,
)
_PROTOCOL_CUE_RE = re.compile(
    r"(c/\d|c-rate|\b\d+(?:\.\d+)?\s*c\b|\bgitt\b|\beis\b|\bpeis\b"
    r"|cc-?cv|galvanostatic|potentiostatic|\bpulse\b|\brest(?:ing)?\b"
    r"|current\s+interrupt|\bocv\b|cut-?off|\bcharged\s+at\b"
    r"|\bdischarged\s+at\b|charge\s+rate|discharge\s+rate"
    r"|\bcycle(?:s|d)?\s+at\b)",
    re.IGNORECASE,
)


def _context_slice(context: Any, fname: str) -> Any:
    """Pull the SOC or protocol part out of the free-text context.

    ``protocol`` is only reported when the context actually states one: an
    explicit abstention or a context without any protocol cue yields ``None``
    (i.e. "not stated"). Caveat: a bare ``"25 C"`` temperature spelling can
    read as a C-rate cue; the extraction prompt mandates Kelvin, so this is
    accepted and documented rather than pattern-matched away.
    """
    text = _norm(context)
    if not text:
        return None
    if fname == "soc":
        m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:soc|state[- ]of[- ]charge)", text)
        if m:
            return m.group(1)
        m = re.search(r"soc[^0-9]{0,12}(\d{1,3}(?:\.\d+)?)", text)
        return m.group(1) if m else None
    # protocol: claim only when stated (cue present, not negated)
    if not _PROTOCOL_CUE_RE.search(text):
        return None
    if _PROTOCOL_ABSTENTION_RE.search(text):
        return None
    return context


def _same_magnitude(a: float, b: float) -> bool:
    """Values printed in different exponents (e.g. 9.61e-15 vs 9.61·10−15)."""
    if a == 0 or b == 0:
        return a == b
    return abs(a - b) / abs(b) <= 1e-3 or (
        abs(a) / abs(b) < 100 and abs(b) / abs(a) < 100 and _ratio_close(a, b)
    )


def _ratio_close(a: float, b: float) -> bool:
    import math

    if a == 0 or b == 0:
        return False
    ratio = abs(a / b)
    if ratio < 1:
        ratio = 1 / ratio
    exponent = round(math.log10(ratio))
    return abs(ratio - 10**exponent) / (10**exponent) <= 1e-2


def _unit_match(extracted: Any, gold: Any) -> bool:
    if not gold or not extracted:
        return False
    e = _norm(extracted).replace(" ", "").replace("·", ".").replace("−", "-")
    g = _norm(gold).replace(" ", "").replace("·", ".").replace("−", "-")
    if e == g:
        return True
    aliases = {
        "m2s-1": ("m2/s", "m2s-1", "m^2s-1", "m2.s-1"),
        "mol.l-1": ("mol/l", "moll-1", "mol.l-1"),
        "a.m-2": ("a/cm2", "ma.cm-2", "ma/cm2"),
        "kj.mol-1": ("kjmol-1", "kj/mol"),
    }
    for canon, options in aliases.items():
        if canon in g and any(o in e for o in options):
            return True
        if canon in e and any(o in g for o in options):
            return True
    return False


def _mean_optional(values: Iterable[Any]) -> float:
    vals = [v for v in values if v is not None and v == v]
    return statistics.fmean(vals) if vals else float("nan")


def aggregate(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate v4 scores overall and per category.

    Rows whose model call failed (transport error) are **excluded** from the
    scores and reported separately: a failed call is not an abstention.
    """
    all_rows = list(rows)
    rows = [r for r in all_rows if not r.get("transport_error")]
    out: dict[str, Any] = {"n_transport_errors": len(all_rows) - len(rows)}

    def block(subset: list[Mapping[str, Any]]) -> dict[str, Any]:
        if not subset:
            return {}
        n = len(subset)
        hits = sum(r["field_hits"] for r in subset)
        total = sum(r["field_total"] for r in subset)
        per_field: dict[str, float] = {}
        for fname in CONDITION_FIELDS:
            vals = [r["fields"].get(fname) for r in subset if fname in r.get("fields", {})]
            if vals:
                per_field[fname] = sum(1 for v in vals if v) / len(vals)
        invented = sum(len(r.get("invented_conditions", [])) for r in subset)
        return {
            "n_items": n,
            "condition_field_accuracy": hits / total if total else float("nan"),
            "per_field_accuracy": per_field,
            "parameter_value_accuracy": sum(1 for r in subset if r["parameter_value_ok"]) / n,
            "value_found_rate": sum(1 for r in subset if r.get("value_found")) / n,
            "parameter_unit_accuracy": sum(1 for r in subset if r["parameter_unit_ok"]) / n,
            "invented_condition_rate": invented / n,
            "abstention_rate": sum(1 for r in subset if r["abstained"]) / n,
            "mean_dropped_conditions": (
                statistics.fmean([r.get("n_dropped_conditions", 0) for r in subset])
                if subset
                else float("nan")
            ),
            "quote_in_evidence_rate": _mean_optional(
                [r.get("quote_in_evidence_rate") for r in subset]
            ),
            "raw_condition_field_accuracy": (
                sum(r.get("raw_field_hits", 0) for r in subset) / total
                if total
                else float("nan")
            ),
            "raw_invented_condition_rate": (
                sum(len(r.get("raw_invented_conditions", [])) for r in subset) / n
                if n
                else float("nan")
            ),
        }

    out["all"] = block(rows)
    for category in sorted({r["category"] for r in rows}):
        out[f"category:{category}"] = block([r for r in rows if r["category"] == category])
    return out


# ---------------------------------------------------------------------------
# v4 extraction prompt (P5′): same schema, conditions made explicit
# ---------------------------------------------------------------------------
_V4_PROMPT = """You are a battery-parameter extraction assistant.

You may ONLY use the EVIDENCE passages provided in the user message. Nothing is
known outside them. Missing information must be reported as UNRESOLVED; never
infer, never guess, never import knowledge from another paper.

TASK: extract the parameter value AND the experimental conditions under which
it was reported.

FIELDS (fill every field; use UNRESOLVED only where the evidence does not state it):
- parameter_name: descriptive name including electrode/side and any particle/phase qualifier.
- value: a JSON NUMBER (never a string). Convert the printed form to a plain number, e.g. "9.61·10−15" -> 9.61e-15, "1.10·10−13" -> 1.1e-13, "37.309" -> 37.309. Keep the printed significant digits; if the printed form carries a scale (e.g. "14.7·10^4"), write the number it represents.
- unit: the unit EXACTLY as printed, including any scale prefix.
- definition: 1-2 sentences describing the quantity.
- material: the active material and its composition as stated (e.g. "NCA cathode, graphite-SiOx anode").
- temperature: a JSON NUMBER in Kelvin (e.g. 298.15) when the evidence states a temperature, otherwise null. Never write "UNRESOLVED" or a string here; use null. Never infer a temperature that is not stated.
- cell_config: the cell product or configuration as stated (chemistry, format, cell type) — for example "INR21700-50E high-energy cell, 21700" or "2032 coin cell, NMC920503 half-cell vs Li".
- measurement_method: the technique used for THIS value (e.g. "GITT", "EIS", "CIM", "calculation from FIB-SEM tortuosity").
- qualifier: one of measured / fitted / calculated / assumed / unknown.
- context: 1-3 sentences stating the remaining experimental conditions of THIS value — the state of charge (SOC) window if stated, and the measurement protocol (pulse current, pulse duration, rest time, C-rate, cutoff voltages) if stated. If a condition is not stated, say so explicitly (e.g. "SOC not stated in the evidence").
- reported_uncertainty: a JSON NUMBER in the same unit as value, or null.
- source: a nested object with exactly four keys:
    "document_id": the document id exactly as given in the evidence header (never invent one),
    "page": the page number only if the evidence header shows one, otherwise null (never guess),
    "locator": the visible table/figure/equation label, or the string UNRESOLVED,
    "quote": ONE verbatim contiguous span copied character-for-character from the evidence (never splice with "...", never reorder, never summarise).

Output format: a JSON array of objects only. Do not wrap it in markdown code fences and do not add any text before or after it.

The EVIDENCE may contain several kinds of statements: the value itself (often in a parameter table), and the experimental setup (temperature, cell, protocol, SOC) stated elsewhere in the document. Use the setup statements to fill the conditions OF THIS VALUE, but only when the evidence does not contradict them.

Respond with a JSON array of objects and nothing else. If the evidence supports no parameter statement, respond with [].
"""


def build_v4_prompt() -> str:
    """The v4 extraction system prompt (schema identical to the frozen spec)."""
    return _V4_PROMPT


# ---------------------------------------------------------------------------
# deterministic numeric coercion (identical for every arm)
# ---------------------------------------------------------------------------
_MUL = r"(?:\u00b7|\u00d7|\u22c5|\u2219|\*)"


def coerce_number(value: Any) -> Any:
    """Convert a printed number into a JSON number, deterministically.

    Handles the forms that appear in extracted PDF text: "9.61\u00b710\u221215",
    "1.10 \u00d7 10\u221213", "9.61e-15", unicode minus signs, thin spaces and
    a leading "ca." (approximate). Anything that cannot be parsed with
    certainty is returned unchanged (the schema validator will then reject it,
    which is the honest outcome).

    The conversion is applied to every arm identically and is reported in the
    run summary, so it cannot favour one evidence mode.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    text = text.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u00a0", " ").replace("\u2009", " ").replace("\u202f", " ")
    text = re.sub(r"^ca\.?\s*", "", text, flags=re.IGNORECASE)
    # number with an explicit exponent marker: 9.61*10^-15
    m = re.match(
        r"^([-+]?\d+(?:[.,]\d+)?)\s*" + _MUL + r"?\s*10\s*\^?\s*([-+]?\d+)$",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        try:
            base = float(m.group(1).replace(",", "."))
            return base * (10.0 ** int(m.group(2)))
        except ValueError:
            return value
    # plain number possibly with an exponent
    m = re.match(r"^[-+]?\d+(?:[.,]\d+)?(?:\s*[eE]\s*[-+]?\d+)?$", text)
    if m:
        try:
            return float(text.replace(",", ".").replace(" ", ""))
        except ValueError:
            return value
    return value


def coerce_temperature(value: Any) -> Any:
    """Coerce a temperature field to Kelvin (number) or None."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if text.lower() in ("", "unresolved", "not stated", "not_stated", "unknown", "null", "none"):
        return None
    m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*(?:\u00b0|deg\s*|degrees?\s*)?\s*c\b", text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1).replace(",", ".")) + 273.15
        except ValueError:
            return None
    m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*k\b", text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


def coerce_candidates(candidates: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Apply the numeric coercions to extracted candidates.

    Returns (candidates, n_coerced). Applied identically to every arm.
    """
    out: list[dict[str, Any]] = []
    n_coerced = 0
    for cand in candidates:
        c = dict(cand)
        value = coerce_number(c.get("value"))
        if value is not c.get("value"):
            n_coerced += 1
        c["value"] = value
        temp = coerce_temperature(c.get("temperature"))
        if temp is not c.get("temperature"):
            n_coerced += 1
        c["temperature"] = temp
        out.append(c)
    return out, n_coerced


# ---------------------------------------------------------------------------
# evidence-grounded `not_stated` discipline (deterministic, applied to all arms)
# ---------------------------------------------------------------------------
def evidence_support(
    evidence_text: str, field_name: str, value: Any
) -> bool:
    """Is the stated condition supported by the evidence that was shown?

    A condition that the evidence does not mention is *not* evidence-grounded:
    it is either a guess or imported from the model's memory. This check
    therefore drops such statements (they become ``None``, i.e. ``not_stated``)
    instead of letting them be reported as conditions.

    The check is deterministic, arm-independent and deliberately conservative:
    it only accepts a condition when a matching trace (a number, a keyword)
    is present in the evidence text.
    """
    from ..literature.evidence import extract_conditions

    if value is None:
        return False
    text = _norm(value)
    if not text:
        return False

    if field_name == "temperature_k":
        facts = extract_conditions(evidence_text)
        candidates = [facts.temperature_k]
        if facts.temperature_k is None:
            return False
        try:
            target = float(value)
        except (TypeError, ValueError):
            return False
        return any(c is not None and abs(c - target) <= 1.0 for c in candidates)

    if field_name in ("chemistry", "cell", "format", "method"):
        haystack = _norm(evidence_text)
        # "-" separates tokens too ("INR21700-50E" -> "inr21700", "50e")
        tokens = [t for t in re.split(r"[^a-z0-9.+]+", text) if len(t) > 2]
        if not tokens:
            return False
        if field_name == "cell":
            # the generic product words carry no discriminating information; the
            # distinguishing token (e.g. "50e" vs "30t") must be present
            generic = {
                "inr21700", "21700", "18650", "cell", "cells", "cylindrical",
                "coin", "pouch", "type", "samsung", "graphite", "anode", "cathode",
                "full", "half", "laboratory", "commercial", "high", "energy",
                "power",
            }
            specific = [t for t in tokens if t not in generic]
            if specific:
                tokens = specific
        for token in tokens:
            if token in haystack:
                continue
            if field_name == "chemistry" and token in haystack:
                continue
            return False
        return True

    # SOC / protocol: the stated numbers or keywords must occur in the evidence.
    # Numbers must appear as standalone tokens (word-ish boundaries): a bare
    # substring check would match "50" inside "INR21700-50E" and wrongly
    # confirm a SOC the source never states.
    haystack = _norm(evidence_text)
    numbers = re.findall(r"\d+(?:[.,]\d+)?", text)
    if numbers:
        for n in numbers:
            needle = _norm(n).replace(",", ".")
            if re.search(rf"(?<![\w.]){re.escape(needle)}(?![\w])", haystack.replace(",", ".")):
                return True
        return False
    keywords = [t for t in re.split(r"[^a-z0-9.+-]+", text) if len(t) > 2]
    if not keywords:
        return False
    return any(k in haystack for k in keywords)


def enforce_not_stated(
    evidence_text: str, candidate: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Replace unsupported conditions with None (deterministic `not_stated`).

    Returns (cleaned_candidate, dropped_fields). Nothing else about the
    candidate is changed, and the dropped fields are reported so the effect is
    visible rather than hidden.
    """
    cleaned = dict(candidate)
    dropped: list[str] = []
    for fname in CONDITION_FIELDS:
        source_field = FIELD_SOURCE[fname]
        value = cleaned.get(source_field)
        if value is None:
            continue
        if fname in ("soc", "protocol"):
            value = _context_slice(cleaned.get("context"), fname)
            if value is None:
                continue
        if not evidence_support(evidence_text, fname, value):
            if fname in ("soc", "protocol"):
                # the context carries several statements; drop only the
                # unsupported sub-statement by neutralising it
                cleaned["context"] = _strip_context_part(cleaned.get("context"), fname)
            else:
                cleaned[source_field] = None
            dropped.append(fname)
    return cleaned, dropped


def apply_discipline(
    evidence_text: str, candidates: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Verification pass + `not_stated` discipline over one item's candidates.

    Shared by the live runner and the offline re-score path so both apply the
    identical deterministic post-processing. Returns (cleaned_candidates, stats).
    """
    from ..literature.evidence import verify_quote_in_evidence

    cleaned: list[dict[str, Any]] = []
    dropped_total = 0
    n_quote_unsupported = 0
    for cand in candidates:
        quote = (cand.get("source") or {}).get("quote")
        supported = verify_quote_in_evidence(quote, evidence_text) if quote else False
        c = dict(cand)
        c["_quote_in_evidence"] = supported
        if not supported:
            n_quote_unsupported += 1
        cleaned_cand, dropped = enforce_not_stated(evidence_text, c)
        cleaned_cand["_dropped_conditions"] = dropped
        dropped_total += len(dropped)
        cleaned.append(cleaned_cand)
    stats = {
        "n_dropped_conditions": dropped_total,
        "n_quote_not_in_evidence": n_quote_unsupported,
        "quote_in_evidence_rate": (
            1.0 - n_quote_unsupported / len(candidates) if candidates else None
        ),
    }
    return cleaned, stats


def score_with_discipline(
    item: V4Item,
    evidence_text: str,
    candidates: Sequence[Mapping[str, Any]],
    transport_error: bool,
    n_coerced: int = 0,
) -> dict[str, Any]:
    """Score one item after applying the verification + `not_stated` discipline."""
    cleaned, stats = apply_discipline(evidence_text, candidates)
    row = score_item(item, cleaned, abstained=not cleaned)
    row["transport_error"] = transport_error
    row["n_coerced"] = n_coerced
    row["evidence_chars"] = len(evidence_text)
    row.update(stats)
    row_raw = score_item(item, candidates, abstained=not candidates)
    row["raw_condition_score"] = row_raw["condition_score"]
    row["raw_field_hits"] = row_raw["field_hits"]
    row["raw_invented_conditions"] = row_raw["invented_conditions"]
    return row


def _strip_context_part(context: Any, fname: str) -> Any:
    """Remove an unsupported SOC/protocol fragment from the free-text context."""
    text = str(context or "")
    if not text:
        return context
    if fname == "soc":
        cleaned = re.sub(
            r"[^.;]*?(\d{1,3}(?:\.\d+)?)\s*%\s*(?:soc|state[- ]of[- ]charge)[^.;]*",
            "SOC not stated in the evidence",
            text,
            flags=re.IGNORECASE,
        )
        return cleaned if cleaned.strip() else text
    return text
