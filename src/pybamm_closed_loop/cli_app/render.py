"""Reusable Rich rendering components for the `parallm` command line."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from .errors import CliError

PALETTE: dict[str, str] = {
    "app.title": "bold #E6EDF2",
    "app.label": "#E6EDF2",
    "app.value": "#E6EDF2",
    "app.muted": "dim #8B98A5",
    "app.accent": "bold #5FB6C4",
    "app.line": "#2E5F6B",
    "app.success": "bold #7FB98A",
    "app.warning": "bold #D9A441",
    "app.error": "bold #C96A65",
    "app.panel": "on #12161B",
}

THEME = Theme(PALETTE)

_STATUS_STYLES: dict[str, str] = {
    "PASSED": "app.success",
    "OK": "app.success",
    "COMPLETED": "app.success",
    "CONVERGED": "app.success",
    "FOUND": "app.success",
    "READY": "app.success",
    "SUCCESS": "app.success",
    "WARNING": "app.warning",
    "WARN": "app.warning",
    "UNCERTAIN": "app.warning",
    "MISSING": "app.warning",
    "FAILED": "app.error",
    "FAIL": "app.error",
    "ERROR": "app.error",
    "REJECTED": "app.error",
    "NOT CHECKED": "app.muted",
    "NOT FOUND": "app.muted",
    "NOT CALIBRATED": "app.muted",
    "UNAVAILABLE": "app.muted",
    "UNRESOLVED": "app.muted",
    "PENDING": "app.muted",
    "NOT ASSESSED": "app.muted",
}

_LEVEL_TO_STATUS = {
    "ok": "PASSED",
    "warn": "WARNING",
    "fail": "FAILED",
    "not_checked": "NOT CHECKED",
    "not_assessed": "NOT ASSESSED",
    "pending": "PENDING",
}


def make_console(
    *,
    quiet: bool = False,
    json_mode: bool = False,
    no_color: bool = False,
    stderr: bool = False,
    width: int | None = None,
) -> Console:
    """Create a configured console; redirected output is styled conservatively."""
    env_no_color = bool(os.environ.get("NO_COLOR"))
    force = True if os.environ.get("FORCE_COLOR") else None
    return Console(
        stderr=stderr,
        theme=THEME,
        no_color=no_color or json_mode or quiet or env_no_color,
        force_terminal=force,
        width=width,
        highlight=False,
        markup=False,
        soft_wrap=False,
    )


def header(console: Console, context: str = "", version: str = "") -> None:
    """Print the compact application header once per invocation."""
    left = Text("ParaLLM-PyBaMM", style="app.title")
    if version:
        left.append(f"  v{version}", style="app.muted")
    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(justify="right")
    grid.add_row(left, Text(context, style="app.muted"))
    console.print(grid)
    console.print("Literature-driven parameter intelligence", style="app.muted")
    console.print(Rule(style="app.line", characters="-"))


def section(console: Console, title: str) -> None:
    console.print(Text(title.upper(), style="app.accent"))
    console.print(Rule(style="app.line", characters="-"))


def status_text(status: str) -> Text:
    """Render a status word with the convention defined in the design system."""
    key = _LEVEL_TO_STATUS.get(status.lower(), status.upper()) if status else "NOT CHECKED"
    return Text(key, style=_STATUS_STYLES.get(key, "app.value"))


def format_value(value: Any) -> str:
    """Format a value for aligned display without inventing precision."""
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value == 0 or 1e-4 <= abs(value) < 1e6:
            return f"{value:.6g}"
        return f"{value:.4e}"
    if isinstance(value, (list, tuple, dict)):
        text = json.dumps(value, sort_keys=True, default=str)
        return text if len(text) <= 60 else text[:57] + "..."
    return str(value)


def kv(console: Console, rows: Sequence[tuple[str, Any]], label_width: int = 14) -> None:
    """Print aligned label/value rows."""
    grid = Table.grid(padding=(0, 2), collapse_padding=True)
    grid.add_column(min_width=label_width, style="app.label", no_wrap=False)
    grid.add_column(style="app.value", overflow="fold")
    for label, value in rows:
        if isinstance(value, Text):
            rendered = value
        else:
            rendered = Text(format_value(value))
        grid.add_row(Text(str(label)), rendered)
    console.print(grid)


def table(
    console: Console,
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    status_columns: Sequence[int] = (),
    numeric_columns: Sequence[int] = (),
) -> None:
    """Print a boxless aligned table."""
    grid = Table(
        box=None,
        show_header=True,
        header_style="app.accent",
        pad_edge=False,
        padding=(0, 1),
        expand=False,
    )
    for index, name in enumerate(columns):
        grid.add_column(
            str(name),
            justify="right" if index in numeric_columns else "left",
            overflow="ellipsis",
            min_width=1,
        )
    for row in rows:
        cells: list[Text] = []
        for index, cell in enumerate(row):
            if isinstance(cell, Text):
                cells.append(cell)
            elif index in status_columns:
                cells.append(status_text(str(cell)))
            else:
                cells.append(Text(format_value(cell)))
        grid.add_row(*cells)
    console.print(grid)


def footer(console: Console, next_command: str) -> None:
    """Print the optional dim `next:` line defined in the design system."""
    console.print()
    console.print(Text("next: ", style="app.muted") + Text(next_command, style="app.accent"))


def notice(console: Console, message: str, kind: str = "info") -> None:
    """Print a one-line note; colour is reserved for warning and error."""
    prefix, style = {
        "info": ("NOTE", "app.muted"),
        "warn": ("WARNING", "app.warning"),
        "error": ("ERROR", "app.error"),
    }.get(kind, ("NOTE", "app.muted"))
    console.print(Text(prefix, style=style))
    console.print(Text(f"  {message}", style="app.muted"))


def error_panel(console: Console, error: CliError, *, debug_exc: BaseException | None = None) -> None:
    """Print a structured error with what, why and next action."""
    body = Table.grid(padding=(0, 1))
    body.add_column(min_width=9, style="app.muted")
    body.add_column(overflow="fold")
    body.add_row("What", Text(error.what, style="app.value"))
    if error.why:
        body.add_row("Why", Text(error.why, style="app.value"))
    if error.action:
        body.add_row("Action", Text(error.action, style="app.value"))
    for line in error.details:
        body.add_row("", Text(line, style="app.muted"))
    if debug_exc is not None:
        body.add_row("Debug", Text(f"{type(debug_exc).__name__}: {debug_exc}", style="app.error"))
    panel = Panel(
        body,
        title=f"ERROR {error.code}",
        title_align="left",
        border_style="app.error",
        box=box.SQUARE,
        padding=(0, 1),
        width=min(console.width, 84),
    )
    console.print(panel)


def success(console: Console, message: str) -> None:
    console.print(Text(message, style="app.success"))


def muted(console: Console, message: str) -> None:
    console.print(Text(message, style="app.muted"))


def make_progress(console: Console, description: str, *, enabled: bool) -> Progress:
    """Create a progress display only when real progress will be reported."""
    return Progress(
        TextColumn("{task.description}"),
        BarColumn(bar_width=24),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        disable=not enabled or not console.is_terminal,
        transient=False,
    )


def write_json(payload: Mapping[str, Any], *, stream: Any = None) -> None:
    """Write one machine-readable JSON object with no styling."""
    target = stream if stream is not None else sys.stdout
    target.write(json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n")
