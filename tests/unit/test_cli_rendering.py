"""Rendering tests: status conventions, narrow widths and long values."""

from __future__ import annotations

from rich.console import Console

from pybamm_closed_loop.cli_app.render import (
    THEME,
    error_panel,
    format_value,
    kv,
    make_console,
    section,
    status_text,
    table,
)
from pybamm_closed_loop.cli_app.errors import InputError


def _console(width: int = 100) -> Console:
    return Console(width=width, no_color=True, theme=THEME, record=True, markup=False, highlight=False)


def test_status_conventions_never_confuse_unperformed_checks():
    assert status_text("ok").plain == "PASSED"
    assert status_text("warn").plain == "WARNING"
    assert status_text("fail").plain == "FAILED"
    assert status_text("not_checked").plain == "NOT CHECKED"
    assert status_text("NOT CALIBRATED").plain == "NOT CALIBRATED"


def test_format_value_handles_large_and_missing_values():
    assert format_value(None) == "unavailable"
    assert format_value(1.2e-12) == "1.2000e-12"
    assert format_value(123456.0) == "123456"
    assert format_value(True) == "true"


def test_kv_aligns_labels_and_supports_long_parameter_names():
    console = _console(80)
    kv(console, [("Parameter", "a_very_long_canonical_parameter_identifier_that_wraps"), ("Value", 1.2e-12)])
    text = console.export_text()
    assert "Parameter" in text
    assert "a_very_long" in text
    assert "1.2000e-12" in text


def test_table_at_narrow_width_does_not_overflow():
    console = _console(48)
    table(
        console,
        ("CHECK", "STATUS", "DETAIL"),
        [("physical_plausibility", "WARNING", "value outside plausible range")],
        status_columns=(1,),
    )
    text = console.export_text()
    for line in text.splitlines():
        assert len(line) <= 48
    assert "WARNING" in text


def test_section_headings_are_uppercase():
    console = _console()
    section(console, "parameter record")
    assert "PARAMETER RECORD" in console.export_text()


def test_error_panel_has_code_what_why_action():
    console = _console()
    error = InputError("File not found.", why="Missing path", action="Pass --input.")
    error_panel(console, error)
    text = console.export_text()
    assert "E201" in text
    assert "Missing path" in text
    assert "Pass --input." in text
    assert "Traceback" not in text


def test_console_respects_no_color_and_quiet():
    console = make_console(quiet=True, no_color=True, width=60)
    assert console.no_color is True
    assert console.width == 60
