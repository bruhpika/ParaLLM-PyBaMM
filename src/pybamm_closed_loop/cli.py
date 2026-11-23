"""Console entry point for ParaLLM-PyBaMM.

The historical ``main(argv)`` API is preserved for library users and tests.
Command logic lives in :mod:`pybamm_closed_loop.cli_app`; this module only wires
the Typer application to the process and renders unexpected failures.
"""

from __future__ import annotations

import sys
import traceback
from typing import Sequence

import click

from .cli_app import render
from .cli_app.app import app
from .cli_app.errors import CliError
from .cli_app.inputs import load_doc_texts, load_target, sha256, tool_version

__all__ = ["app", "load_doc_texts", "load_target", "main", "sha256", "tool_version"]

# Typer 0.29+ vendors Click under ``typer._click``; its usage errors are no
# longer subclasses of the external ``click.ClickException``.  Collect both
# hierarchies so invalid invocations are reported as usage errors on every
# supported Typer version, while genuine application failures still fall
# through to the E199 handler below.
_USAGE_ERRORS: tuple[type[BaseException], ...] = (click.ClickException,)
_EXIT_ERRORS: tuple[type[BaseException], ...] = (click.exceptions.Exit,)
_ABORT_ERRORS: tuple[type[BaseException], ...] = (click.exceptions.Abort,)

try:
    from typer.exceptions import Abort as _TyperAbort
    from typer.exceptions import Exit as _TyperExit
    from typer.exceptions import TyperException as _TyperException
except ImportError:  # Typer < 0.29 uses the external Click classes above.
    pass
else:
    _USAGE_ERRORS += (_TyperException,)
    _EXIT_ERRORS += (_TyperExit,)
    _ABORT_ERRORS += (_TyperAbort,)


def _error_console(debug: bool):
    return render.make_console(stderr=True, no_color=not debug)


def _command_name(args: list[str]) -> str:
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in ("--config", "--width"):
            skip = True
            continue
        if not arg.startswith("-"):
            return arg
    return "parallm"


def _json_failure(command: str, error: CliError) -> None:
    render.write_json(
        {
            "schema_version": 1,
            "command": command,
            "status": "failed",
            "data": {},
            "diagnostics": [{"level": "error", **error.to_dict()}],
        }
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI with explicit arguments and return a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    debug = "--debug" in args
    try:
        result = app(args=args or ["--help"], prog_name="parallm", standalone_mode=False)
    except SystemExit as exc:
        return int(exc.code or 0)
    except _EXIT_ERRORS as exc:
        return int(exc.exit_code)
    except _ABORT_ERRORS:
        sys.stderr.write("\ninterrupted\n")
        return 130
    except _USAGE_ERRORS as exc:
        message = exc.format_message()
        if "--json" in args:
            _json_failure(
                _command_name(args),
                CliError(message, code="E100", action="Check command usage."),
            )
        else:
            sys.stderr.write(f"ERROR  {message}\n")
        return int(exc.exit_code)
    except CliError as exc:
        if "--json" in args:
            _json_failure(_command_name(args), exc)
        else:
            render.error_panel(_error_console(debug), exc)
        return int(exc.exit_code)
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    except Exception as exc:
        error = CliError(
            "Unexpected CLI failure.",
            why=f"{type(exc).__name__}: {exc}",
            action="Re-run with --debug for a traceback, or report this as a bug.",
            code="E199",
        )
        if "--json" in args:
            _json_failure(_command_name(args), error)
        else:
            render.error_panel(_error_console(debug), error, debug_exc=exc if debug else None)
        if debug:
            traceback.print_exc()
        return 2
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
