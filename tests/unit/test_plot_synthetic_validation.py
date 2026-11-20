"""Tests for scripts/plot_synthetic_validation.py (no simulation, no network)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_PATH = REPO_ROOT / "scripts/plot_synthetic_validation.py"
_SPEC = importlib.util.spec_from_file_location("plot_synthetic_validation", _PATH)
assert _SPEC and _SPEC.loader
MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MOD)


def test_load_main_series_has_five_seeds_and_expected_means():
    series = MOD.load_main_series(MOD.MAIN_REPORT)
    assert len(series["seeds"]) == 5
    assert len(series["baseline"]) == 5
    assert len(series["positive_control"]) == 5
    assert len(series["negative_control"]) == 5
    baseline_mean, _ = MOD._mean_std(series["baseline"])
    positive_mean, _ = MOD._mean_std(series["positive_control"])
    assert baseline_mean == pytest.approx(4.434, abs=0.01)
    assert positive_mean == pytest.approx(1.052, abs=0.01)
    assert series["baseline"] == series["negative_control"]


def test_load_mismatch_series_has_eighteen_runs():
    series = MOD.load_mismatch_series(MOD.MISMATCH_REPORT)
    assert len(series["seeds"]) == 18
    assert len(series["baseline"]) == 18
    assert len(series["positive_control"]) == 18
    assert len(series["negative_control"]) == 18
    baseline_mean, _ = MOD._mean_std(series["baseline"])
    positive_mean, _ = MOD._mean_std(series["positive_control"])
    assert baseline_mean == pytest.approx(2.580, abs=0.01)
    assert positive_mean == pytest.approx(1.798, abs=0.01)
    assert series["baseline"] == series["negative_control"]


def test_plot_overview_writes_png(tmp_path):
    main = MOD.load_main_series(MOD.MAIN_REPORT)
    mismatch = MOD.load_mismatch_series(MOD.MISMATCH_REPORT)
    out = tmp_path / "heldout_rmse.png"
    path = MOD.plot_overview(main, mismatch, out)
    assert path == out
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert out.stat().st_size > 10_000
