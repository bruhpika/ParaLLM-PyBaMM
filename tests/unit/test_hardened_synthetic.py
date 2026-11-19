"""Unit tests for the hardened SYNTHETIC mismatch validation helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

_PATH = REPO_ROOT / "benchmarks/v2/run_synthetic_validation.py"
_SPEC = importlib.util.spec_from_file_location("v2_synthetic_validation", _PATH)
assert _SPEC and _SPEC.loader
MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MOD)


def _payload(base: float, positive: float, negative: float, reproduced: bool) -> dict:
    def arm(value: float) -> dict:
        return {
            "mean_held_out_error_V": value,
            "fit": {"success": True},
            "ci_coverage": {"available": False, "reason": "none"},
        }

    return {
        "truth": {"values": {}},
        "baseline": arm(base),
        "positive_control": arm(positive),
        "negative_control": arm(negative),
        "prediction": {
            "observed_positive_improves": positive < base,
            "observed_negative_does_not_improve": negative >= base,
            "reproduced": reproduced,
        },
    }


def test_scaled_truth_uses_recorded_offsets_only():
    start = {name: value * 0.9 for name, value in MOD.TRUTH_VALUES.items()}
    assert MOD.scaled_truth(start, 1.0) == MOD.TRUTH_VALUES
    scaled = MOD.scaled_truth(start, 0.75)
    assert set(scaled) == set(MOD.TRUTH_VALUES)
    for name, base in MOD.TRUTH_VALUES.items():
        assert scaled[name] == pytest.approx(start[name] + 0.75 * (base - start[name]))
    assert scaled != MOD.TRUTH_VALUES


def test_ci_coverage_unavailable_is_explicit():
    result = MOD.ci_coverage({"parameters": []}, {})
    assert result["available"] is False
    assert "no covariance" in result["reason"]


def test_ci_coverage_computes_95_percent_interval_when_available():
    report = {
        "parameters": [
            {"name": "a", "estimate": 1.0},
            {"name": "b", "estimate": 2.0},
        ],
        "standard_errors": {"a": 0.01, "b": 0.10},
    }
    covered = MOD.ci_coverage(report, {"a": 1.0, "b": 5.0})
    assert covered["available"] is True
    assert covered["n_parameters"] == 2
    assert covered["n_covered"] == 1
    assert covered["coverage"] == pytest.approx(0.5)


def test_hardened_validation_aggregates_counts_and_stats(monkeypatch, tmp_path):
    calls = []

    def fake_run_experiment(**kwargs):
        calls.append(kwargs)
        i = len(calls)
        return _payload(0.004, 0.001, 0.004, True) if i % 2 else _payload(
            0.005, 0.006, 0.003, False
        )

    monkeypatch.setattr(MOD, "run_experiment", fake_run_experiment)
    payload = MOD.run_hardened_validation(
        out_dir=tmp_path,
        n_truths=1,
        noise_levels=(0.001, 0.002),
        seeds=(101, 102),
    )
    assert len(calls) == 4 + 1  # 4 grid runs + 1 fixed-truth reference
    assert all(c["mismatch"] is True for c in calls[:-1])
    assert calls[-1]["mismatch"] is False
    assert calls[-1]["noise_sigma_V"] == 0.001
    agg = payload["aggregate"]
    assert agg["held_out_rmse_V"]["baseline"]["mean"] == pytest.approx(0.0045)
    assert agg["held_out_rmse_V"]["baseline"]["min"] == pytest.approx(0.004)
    assert agg["held_out_rmse_V"]["baseline"]["max"] == pytest.approx(0.005)
    assert agg["positive_beats_baseline"]["count"] == 2
    assert agg["negative_does_not_beat_baseline"]["count"] == 2
    assert agg["prediction_reproduced"]["count"] == 2
    assert agg["all_fits_converged"] is True
    assert agg["ci_coverage"]["positive"]["available"] is False
    assert payload["fixed_truth_reference"]["baseline_mean_V"] == pytest.approx(0.004)
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "summary.md").exists()
    summary = (tmp_path / "summary.md").read_text()
    assert "SYNTHETIC" in summary
    assert "CI coverage" in summary
    assert "Old fixed-truth result" in summary


def test_mismatch_solver_is_a_different_dae_solver():
    pybamm = pytest.importorskip("pybamm")
    solver = MOD._mismatch_solver()
    assert isinstance(solver, pybamm.CasadiSolver)
    assert solver.rtol == MOD.MISMATCH_RTOL
    assert solver.atol == MOD.MISMATCH_ATOL
    assert MOD.MISMATCH_VAR_PTS["x_n"] < pybamm.lithium_ion.DFN().default_var_pts["x_n"]
