"""Observability join (V2.3): P2 identifiability artifacts -> dossier field 7.

Deterministic mapping from the recorded P2 studies
(``results/p2/``) to per-parameter observability assessments and a
fit/fix/measure action. Nothing here is estimated or inferred at runtime:
every number comes from a recorded artifact, every rule is a fixed threshold
recorded with its inputs (rule-firing transcript).

Assumptions (explicit, recorded in every assessment and in the run manifest):

- ``SENSITIVITY_OBSERVABILITY_THRESHOLD = 0.05`` — a parameter whose mean
  absolute *normalised* sensitivity (relative output change per relative
  parameter change) is below 0.05 under a protocol moves the observable by
  less than 5 % for an order-unity parameter change; against realistic
  voltage noise that is unobservable. The P2 study classifies the negative
  particle diffusivity this way for 0.5C/1C/2C discharge (values
  0.011/0.021/0.048), while every other studied parameter stays above it.
- ``BOOTSTRAP_REL_STD_OBSERVABILITY = 0.05`` — a parametric-bootstrap
  relative standard deviation above 5 % means the data cannot pin the
  parameter to better than ±5 % at 1 sigma.

Limitations: only the protocols actually studied in the recorded artifacts
are classified; anything else is ``NOT_ASSESSED`` (explicit, never silent).
A successful fit never proves identifiability (scientific rule 7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Collection, Iterable, Mapping

SENSITIVITY_OBSERVABILITY_THRESHOLD = 0.05
BOOTSTRAP_REL_STD_OBSERVABILITY = 0.05

STATUS_OBSERVABLE = "OBSERVABLE"
STATUS_UNOBSERVABLE = "UNOBSERVABLE"
STATUS_NOT_ASSESSED = "not_assessed"

ACTION_CALIBRATE = "CALIBRATE"
ACTION_FIX = "FIX"
ACTION_MEASURE = "MEASURE"


@dataclass(frozen=True)
class ObservabilityAssessment:
    """Observability of one parameter under the recorded protocols."""

    canonical_id: str
    pybamm_names: tuple[str, ...]
    status: str
    action: str | None
    protocols: tuple[str, ...]
    parameter_set: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    rules_fired: tuple[dict[str, Any], ...] = ()
    sources: tuple[str, ...] = ()
    note: str = ""

    def to_dossier_field(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            "protocols": list(self.protocols),
            "parameter_set": self.parameter_set,
            "metrics": self.metrics,
            "rules_fired": [dict(r) for r in self.rules_fired],
            "sources": list(self.sources),
            "note": self.note,
        }


def not_assessed(canonical_id: str, pybamm_names: Iterable[str] = ()) -> ObservabilityAssessment:
    return ObservabilityAssessment(
        canonical_id=canonical_id,
        pybamm_names=tuple(pybamm_names),
        status=STATUS_NOT_ASSESSED,
        action=None,
        protocols=(),
        note="no recorded identifiability artifact covers this parameter",
    )


def _action_for(status: str, accuracy_critical: bool) -> str | None:
    if status == STATUS_OBSERVABLE:
        return ACTION_CALIBRATE
    if status == STATUS_UNOBSERVABLE:
        return ACTION_MEASURE if accuracy_critical else ACTION_FIX
    return None


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_observability(
    p2_dir: Path,
    records: Iterable[Mapping[str, Any]],
    accuracy_critical: Collection[str] = (),
) -> dict[str, ObservabilityAssessment]:
    """Build per-parameter assessments from the recorded P2 artifacts.

    Returns assessments keyed by ``canonical_id`` for every parameter covered
    by an artifact; uncovered parameters are simply absent (callers use
    :func:`not_assessed`). Records are only read for the PyBaMM-name ->
    canonical-id mapping.
    """
    p2_dir = Path(p2_dir)
    by_pybamm_name: dict[str, str] = {}
    names_by_id: dict[str, list[str]] = {}
    for rec in records:
        cid = str(rec.get("canonical_id", ""))
        names_by_id.setdefault(cid, [])
        for pn in rec.get("pybamm_names") or []:
            by_pybamm_name[str(pn)] = cid
            names_by_id[cid].append(str(pn))

    out: dict[str, ObservabilityAssessment] = {}

    # --- P2 sensitivity study (diffusivity feasibility) -------------------
    diff = _load_json(p2_dir / "diffusivity_feasibility" / "report.json")
    if diff:
        src = str(p2_dir / "diffusivity_feasibility" / "report.json")
        per_condition = diff.get("per_condition") or {}
        protocols = tuple(sorted(per_condition))
        recorded_set = (diff.get("config") or {}).get("parameter_set")
        # collect sensitivities per PyBaMM name across protocols
        sens: dict[str, dict[str, float]] = {}
        for cond in protocols:
            block = per_condition[cond].get("mean_abs_normalized_sensitivity") or {}
            for name, value in block.items():
                sens.setdefault(str(name), {})[str(cond)] = float(value)
        for name, by_cond in sens.items():
            cid = by_pybamm_name.get(name)
            if cid is None:
                continue
            unobs = [
                c for c, s in by_cond.items()
                if s < SENSITIVITY_OBSERVABILITY_THRESHOLD
            ]
            status = (
                STATUS_UNOBSERVABLE if len(unobs) == len(by_cond) else STATUS_OBSERVABLE
            )
            rules = (
                {
                    "rule": "sensitivity_observability",
                    "threshold": SENSITIVITY_OBSERVABILITY_THRESHOLD,
                    "inputs": {"mean_abs_normalized_sensitivity": by_cond},
                    "fired": (
                        "all studied protocols below threshold -> unobservable"
                        if status == STATUS_UNOBSERVABLE
                        else "at least one protocol above threshold -> observable"
                    ),
                },
            )
            note = ""
            if status == STATUS_UNOBSERVABLE:
                note = (
                    "unobservable under the studied protocols ("
                    + "/".join(protocols)
                    + "); a literature value must be held, not fitted"
                )
            out[cid] = ObservabilityAssessment(
                canonical_id=cid,
                pybamm_names=tuple(names_by_id.get(cid, (name,))),
                status=status,
                action=_action_for(status, cid in accuracy_critical),
                protocols=protocols,
                parameter_set=recorded_set,
                metrics={"mean_abs_normalized_sensitivity": by_cond},
                rules_fired=rules,
                sources=(src,),
                note=note,
            )

    # --- P2 identifiability study (volume fractions) ----------------------
    ident = _load_json(p2_dir / "identifiability_volume_fractions" / "report.json")
    if ident:
        src = str(p2_dir / "identifiability_volume_fractions" / "report.json")
        boot = ident.get("bootstrap") or {}
        per_parameter = boot.get("per_parameter") or {}
        fim = {
            "fim_single_condition_number": (ident.get("fim_single") or {}).get("condition_number"),
            "fim_multi_condition_number": (ident.get("fim_multi") or {}).get("condition_number"),
        }
        recorded_set = None
        for key in ("recovery_config_single", "recovery_config_multi"):
            rel = (ident.get("config") or {}).get(key)
            if not rel:
                continue
            cfg_path = Path(rel)
            if not cfg_path.is_file():
                cfg_path = p2_dir.parent.parent / str(rel)
            if not cfg_path.is_file():
                cfg_path = p2_dir.parent / str(rel)
            if cfg_path.is_file():
                try:
                    import yaml
                    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                    recorded_set = cfg.get("parameter_set")
                    if isinstance(recorded_set, dict):
                        recorded_set = recorded_set.get("name")
                    if recorded_set:
                        break
                except (OSError, ValueError):
                    continue
        for name, stats in per_parameter.items():
            cid = by_pybamm_name.get(str(name))
            if cid is None:
                continue
            mean = float(stats.get("mean", float("nan")))
            std = float(stats.get("std", float("nan")))
            rel_std = std / abs(mean) if mean else float("inf")
            status = (
                STATUS_OBSERVABLE
                if rel_std <= BOOTSTRAP_REL_STD_OBSERVABILITY
                else STATUS_UNOBSERVABLE
            )
            rules = (
                {
                    "rule": "bootstrap_observability",
                    "threshold": BOOTSTRAP_REL_STD_OBSERVABILITY,
                    "inputs": {"bootstrap_mean": mean, "bootstrap_std": std,
                               "rel_std": rel_std},
                    "fired": (
                        "bootstrap rel std within threshold -> observable"
                        if status == STATUS_OBSERVABLE
                        else "bootstrap rel std above threshold -> unobservable"
                    ),
                },
            )
            metrics = {
                "bootstrap": {"mean": mean, "std": std, "rel_std": rel_std},
                "truth": stats.get("truth"),
            }
            metrics.update(fim)
            out[cid] = ObservabilityAssessment(
                canonical_id=cid,
                pybamm_names=tuple(names_by_id.get(cid, (str(name),))),
                status=status,
                action=_action_for(status, cid in accuracy_critical),
                protocols=("1C", "0.5C+1C+2C"),
                parameter_set=recorded_set,
                metrics=metrics,
                rules_fired=rules,
                sources=(src,),
                note=(
                    "parameter is pinned by the recorded synthetic recovery "
                    "study (bootstrap std relative to the estimate); a "
                    "successful fit alone does not prove identifiability"
                ),
            )
    return out
