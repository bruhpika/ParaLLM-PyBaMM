"""Input helpers shared by CLI commands; no scientific decisions live here."""

from __future__ import annotations

import hashlib
import json
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..assembly import TargetSpecification

from .. import __version__
from .errors import InputError, ParseError


def _string_map(value: Any, field_name: str) -> dict[str, str]:
    """Validate a YAML mapping of string -> string without inventing defaults."""
    if value is None:
        return {}
    if not isinstance(value, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()
    ):
        raise ValueError(f"{field_name} must be a mapping of strings to strings")
    return dict(value)


def load_target(path: Path) -> "TargetSpecification":
    """Load a target specification; preserves the historical SystemExit API."""
    import yaml

    from ..assembly import TargetSpecification

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    target = raw.get("target") if isinstance(raw, dict) and "target" in raw else raw
    if not isinstance(target, dict):
        raise SystemExit(f"target spec {path} has no 'target' mapping")
    try:
        return TargetSpecification(
            target_id=target["target_id"],
            cell_product=target["cell_product"],
            chemistry_families=tuple(target.get("chemistry_families") or ()),
            format=target.get("format"),
            temperature_k=target.get("temperature_k"),
            temperature_range_k=(
                tuple(target["temperature_range_k"]) if target.get("temperature_range_k") else None
            ),
            soc=target.get("soc"),
            electrolyte=target.get("electrolyte"),
            model=target.get("model") or "DFN",
            parameter_set=target.get("parameter_set") or "Chen2020",
            notes=target.get("notes") or "",
            model_options=_string_map(target.get("model_options"), "model_options"),
            nmc_composition=target.get("nmc_composition"),
            verification=_string_map(target.get("verification"), "verification"),
        )
    except KeyError as exc:
        raise SystemExit(f"target spec {path} missing required key {exc}") from exc
    except ValueError as exc:
        raise SystemExit(f"target spec {path}: {exc}") from exc


def read_target(path: Path) -> "TargetSpecification":
    """CLI-facing adapter that converts legacy SystemExit into a CLI error."""
    try:
        return load_target(path)
    except SystemExit as exc:
        raise InputError(
            "Target specification is invalid.",
            why=str(exc),
            action="Add the missing keys or the top-level 'target:' mapping.",
        ) from exc


def load_doc_texts(documents: Path) -> dict[str, str]:
    """Map document id -> full text from a raw-document store directory."""
    if not documents.is_dir():
        raise InputError(
            "Documents directory not found.",
            why=f"Expected: {documents}",
            action="Pass an existing raw-document store with --documents.",
        )
    out: dict[str, str] = {}
    raw_dir = documents / "raw"
    if (documents / "documents.json").is_file() and raw_dir.is_dir():
        for text_file in sorted(raw_dir.glob("*.txt")):
            out[text_file.stem] = text_file.read_text(encoding="utf-8", errors="replace")
        return out
    for sub in sorted(documents.iterdir()):
        if not sub.is_dir():
            continue
        fulltexts = sorted(sub.glob("*_fulltext.txt"))
        if fulltexts:
            out[sub.name] = fulltexts[0].read_text(encoding="utf-8", errors="replace")
    return out


def load_json(path: Path, *, description: str = "input") -> Any:
    """Read a JSON file with a stable, actionable error."""
    if not path.is_file():
        raise InputError(
            f"{description.capitalize()} file not found.",
            why=f"Expected: {path}",
            action="Provide an existing JSON file.",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ParseError(
            f"Could not parse {description} JSON: {path}", why=str(exc)
        ) from exc


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tool_version() -> str:
    try:
        return metadata.version("parallm-pybamm")
    except metadata.PackageNotFoundError:
        return __version__
