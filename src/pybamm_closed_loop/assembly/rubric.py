"""The applicability rubric: hand-set, weighted, fully auditable.

Every dimension is scored in [0, 1]; the total is the weighted sum (weights
sum to 1.00). Each score comes from an explicit, named rule, and the rule
records the inputs it used, so a reviewer can re-derive or contest any score.

Three rules are **blocking** (the candidate is excluded for that target):
  - chemistry family not applicable to the target,
  - quote verification failed (fabricated / unverifiable quote),
  - parameter not declarable in the model (function-valued parameter).

Unknown facts never block: they score 0.5 with a recorded warning, so missing
evidence lowers confidence instead of silently deciding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .schema import CandidateValue, MethodClass, TargetSpecification
from ..registry.textnorm import ascii_fold

# ---------------------------------------------------------------------------
# dimension weights (hand-set; sum = 1.00)
# ---------------------------------------------------------------------------
# electrolyte-family parameters weight the electrolyte instead of the electrode
# chemistry (the deciding condition differs).
ELECTROLYTE_WEIGHTS: dict[str, float] = {
    "chemistry": 0.06,
    "temperature": 0.12,
    "method": 0.16,
    "evidence": 0.12,
    "soc": 0.08,
    "format": 0.04,
    "agreement": 0.04,
    "model": 0.05,
    "cell_product": 0.14,
    "electrolyte": 0.19,
}

DEFAULT_WEIGHTS: dict[str, float] = {
    # rubric v2 (2026-11-16): the cell product and the electrolyte/medium were
    # missing, so values measured on a *different cell* (or with a different
    # electrolyte) could outrank the demonstrator's own value. Weights are
    # re-balanced to keep the sum at 1.00.
    "chemistry": 0.22,
    "temperature": 0.12,
    "method": 0.16,
    "evidence": 0.12,
    "soc": 0.08,
    "format": 0.04,
    "agreement": 0.04,
    "model": 0.05,
    "cell_product": 0.12,
    "electrolyte": 0.05,
}

_NMC_COMPOSITION_RE = re.compile(r"nmc[^0-9]{0,3}(\d{3})")


def _electrolyte_tokens(text: str) -> set[str]:
    """Distinguishing tokens of an electrolyte description (salt, ratio, additive)."""
    t = ascii_fold(str(text)).lower()
    tokens: set[str] = set()
    for salt in ("lipf6", "lifipf6", "lifsi", "libf4", "litfsi"):
        if salt in t:
            tokens.add(salt)
    for ratio in ("3:7", "1:1", "2:1", "4:1"):
        if ratio in t:
            tokens.add("ratio" + ratio)
    if "vc" in t and "vinylene" in t:
        tokens.add("vc")
    return tokens


def _electrolyte_key(text: str) -> str | None:
    """A short, comparable key for an electrolyte description (salt only)."""
    t = ascii_fold(str(text)).lower()
    for salt in ("lipf6", "lifipf6", "lifsi", "libf4", "litfsi"):
        if salt in t:
            return salt
    return None


def _nmc_composition(families: Iterable[str], text: str | None) -> str | None:
    """Return the NMC composition number (e.g. '811') if it can be read."""
    joined = " ".join(families) + " " + ("" if text is None else str(text))
    m = _NMC_COMPOSITION_RE.search(joined.lower())
    return m.group(1) if m else None


@dataclass(frozen=True)
class Dimension:
    name: str
    weight: float
    description: str


@dataclass(frozen=True)
class Rule:
    """One named, auditable rule inside a dimension."""

    id: str
    dimension: str
    score: float
    reason: str
    blocking: bool = False


@dataclass
class RubricOutcome:
    """Result of evaluating one candidate against one target."""

    candidate: CandidateValue
    total: float
    dimension_scores: dict[str, float] = field(default_factory=dict)
    fired: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 6),
            "dimension_scores": {k: round(v, 6) for k, v in self.dimension_scores.items()},
            "fired": self.fired,
            "blockers": self.blockers,
            "warnings": self.warnings,
        }


class Rubric:
    """Versioned, hand-set rubric.

    ``version`` is recorded in every decision and in the approval record, so a
    decision can always be traced to the rule set that produced it.
    """

    def __init__(
        self,
        version: str,
        weights: dict[str, float] | None = None,
        dimensions: Sequence[Dimension] | None = None,
        review_margin: float = 0.10,
        method_divergence_margin: float = 0.10,
        electrolyte_weights: dict[str, float] | None = None,
        rules: Sequence[Rule] | None = None,
    ) -> None:
        self.version = version
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        self.electrolyte_weights = dict(
            electrolyte_weights or ELECTROLYTE_WEIGHTS
        )
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"rubric weights must sum to 1.0 (got {total})")
        e_total = sum(self.electrolyte_weights.values())
        if abs(e_total - 1.0) > 1e-9:
            raise ValueError(
                f"electrolyte rubric weights must sum to 1.0 (got {e_total})"
            )
        if set(self.electrolyte_weights) != set(self.weights):
            raise ValueError(
                "electrolyte_weights must cover the same dimensions as weights"
            )
        self.dimensions = list(
            dimensions
            or [
                Dimension("chemistry", self.weights["chemistry"], "active-material / cell chemistry applicability"),
                Dimension("temperature", self.weights["temperature"], "temperature of the measurement vs target"),
                Dimension("method", self.weights["method"], "how the value was obtained"),
                Dimension("evidence", self.weights["evidence"], "evidence integrity (verified quote, locator)"),
                Dimension("soc", self.weights["soc"], "state of charge window"),
                Dimension("format", self.weights["format"], "cell format / geometry"),
                Dimension("agreement", self.weights["agreement"], "agreement with other sources"),
                Dimension("model", self.weights["model"], "declarability in the target model"),
                Dimension(
                    "cell_product",
                    self.weights["cell_product"],
                    "cell product / build the value was measured on",
                ),
                Dimension(
                    "electrolyte",
                    self.weights["electrolyte"],
                    "electrolyte / medium the value applies to",
                ),
            ]
        )
        self.review_margin = review_margin
        self.method_divergence_margin = method_divergence_margin
        self.rules = list(rules or [])

    # -- helpers ---------------------------------------------------------
    def _fire(
        self,
        outcome: RubricOutcome,
        dimension: str,
        score: float,
        reason: str,
        inputs: dict[str, Any] | None = None,
        blocking: bool = False,
    ) -> None:
        outcome.fired.append(
            {
                "dimension": dimension,
                "score": round(score, 6),
                "reason": reason,
                "inputs": inputs or {},
                "blocking": blocking,
            }
        )
        if blocking:
            outcome.blockers.append({"dimension": dimension, "reason": reason, "inputs": inputs or {}})

    # -- dimensions ------------------------------------------------------
    def _score_chemistry(
        self, cand: CandidateValue, target: TargetSpecification, outcome: RubricOutcome
    ) -> float:
        fam = set(cand.conditions.chemistry_families)
        target_fam = set(target.chemistry_families)
        if not fam:
            self._fire(outcome, "chemistry", 0.5, "chemistry not stated in the evidence conditions",
                       {"candidate_families": []})
            outcome.warnings.append("chemistry unknown")
            return 0.5
        if not (fam & target_fam):
            self._fire(
                outcome,
                "chemistry",
                0.0,
                "chemistry family not applicable to the target",
                {"candidate_families": sorted(fam), "target_families": sorted(target_fam)},
                blocking=True,
            )
            return 0.0
        cand_comp = _nmc_composition(fam, cand.conditions.raw.get("chemistry") if cand.conditions.raw else None)
        # The target composition is an explicit, auditable field (e.g. "811");
        # family labels alone cannot distinguish NMC811 from NMC111. Fall back
        # to parsing the labels only for legacy targets without that field.
        target_comp = str(target.nmc_composition) if target.nmc_composition else _nmc_composition(target_fam, None)
        if cand_comp and target_comp and cand_comp != target_comp:
            self._fire(
                outcome,
                "chemistry",
                0.25,
                "same chemistry family but different composition",
                {"candidate_nmc": cand_comp, "target_nmc": target_comp},
            )
            return 0.25
        if cand.conditions.cell_product and cand.conditions.cell_product == target.cell_product:
            self._fire(outcome, "chemistry", 1.0, "same cell product and chemistry family",
                       {"cell_product": cand.conditions.cell_product})
            return 1.0
        if cand.conditions.cell_product and cand.conditions.cell_product != target.cell_product:
            self._fire(outcome, "chemistry", 0.5, "same chemistry family, different cell product",
                       {"candidate_cell": cand.conditions.cell_product, "target_cell": target.cell_product})
            return 0.5
        self._fire(outcome, "chemistry", 0.6, "same chemistry family, cell product not stated",
                   {"candidate_families": sorted(fam)})
        return 0.6

    def _score_temperature(
        self, cand: CandidateValue, target: TargetSpecification, outcome: RubricOutcome
    ) -> float:
        t_c = cand.conditions.temperature_k
        t_t = target.temperature_k
        rng = cand.conditions.temperature_range_k
        if rng is not None and t_t is not None:
            lo, hi = rng
            if lo <= t_t <= hi:
                self._fire(outcome, "temperature", 1.0,
                           "target temperature lies inside the measured range",
                           {"range_k": [lo, hi], "target_k": t_t})
                return 1.0
            d = lo - t_t if t_t < lo else t_t - hi
            score = 0.7 if d <= 10.0 else (0.4 if d <= 25.0 else 0.15)
            self._fire(outcome, "temperature", score,
                       "target temperature outside the measured range",
                       {"range_k": [lo, hi], "target_k": t_t, "distance_k": round(d, 3)})
            return score
        if t_c is None or t_t is None:
            self._fire(outcome, "temperature", 0.5, "temperature not stated on one side",
                       {"candidate_k": t_c, "target_k": t_t})
            outcome.warnings.append("temperature unknown")
            return 0.5
        d = abs(t_c - t_t)
        if d <= 2.0:
            score, reason = 1.0, "temperature within 2 K of the target"
        elif d <= 10.0:
            score, reason = 0.7, "temperature within 10 K of the target"
        elif d <= 25.0:
            score, reason = 0.4, "temperature within 25 K of the target"
        else:
            score, reason = 0.15, "temperature far from the target"
        self._fire(outcome, "temperature", score, reason,
                   {"candidate_k": t_c, "target_k": t_t, "delta_k": round(d, 3)})
        return score

    def _score_method(self, cand: CandidateValue, outcome: RubricOutcome) -> float:
        table = {
            MethodClass.MEASURED: (1.0, "direct measurement"),
            MethodClass.CALCULATED: (0.8, "calculated from other measured quantities"),
            MethodClass.FITTED: (0.7, "fitted to data by the source"),
            MethodClass.CALIBRATED: (0.6, "tuned/calibrated value (model-consistent, not a measurement)"),
            MethodClass.ASSUMED: (0.5, "assumed / conventional value"),
            MethodClass.UNKNOWN: (0.4, "method class unknown"),
        }
        score, reason = table[cand.method_class]
        self._fire(outcome, "method", score, reason,
                   {"method_class": cand.method_class.value, "method": (cand.method or "")[:160]})
        return score

    def _score_evidence(self, cand: CandidateValue, outcome: RubricOutcome) -> float:
        if cand.quote_verified is False:
            self._fire(outcome, "evidence", 0.0,
                       "quote could not be verified against the archived source",
                       {"source_document": cand.source_document}, blocking=True)
            return 0.0
        if cand.quote_verified and cand.source_locator:
            self._fire(outcome, "evidence", 1.0, "quote verified and locator recorded",
                       {"locator": cand.source_locator})
            return 1.0
        if cand.quote_verified:
            self._fire(outcome, "evidence", 0.85, "quote verified, no locator recorded", {})
            return 0.85
        if cand.quote_present:
            self._fire(outcome, "evidence", 0.6,
                       "quote recorded but not independently verified in this pass", {})
            return 0.6
        self._fire(outcome, "evidence", 0.4, "no quote attached", {})
        return 0.4

    def _score_soc(self, cand: CandidateValue, target: TargetSpecification, outcome: RubricOutcome) -> float:
        c, t = cand.conditions.soc, target.soc
        if not c or not t:
            self._fire(outcome, "soc", 0.5, "SOC window not stated on one side",
                       {"candidate_soc": c, "target_soc": t})
            return 0.5
        if str(c).strip() == str(t).strip():
            self._fire(outcome, "soc", 1.0, "SOC window matches the target", {"soc": c})
            return 1.0
        self._fire(outcome, "soc", 0.3, "SOC window differs from the target",
                   {"candidate_soc": c, "target_soc": t})
        return 0.3

    def _score_format(self, cand: CandidateValue, target: TargetSpecification, outcome: RubricOutcome) -> float:
        c, t = cand.conditions.format, target.format
        if not c or not t:
            self._fire(outcome, "format", 0.5, "format not stated on one side",
                       {"candidate_format": c, "target_format": t})
            return 0.5
        if c == t:
            self._fire(outcome, "format", 1.0, "cell format matches the target", {"format": c})
            return 1.0
        self._fire(outcome, "format", 0.3, "cell format differs from the target",
                   {"candidate_format": c, "target_format": t})
        return 0.3

    def _score_agreement(
        self,
        cand: CandidateValue,
        siblings: Sequence[tuple[str | None, float]],
        outcome: RubricOutcome,
    ) -> float:
        others = [v for sid, v in siblings if sid != cand.source_id and v is not None]
        if not others:
            self._fire(outcome, "agreement", 0.6, "single source for this parameter", {})
            return 0.6
        if cand.canonical_value is None:
            self._fire(outcome, "agreement", 0.5, "value not in canonical units for comparison", {})
            return 0.5
        close = [v for v in others if abs(v - cand.canonical_value) <= 0.1 * abs(cand.canonical_value)]
        if close:
            self._fire(outcome, "agreement", 1.0, "an independent source reports a matching value",
                       {"n_independent": len(close)})
            return 1.0
        self._fire(outcome, "agreement", 0.35, "independent sources report differing values",
                   {"n_independent": len(others)})
        return 0.35

    def _score_cell_product(
        self, cand: CandidateValue, target: TargetSpecification, outcome: RubricOutcome
    ) -> float:
        """Cell product / build match; a *known* mismatch blocks the candidate.

        Electrode thickness, porosity, current collectors and cell areas are
        properties of one specific build: a value measured on another cell is
        not transferable, however similar the chemistry is. The comparison uses
        the cell identifiers in the free-text condition ("coin cell",
        "three-electrode", "18650", "LG M50", ...) rather than a whitelist of
        product names.
        """
        from .lexicon import cell_tokens

        c = cand.conditions.cell_product
        t = target.cell_product
        raw_cell = (cand.conditions.raw or {}).get("cell")
        tokens = cell_tokens(raw_cell) or cell_tokens(c)
        target_tokens = {tok.lower() for tok in cell_tokens(t)}

        from .lexicon import is_cell_specific

        cell_specific = is_cell_specific(cand.canonical_id)
        if tokens and target_tokens:
            matched = any(
                tok.lower() in target_tokens
                or any(tok.lower() in tt for tt in target_tokens)
                for tok in tokens
            )
            if not matched and cell_specific:
                self._fire(
                    outcome,
                    "cell_product",
                    0.0,
                    "value measured on a different cell/build (cell-specific parameter)",
                    {
                        "candidate_cell": raw_cell or c,
                        "candidate_tokens": list(tokens),
                        "target_cell": t,
                    },
                    blocking=True,
                )
                return 0.0
            if not matched:
                self._fire(
                    outcome,
                    "cell_product",
                    0.6,
                    "value measured on a different build, but the parameter is not "
                    "cell-specific",
                    {"candidate_cell": raw_cell or c, "target_cell": t},
                )
                return 0.6
            self._fire(
                outcome,
                "cell_product",
                1.0,
                "same cell build as the target",
                {"candidate_tokens": list(tokens), "target_cell": t},
            )
            return 1.0

        if c and t and c == t:
            self._fire(outcome, "cell_product", 1.0, "same cell product", {"cell": c})
            return 1.0
        self._fire(
            outcome,
            "cell_product",
            0.5,
            "cell build could not be matched to the target",
            {"candidate_cell": raw_cell or c, "target_cell": t},
        )
        return 0.5

    def _score_electrolyte(
        self, cand: CandidateValue, target: TargetSpecification, outcome: RubricOutcome
    ) -> float:
        """Electrolyte / medium match (electrolyte-level parameters)."""
        c = (cand.conditions.raw or {}).get("electrolyte")
        t = (target.electrolyte or "").strip()
        if not c or not t:
            self._fire(outcome, "electrolyte", 0.5, "electrolyte not stated on one side",
                       {"candidate": c, "target": t or None})
            return 0.5
        cn = ascii_fold(str(c)).lower()
        tn = ascii_fold(t).lower()
        if cn == tn:
            self._fire(outcome, "electrolyte", 1.0, "same electrolyte", {"electrolyte": c})
            return 1.0
        # the demonstrator's own electrolyte (salt AND solvent ratio AND
        # additive) is a stronger match than "same salt, different solvent mix"
        target_tokens = _electrolyte_tokens(t)
        candidate_tokens = _electrolyte_tokens(str(c))
        if target_tokens and target_tokens <= candidate_tokens:
            self._fire(outcome, "electrolyte", 1.0,
                       "candidate states the target electrolyte",
                       {"candidate": c})
            return 1.0
        salt = _electrolyte_key(t)
        if salt and salt in cn:
            self._fire(outcome, "electrolyte", 0.6,
                       "same salt, but the solvent mix / additive is not stated",
                       {"candidate": c, "target": t})
            return 0.6
        self._fire(outcome, "electrolyte", 0.4, "different electrolyte",
                   {"candidate": c, "target": t})
        return 0.4

    def _score_model(self, cand: CandidateValue, outcome: RubricOutcome) -> float:
        if cand.model_applicable is False:
            self._fire(outcome, "model", 0.0, "parameter is not declarable in the target model",
                       {"note": cand.model_note}, blocking=True)
            return 0.0
        if cand.model_applicable is True:
            self._fire(outcome, "model", 1.0, "parameter is declarable in the target model", {})
            return 1.0
        self._fire(outcome, "model", 0.6, "model applicability not established", {})
        return 0.6

    # -- public API ------------------------------------------------------
    def weights_for(self, parameter: str) -> dict[str, float]:
        """Weight set for a parameter family (electrolyte vs electrode)."""
        from .lexicon import parameter_family

        if parameter_family(parameter) == "electrolyte":
            return dict(self.electrolyte_weights)
        return dict(self.weights)

    def evaluate(
        self,
        candidate: CandidateValue,
        target: TargetSpecification,
        siblings: Sequence[tuple[str | None, float]] = (),
    ) -> RubricOutcome:
        """Score one candidate against one target; record every rule fired."""
        outcome = RubricOutcome(candidate=candidate, total=0.0)
        scores = {
            "chemistry": self._score_chemistry(candidate, target, outcome),
            "temperature": self._score_temperature(candidate, target, outcome),
            "method": self._score_method(candidate, outcome),
            "evidence": self._score_evidence(candidate, outcome),
            "soc": self._score_soc(candidate, target, outcome),
            "format": self._score_format(candidate, target, outcome),
            "agreement": self._score_agreement(candidate, siblings, outcome),
            "model": self._score_model(candidate, outcome),
            "cell_product": self._score_cell_product(candidate, target, outcome),
            "electrolyte": self._score_electrolyte(candidate, target, outcome),
        }
        outcome.dimension_scores = scores
        weights = self.weights_for(candidate.canonical_id)
        outcome.total = sum(weights[k] * v for k, v in scores.items())
        return outcome

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "weights": dict(self.weights),
            "electrolyte_weights": dict(self.electrolyte_weights),
            "review_margin": self.review_margin,
            "method_divergence_margin": self.method_divergence_margin,
            "dimensions": [
                {"name": d.name, "weight": d.weight, "description": d.description}
                for d in self.dimensions
            ],
        }
