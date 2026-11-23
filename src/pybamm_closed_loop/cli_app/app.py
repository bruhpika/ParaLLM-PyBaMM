"""Typer application definition for the `parallm` command line."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
import typer.rich_utils as rich_utils

from .. import __version__
from . import render
from .config import load_config
from .context import State

rich_utils.MAX_WIDTH = 100
rich_utils.STYLE_OPTION = "bold #5FB6C4"
rich_utils.STYLE_SWITCH = "bold #5FB6C4"
rich_utils.STYLE_USAGE = "bold #5FB6C4"
rich_utils.STYLE_USAGE_COMMAND = "bold #E6EDF2"
rich_utils.STYLE_HELPTEXT_FIRST_LINE = "#E6EDF2"
rich_utils.STYLE_HELPTEXT = "#8B98A5"
rich_utils.STYLE_OPTION_HELP = "#8B98A5"
rich_utils.STYLE_OPTION_DEFAULT = "dim #8B98A5"
rich_utils.STYLE_REQUIRED_SHORT = "bold #C96A65"
rich_utils.STYLE_REQUIRED_LONG = "bold #C96A65"
rich_utils.STYLE_ERRORS_PANEL_BORDER = "#C96A65"
rich_utils.STYLE_ERRORS_SUGGESTION = "#5FB6C4"
rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = "bold #5FB6C4"
rich_utils.STYLE_COMMANDS_PANEL_BORDER = "#2E5F6B"
rich_utils.STYLE_OPTIONS_PANEL_BORDER = "#2E5F6B"

APP_HELP = """ParaLLM-PyBaMM — literature-driven parameter intelligence.

Commands follow the research workflow: set up a workspace (init), check the
environment (doctor), collect evidence (extract), inspect provenance (evidence,
explain), check candidates (validate), assemble dossiers (assemble), and export
only human-approved values (export).

Extracted values are candidates, not validated or calibrated parameters.
Synthetic calibration is not experimental validation.
"""

app = typer.Typer(
    name="parallm",
    help=APP_HELP,
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    rich_markup_mode=None,
)


def _version_callback(value: bool, ctx: typer.Context) -> None:
    if value:
        sys.stdout.write(f"parallm {__version__}\n")
        ctx.exit()


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit one machine-readable JSON object."
    ),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress decorative output."),
    debug: bool = typer.Option(False, "--debug", help="Include tracebacks for unexpected errors."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable terminal colour."),
    config: str | None = typer.Option(
        None, "--config", envvar="PARALLM_CONFIG", help="Configuration file path."
    ),
    width: int | None = typer.Option(
        None, "--width", hidden=True, help="Force output width (used by tests)."
    ),
) -> None:
    console = render.make_console(
        quiet=quiet, json_mode=json_output, no_color=no_color, width=width
    )
    err_console = render.make_console(
        quiet=quiet, json_mode=json_output, no_color=no_color, stderr=True, width=width
    )
    state = State(
        console=console,
        err=err_console,
        quiet=quiet,
        json_mode=json_output,
        debug=debug,
        config=None,
        config_path=Path.home() / ".config" / "parallm" / "config.toml",
        command=ctx.invoked_subcommand or "parallm",
    )
    try:
        loaded, path = load_config(config)
        state.config, state.config_path = loaded, path
    except Exception as exc:
        state.config_error = f"{type(exc).__name__}: {exc}"
    ctx.obj = state
    if ctx.invoked_subcommand and not quiet and not json_output:
        context = (
            f"workspace: {state.config.workspace.name}"
            if state.config is not None and state.config.workspace is not None
            else "no workspace"
        )
        render.header(console, context=context, version=__version__)


from .commands import assemble, calibration, core, export, science  # noqa: E402

app.command("assemble")(assemble.assemble_command)
app.command("export")(export.export)
app.add_typer(calibration.calibrate_app, name="calibrate")
app.command("extract")(science.extract)
app.command("validate")(science.validate)
app.command("explain")(science.explain)
app.add_typer(science.evidence_app, name="evidence")
app.command("doctor")(core.doctor)
app.command("init")(core.init)
app.command("status")(core.status)
app.command("simulate")(core.simulate)
app.add_typer(core.project_app, name="project")
