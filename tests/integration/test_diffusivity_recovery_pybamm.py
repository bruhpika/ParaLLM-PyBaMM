"""Integration tests for the synthetic GITT recovery study (pinned PyBaMM).

Tiny SPM protocols; everything is model-generated (SYNTHETIC). These tests
prove the dry-run machinery wires correctly to the verified observables API;
they make no claim about real data (rules 7/8) and change no decision (rule 10).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import yaml

pybamm = pytest.importorskip("pybamm")

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH = REPO_ROOT / "benchmarks/observables/diffusivity_gitt_recovery.py"
PARAMETER_SET = "Chen2020"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "diffusivity_gitt_recovery_integration", BENCH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return load_module()


def tiny_config(tmp_path: Path) -> dict:
    return {
        "schema_version": 1,
        "run_id": "integration_recovery_tiny",
        "description": "tiny recovery dry-run",
        "model_name": "SPM",
        "parameter_set": PARAMETER_SET,
        "parameters": [
            {"label": "D_neg", "name": "Negative particle diffusivity [m2.s-1]"},
            {
                "label": "j0_neg",
                "name": "Negative electrode exchange-current density [A.m-2]",
            },
            {"label": "D_e", "name": "Electrolyte diffusivity [m2.s-1]"},
        ],
        "truth_scale_factors": {"D_neg": 0.8, "j0_neg": 1.2, "D_e": 0.9},
        "gitt_d": {
            "model_name": "SPM",
            "current_A": 0.5,
            "pulse_duration_s": 60.0,
            "rest_duration_s": 60.0,
            "n_pulses": 2,
            "period_s": 20.0,
            "initial_soc": 0.2,
            "relaxation_fit_points": 5,
        },
        "noise_sigma_V": 1.0e-3,
        "seed": 3,
        "rel_perturbation": 0.02,
        "optimizer": {"method": "trf", "max_nfev": 40, "bounds": [0.1, 10.0]},
        "multi_start": [[1.0, 1.0, 1.0], [0.5, 1.5, 1.5]],
        "recovery": {
            "z_score_threshold": 3.0,
            "max_estimate_spread_ratio": 1.05,
        },
        "profile": {
            "fixed_parameter": "D_neg",
            "grid": [0.5, 0.8, 1.1],
            "delta_chi2_95": 3.841,
        },
        "outputs": {
            "report": str(tmp_path / "recovery.json"),
            "summary": str(tmp_path / "recovery.md"),
        },
    }


def test_raw_gitt_voltage_matches_declared_protocol(module):
    pv = pybamm.ParameterValues(PARAMETER_SET)
    spec = {
        "model_name": "SPM",
        "current_A": 0.5,
        "pulse_duration_s": 60.0,
        "rest_duration_s": 60.0,
        "n_pulses": 2,
        "period_s": 20.0,
        "initial_soc": 0.2,
    }
    voltage = module.raw_gitt_voltage(pv, spec)
    assert voltage.ndim == 1
    assert np.all(np.isfinite(voltage))
    # 2 x (60 s pulse + 60 s rest) at a 20 s period, plus sampling slack.
    assert 12 <= voltage.size <= 24


def test_run_recovery_writes_labelled_synthetic_artifacts(module, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(tiny_config(tmp_path)), encoding="utf-8")

    report = module.run_recovery(config_path)

    assert report["label"].startswith("SYNTHETIC")
    assert report["synthetic_only"] is True
    assert report["diagnostic_only"] is True
    assert report["decision_changed"] is False
    assert report["registry_write"] is False
    assert report["seed"] == 3
    assert report["n_data_points"] > 0

    recovery = report["recovery"]
    assert set(recovery["truth_scale_factors"]) == {"D_neg", "j0_neg", "D_e"}
    # Honesty property: SPM has no electrolyte dynamics, so D_e touches a null
    # direction of the truth FIM. It must be flagged unconstrained and never
    # counted as recovered, while the constrained parameters get finite SEs.
    assert recovery["unconstrained_parameters"] == ["D_e"]
    for label, entry in recovery["per_parameter"].items():
        assert np.isfinite(recovery["estimate"][label])
        assert entry["multi_start_spread_ratio"] >= 1.0
        assert isinstance(entry["recovered"], bool)
        if label in recovery["unconstrained_parameters"]:
            assert not np.isfinite(recovery["predicted_standard_error"][label])
            assert entry["recovered"] is False
        else:
            assert np.isfinite(recovery["predicted_standard_error"][label])
            assert np.isfinite(entry["z_score"])
    # An unconstrained parameter means the joint recovery cannot be overall.
    assert recovery["recovered"] is False
    assert len(report["multi_start_fits"]) == 2
    assert all(fit["nfev"] > 0 for fit in report["multi_start_fits"])

    profile = report["profile_likelihood"]
    assert profile["fixed_parameter"] == "D_neg"
    assert len(profile["grid"]) == 3
    assert len(profile["chi_square"]) == 3
    assert min(profile["delta_chi_square"]) == pytest.approx(0.0, abs=1e-9)

    on_disk = json.loads(
        (tmp_path / "recovery.json").read_text(encoding="utf-8")
    )
    assert on_disk["run_id"] == "integration_recovery_tiny"
    assert "SYNTHETIC" in (tmp_path / "recovery.md").read_text(encoding="utf-8")


def test_tiny_recovery_rejects_unseeded_or_misdeclared_studies(module, tmp_path):
    config = tiny_config(tmp_path)
    config.pop("seed")
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(KeyError):
        module.run_recovery(config_path)
