"""Declarative, multi-chemistry target-spec catalog loading.

A single target spec (``configs/v2/target_lgm50.yaml``) was the v0.2 status quo.
This module adds deterministic loading of a *catalog* of target specs so that
several chemistries can be addressed by name. It performs only checks that can
be made from the YAML and the auditable lexicon; PyBaMM set names, options and
chemistry fields are verified separately by ``pybamm_engine`` (see the v3
integration tests).
"""

from __future__ import annotations

from pathlib import Path

from ..assembly import TargetSpecification
from ..assembly.lexicon import CHEMISTRY_FAMILIES
from ..cli_app.inputs import load_target

# Recognised model names: mirrored from pybamm_engine.config.ModelConfig (the
# pinning itself is checked in the engine, not here).
KNOWN_MODELS = ("DFN", "SPMe", "SPM")

# configs/v3 sits at <repo>/configs/v3 relative to this src-layout package.
DEFAULT_CATALOG_DIR = Path(__file__).resolve().parents[3] / "configs" / "v3"


class TargetSpecError(ValueError):
    """Raised when a target-spec catalog is inconsistent or incomplete."""


def default_catalog_dir() -> Path:
    """Return the repository's v3 target-spec directory."""
    return DEFAULT_CATALOG_DIR


def load_target_catalog(directory: str | Path | None = None) -> tuple[TargetSpecification, ...]:
    """Load all YAML target specs in ``directory`` in deterministic order.

    Validation is intentionally conservative: duplicate ids, unknown chemistry
    family labels, unknown model names and empty parameter-set names are errors.
    Nothing is inferred or defaulted from a chemistry family.
    """
    root = Path(directory) if directory is not None else DEFAULT_CATALOG_DIR
    if not root.is_dir():
        raise TargetSpecError(f"target-spec directory not found: {root}")

    # ``*.meta.yaml`` files are auxiliary coverage/provenance records, not
    # target specs; they are deliberately excluded from the catalog.
    paths = sorted(
        p
        for p in (*root.glob("*.yaml"), *root.glob("*.yml"))
        if not p.name.endswith(".meta.yaml") and not p.name.endswith(".meta.yml")
    )
    if not paths:
        raise TargetSpecError(f"no target specs found in {root}")

    specs: list[TargetSpecification] = []
    seen_ids: set[str] = set()
    for path in paths:
        try:
            spec = load_target(path)
        except SystemExit as exc:
            raise TargetSpecError(f"{path}: {exc}") from exc
        if spec.target_id in seen_ids:
            raise TargetSpecError(f"duplicate target_id '{spec.target_id}' in {root}")
        seen_ids.add(spec.target_id)
        if not spec.chemistry_families:
            raise TargetSpecError(f"{path}: chemistry_families must not be empty")
        unknown = sorted(set(spec.chemistry_families) - set(CHEMISTRY_FAMILIES))
        if unknown:
            raise TargetSpecError(f"{path}: unknown chemistry family/families: {unknown}")
        if spec.model not in KNOWN_MODELS:
            raise TargetSpecError(f"{path}: unknown model '{spec.model}'")
        if not spec.parameter_set.strip():
            raise TargetSpecError(f"{path}: parameter_set must not be empty")
        if spec.nmc_composition is not None and not str(spec.nmc_composition).isdigit():
            raise TargetSpecError(f"{path}: nmc_composition must be a 3-digit stoichiometry label")
        specs.append(spec)
    return tuple(specs)


def load_named_target(target_id: str, directory: str | Path | None = None) -> TargetSpecification:
    """Load one target by id from a catalog."""
    for spec in load_target_catalog(directory):
        if spec.target_id == target_id:
            return spec
    raise TargetSpecError(f"target_id '{target_id}' not found in catalog")
