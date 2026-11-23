"""Shared invocation state passed to every command handler."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import sys

from rich.console import Console

from .config import CLIConfig
from .errors import ConfigError
from .render import format_value, notice, write_json


@dataclass
class State:
    console: Console
    err: Console
    quiet: bool
    json_mode: bool
    debug: bool
    config: CLIConfig | None
    config_path: Path
    config_error: str | None = None
    command: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def require_config(self) -> CLIConfig:
        if self.config is None:
            raise ConfigError(
                "Configuration file not found.",
                why=(
                    self.config_error
                    or f"Expected: {self.config_path}. First run or the file was removed."
                ),
                action="Run `parallm init` to create a configuration.",
            )
        return self.config

    def workspace(self) -> Path:
        config = self.require_config()
        if config.workspace is None:
            raise ConfigError(
                "No workspace directory is configured.",
                why=f"Configuration file {self.config_path} has no 'workspace' entry.",
                action="Run `parallm init --workspace PATH` to set one.",
            )
        return config.resolve(config.workspace) or Path.cwd()

    def warn(self, message: str) -> None:
        self.diagnostics.append({"level": "warning", "message": message})
        if not self.quiet and not self.json_mode:
            notice(self.err, message, "warn")

    def emit(self, data: dict[str, Any], *, status: str = "completed") -> None:
        """Emit JSON in --json mode, a compact line in --quiet mode."""
        if self.quiet and not self.json_mode:
            scalars = [
                f"{key}={format_value(value)}"
                for key, value in data.items()
                if isinstance(value, (str, int, float, bool)) or value is None
            ]
            sys.stdout.write(" ".join(scalars) + "\n")
        if not self.json_mode:
            return
        write_json(
            {
                "schema_version": 1,
                "command": self.command,
                "status": status,
                "data": data,
                "diagnostics": self.diagnostics,
            }
        )
