"""Integration tests for the observable-augmented observability diagnostic.

Runs the real benchmark against pinned PyBaMM 26.8.0.0 with a deliberately
tiny protocol. Everything is model-generated (SYNTHETIC); no experimental
data is claimed and no calibration objective is touched.
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
BENCH = REPO_ROOT / "benchmarks/observables/diffusivity_multi_observable_fim.py"
PARAMETER = "Negative particle diffusivity [m2.s-1]"
PARAMETER_SET = "Chen2020"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "diffusivity_multi_observable_fim_integration", BENCH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return load_module()


def test_pinned_version_and_study_parameter_are_present(module):
    assert pybamm.__version__ == module.PINNED_PYBAM_VERSION
    pv = pybamm.ParameterValues(PARAMETER_SET)
    assert PARAMETER in pv.keys()
    # The study device requires a scalar; the benchmark refuses callables.
    assert not callable(pv[PARAMETER])
    assert "Negative particle radius [m]" in pv.keys()


def test_scaled_parameter_values_scales_only_the_study_parameter(module):
    base = pybamm.ParameterValues(PARAMETER_SET)
    scaled = module.scaled_parameter_values(PARAMETER_SET, PARAMETER, 2.0)
    assert float(scaled[PARAMETER]) == pytest.approx(float(base[PARAMETER]) * 2.0)
    # An unrelated scalar must be untouched.
    other = "Negative particle radius [m]"
    assert float(scaled[other]) == pytest.approx(float(base[other]))


def test_gitt_features_are_finite_and_per_pulse(module):
    pv = pybamm.ParameterValues(PARAMETER_SET)
    spec = {
        "model_name": "SPM",
        "current_A": 0.5,
        "pulse_duration_s": 60.0,
        "rest_duration_s": 60.0,
        "n_pulses": 2,
        "period_s": 20.0,
        "initial_soc": None,
    }
    rest = module.gitt_rest_voltages(pv, spec)
    drops = module.gitt_pulse_drops(pv, spec)
    assert rest.shape == (2,)
    assert drops.shape == (2,)
    assert np.all(np.isfinite(rest)) and np.all(np.isfinite(drops))
    # Discharge pulses must produce a positive overpotential.
    assert np.all(drops > 0)


def test_eis_components_have_expected_signs(module):
    pv = pybamm.ParameterValues(PARAMETER_SET)
    spec = {"model_name": "SPM", "frequencies_Hz": "logspace(-1, 2, 6)", "initial_soc": 0.5}
    real = module.eis_spectrum(pv, spec, "z_re")
    neg_imag = module.eis_spectrum(pv, spec, "neg_z_im")
    assert real.shape == (6,) and neg_imag.shape == (6,)
    assert np.all(real > 0)
    assert np.all(neg_imag > 0)
    with pytest.raises(ValueError):
        module.eis_spectrum(pv, spec, "phase")


def test_eis_positive_control_moves_but_diffusivity_does_not(module):
    """Recorded PyBaMM 26.8.0.0 behaviour: EIS ignores solid diffusivity.

    The positive control proves the harness propagates parameter values
    (kinetics moves the spectrum a lot). If a future PyBaMM release starts
    including solid diffusion in EIS, the second assertion fails and the
    recorded limitation in the docs/result artifact must be revisited.
    """
    spec = {"model_name": "SPM", "frequencies_Hz": "logspace(-1, 2, 8)", "initial_soc": 0.5}
    base = module.eis_spectrum(
        module.scaled_parameter_values(PARAMETER_SET, PARAMETER, 1.0), spec, "z_re"
    )
    kinetics = "Negative electrode exchange-current density [A.m-2]"
    moved = module.eis_spectrum(
        module.scaled_parameter_values(PARAMETER_SET, kinetics, 10.0), spec, "z_re"
    )
    unchanged = module.eis_spectrum(
        module.scaled_parameter_values(PARAMETER_SET, PARAMETER, 100.0), spec, "z_re"
    )
    kinetics_change = module.relative_change(base, moved)
    diffusivity_change = module.relative_change(base, unchanged)
    # Kinetics must move the spectrum substantially; a 100x diffusivity change
    # must be negligible by comparison (observed ~8e-5 vs ~0.19, i.e. the
    # residual is a numerical side-effect of the initial-SOC rebuild, not a
    # resolved diffusion signature). Assert the contrast, not a magic floor.
    assert kinetics_change > 0.05
    assert diffusivity_change < 1e-3
    assert kinetics_change > 100.0 * diffusivity_change


def test_run_diagnostic_writes_labelled_synthetic_artifacts(module, tmp_path):
    report_path = tmp_path / "report.json"
    summary_path = tmp_path / "summary.md"
    config = {
        "schema_version": 1,
        "run_id": "integration_tiny",
        "description": "tiny integration protocol",
        "model_name": "SPM",
        "parameter_set": PARAMETER_SET,
        "parameter": PARAMETER,
        "rel_perturbation": 0.02,
        "baseline_report": str(tmp_path / "absent_baseline.json"),
        "baseline_tolerance": 0.005,
        "voltage_conditions": [
            {"name": "0.5C", "steps": ["Discharge at 0.5C for 300 s"], "t_end_s": 300.0}
        ],
        "voltage_n_points": 6,
        "voltage_t_start_s": 10.0,
        "gitt_d": {
            "model_name": "SPM",
            "current_A": 0.5,
            "pulse_duration_s": 60.0,
            "rest_duration_s": 60.0,
            "n_pulses": 2,
            "period_s": 20.0,
            "initial_soc": None,
        },
        "eis": {
            "model_name": "SPM",
            "frequencies_Hz": "logspace(-1, 2, 6)",
            "initial_soc": 0.5,
        },
        "ocv_soc": {"n_points": 5, "direction": None},
        "positive_control": {
            "parameter": "Negative electrode exchange-current density [A.m-2]",
            "factor": 10.0,
            "component": "z_re",
        },
        "noise": {
            "voltage_V": 1e-3,
            "gitt_voltage_V": 1e-3,
            "eis_relative": 1e-2,
            "ocv_voltage_V": 1e-3,
        },
        "normalization": {
            "voltage": "std",
            "gitt_rest_voltage": "std",
            "gitt_pulse_drop": "mean_magnitude",
            "eis": "std",
            "ocv": "std",
        },
        "outputs": {"report": str(report_path), "summary": str(summary_path)},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    report = module.run_diagnostic(config_path)

    assert report["label"].startswith("SYNTHETIC")
    assert report["diagnostic_only"] is True
    assert report["decision_changed"] is False
    assert report["registry_write"] is False
    assert report["parameter"] == PARAMETER
    assert report["baseline_comparison"]["note"].startswith("committed baseline report absent")
    assert report["a_priori_diffusion_scales"]["diffusion_time_constant_s"] > 0
    assert report["eis_positive_control"]["relative_impedance_change"] > 0.05
    assert set(report["per_observable"]) == {
        "voltage_0.5C",
        "gitt_d_rest_voltage",
        "gitt_d_pulse_drop",
        "eis_re_impedance",
        "eis_neg_im_impedance",
        "ocv_soc_control",
    }
    # OCV is the negative control: equilibrium thermodynamics cannot inform a
    # transport parameter, so its sensitivity must be exactly zero.
    assert report["per_observable"]["ocv_soc_control"][
        "mean_abs_normalized_sensitivity"
    ] == pytest.approx(0.0, abs=1e-12)

    on_disk = json.loads(report_path.read_text(encoding="utf-8"))
    assert on_disk["run_id"] == "integration_tiny"
    assert "SYNTHETIC" in summary_path.read_text(encoding="utf-8")
