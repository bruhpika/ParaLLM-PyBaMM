"""Integration test: V2.4 synthetic end-to-end validation (quick run).

Runs the full pipeline (assemble -> synthetic data -> baseline -> positive /
negative control fits -> held-out validation) on a reduced configuration.
Labelled SYNTHETIC throughout; deterministic (fixed seed).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pybop = pytest.importorskip("pybop")
pytest.importorskip("pybamm")

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "benchmarks" / "v2" / "run_synthetic_validation.py"
)
_spec = importlib.util.spec_from_file_location("run_synthetic_validation", _SCRIPT)
sv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sv)

QUICK_STEPS = {
    "0.5C": ["Discharge at 0.5C for 10 s"],
    "1C": ["Discharge at 1C for 10 s"],
    "2C": ["Discharge at 2C for 10 s"],
}


def test_quick_synthetic_validation_run(tmp_path):
    payload = sv.run_experiment(
        out_dir=tmp_path,
        model_name="SPM",
        steps=QUICK_STEPS,
        maxiter=3,
        seed=7,
        noise_sigma_V=1e-3,
    )
    assert payload["label"].startswith("SYNTHETIC")
    assert payload["assembled"]["experiment_roles"]["negative_control"] == (
        "neg_particle_diffusivity"
    )
    assert payload["assembled"]["action_matrix"]["CALIBRATE"] == 6
    for arm in ("baseline", "positive_control", "negative_control"):
        held = payload[arm]["held_out_errors_V"]
        assert set(held) == {"0.5C", "2C"}
        assert all(v == v and v >= 0 for v in held.values())
    pred = payload["prediction"]
    assert set(pred) == {
        "positive_improves_held_out",
        "negative_does_not_improve",
        "observed_positive_improves",
        "observed_negative_does_not_improve",
        "reproduced",
    }
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "summary.md").exists()
    # labelled synthetic in every artifact
    assert "SYNTHETIC" in (tmp_path / "summary.md").read_text()
