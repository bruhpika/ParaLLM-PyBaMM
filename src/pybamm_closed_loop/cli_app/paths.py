"""Path resolution shared by scientific commands (config-aware, no I/O side effects)."""

from __future__ import annotations

from pathlib import Path

from .context import State
from .errors import InputError


def configured_path(state: State, attribute: str, *, fallback: Path | None = None) -> Path | None:
    config = state.config
    if config is not None:
        path = config.resolve(getattr(config.paths, attribute, None))
        if path is not None:
            return path
    return fallback


def input_path(
    state: State,
    explicit: Path | None,
    attribute: str,
    *,
    fallback: Path | None = None,
    what: str = "input",
    expect: str = "file",
) -> Path:
    """Resolve an input path from an option, config or workspace fallback."""
    path = explicit.expanduser().resolve() if explicit is not None else configured_path(state, attribute, fallback=fallback)
    if path is None:
        raise InputError(
            f"No {what} path is configured.",
            why="No option was given and the configuration has no matching path.",
            action="Pass the path explicitly or run `parallm init` to configure it.",
        )
    exists = path.is_dir() if expect == "directory" else path.is_file()
    if not exists:
        raise InputError(
            f"{what.capitalize()} not found.",
            why=f"Expected {expect}: {path}",
            action="Pass an existing path or update the configuration.",
        )
    return path


def report_path(state: State, explicit: Path | None) -> Path:
    fallback = state.workspace() / "reports" / "assembly" if state.config and state.config.workspace else Path.cwd() / "reports" / "assembly"
    return input_path(state, explicit, "report_dir", fallback=fallback, what="assembly report", expect="directory")
