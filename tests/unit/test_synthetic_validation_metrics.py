"""Unit tests: V2.4 synthetic-validation metrics (pure numpy, no pybop)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "benchmarks" / "v2" / "run_synthetic_validation.py"
)
_spec = importlib.util.spec_from_file_location("run_synthetic_validation", _SCRIPT)
sv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sv)


def test_voltage_rmse_zero_for_identical_traces():
    t = np.linspace(0, 1, 50)
    v = 3.5 + 0.1 * t
    assert sv.voltage_rmse(t, v, t, v) == 0.0


def test_voltage_rmse_interpolates_prediction_onto_grid():
    t = np.linspace(0, 1, 51)
    v = np.full_like(t, 3.5)
    # prediction sampled coarser but identical values
    t_pred = np.linspace(0, 1, 11)
    v_pred = np.full_like(t_pred, 3.5)
    assert sv.voltage_rmse(t, v, t_pred, v_pred) == 0.0


def test_voltage_rmse_measures_constant_offset():
    t = np.linspace(0, 1, 51)
    v = np.full_like(t, 3.5)
    v_pred = np.full_like(t, 3.5 + 0.1)
    assert abs(sv.voltage_rmse(t, v, t, v_pred) - 0.1) < 1e-12


def test_voltage_rmse_nan_for_degenerate_input():
    assert np.isnan(sv.voltage_rmse(np.array([1.0]), np.array([2.0]),
                                    np.array([1.0]), np.array([2.0])))
