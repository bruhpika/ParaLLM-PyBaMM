"""Structured CLI errors with stable codes and actionable recovery steps."""

from __future__ import annotations


class CliError(Exception):
    """Base class for expected, user-facing CLI failures."""

    code = "E100"
    exit_code = 2

    def __init__(
        self,
        what: str,
        *,
        why: str | None = None,
        action: str | None = None,
        details: list[str] | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(what)
        self.what = what
        self.why = why
        self.action = action
        self.details = list(details or [])
        if code is not None:
            self.code = code

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "what": self.what,
            "why": self.why,
            "action": self.action,
            "details": self.details,
        }


class ConfigError(CliError):
    """Configuration is missing, unreadable or invalid."""

    code = "E104"
    exit_code = 2


class InputError(CliError):
    """An input file, format or argument is missing or invalid."""

    code = "E201"
    exit_code = 2


class ParseError(CliError):
    """An input file could not be parsed."""

    code = "E202"
    exit_code = 2


class DependencyError(CliError):
    """A required or optional dependency is unavailable."""

    code = "E301"
    exit_code = 3


class VersionError(CliError):
    """An installed dependency does not match the pinned version."""

    code = "E302"
    exit_code = 3


class ScientificError(CliError):
    """A scientific check or workflow did not succeed."""

    code = "E401"
    exit_code = 1


class TraceabilityError(CliError):
    """Dossier traceability checks failed."""

    code = "E402"
    exit_code = 1


class OverwriteError(CliError):
    """A write was refused to protect existing user data."""

    code = "E403"
    exit_code = 2


class ExportError(CliError):
    """An export could not be produced without losing scientific traceability."""

    code = "E404"
    exit_code = 2
