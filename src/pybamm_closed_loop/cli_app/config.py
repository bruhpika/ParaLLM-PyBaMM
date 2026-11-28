"""Centralised, version-pinned configuration for the `parallm` CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "parallm" / "config.toml"
CONFIG_ENV_VAR = "PARALLM_CONFIG"
SCHEMA_VERSION = 1


class PathSettings(BaseModel):
    """Workspace-relative locations used by scientific commands."""

    model_config = ConfigDict(extra="forbid")

    registry: Path | None = None
    documents: Path | None = None
    p2_results: Path | None = None
    target: Path | None = None
    gate: Path | None = None


class CLIConfig(BaseModel):
    """User configuration; never stores credentials or API keys."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    workspace: Path | None = None
    rubric_version: str = "rubric-v3"
    default_export_format: Literal["json", "pybamm"] = "json"
    paths: PathSettings = Field(default_factory=PathSettings)

    def resolve(self, path: Path | None) -> Path | None:
        """Resolve a configured path against the workspace directory."""
        if path is None:
            return None
        if path.is_absolute():
            return path
        return ((self.workspace or Path.cwd()) / path).resolve()

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.model_dump_json())


def config_path(explicit: str | Path | None = None) -> Path:
    """Return the effective config file path (argument > env > default)."""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get(CONFIG_ENV_VAR)
    if env:
        return Path(env).expanduser()
    return DEFAULT_CONFIG_PATH


def load_config(explicit: str | Path | None = None) -> tuple[CLIConfig | None, Path]:
    """Load configuration, returning ``None`` when no file exists."""
    path = config_path(explicit)
    if not path.is_file():
        return None, path
    raw = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid TOML in {path}: {exc}") from exc
    section = data.get("parallm", data)
    if not isinstance(section, dict):
        raise ValueError(f"config {path} must contain a table of settings")
    return CLIConfig.model_validate(section), path


def dump_config(config: CLIConfig) -> str:
    """Serialise the known config schema to TOML (no generic serialiser)."""

    def quote(value: object) -> str:
        return json.dumps(str(value))

    lines = [
        f"schema_version = {config.schema_version}",
        f"rubric_version = {quote(config.rubric_version)}",
        f"default_export_format = {quote(config.default_export_format)}",
    ]
    if config.workspace is not None:
        lines.append(f"workspace = {quote(config.workspace)}")
    lines.append("")
    lines.append("[paths]")
    for key, value in config.paths.model_dump().items():
        if value is not None:
            lines.append(f"{key} = {quote(value)}")
    return "\n".join(lines) + "\n"


def save_config(config: CLIConfig, path: Path) -> None:
    """Write configuration atomically enough for a single-user CLI."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_config(config), encoding="utf-8")
