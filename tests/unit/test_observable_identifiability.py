"""Unit tests for the observable-augmented observability diagnostic.

Only pure helpers are exercised here; the PyBaMM-backed run lives in
``tests/integration/test_observable_identifiability_pybamm.py``.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH = REPO_ROOT / "benchmarks/observables/diffusivity_multi_observable_fim.py"
CONFIG = REPO_ROOT / "configs/v03/observable_identifiability.yaml"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "diffusivity_multi_observable_fim", BENCH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Config parsing
# --------------------------------------------------------------------------
def test_parse_logspace_round_trip():
    mod = load_module()
    values = mod.parse_logspace("logspace(-2, 2, 5)")
    assert values.shape == (5,)
    assert values[0] == pytest.approx(1e-2)
    assert values[-1] == pytest.approx(1e2)


@pytest.mark.parametrize(
    "spec",
    ["linspace(0, 1, 5)", "logspace(0, 1)", "logspace(a, b, 3)", "logspace(0, 1, 0)"],
)
def test_parse_logspace_rejects_invalid(spec):
    mod = load_module()
    with pytest.raises(ValueError):
        mod.parse_logspace(spec)


def test_committed_config_is_complete():
    mod = load_module()
    cfg = mod.load_config(CONFIG)
    for key in (
        "run_id",
        "parameter_set",
        "parameter",
        "rel_perturbation",
        "voltage_conditions",
        "gitt_d",
        "eis",
        "ocv_soc",
        "noise",
        "normalization",
        "positive_control",
        "outputs",
    ):
        assert key in cfg, key
    assert cfg["parameter"] == "Negative particle diffusivity [m2.s-1]"
    assert cfg["positive_control"]["factor"] > 1.0
    assert cfg["gitt_d"]["initial_soc"] == pytest.approx(0.20)
    assert cfg["gitt_d"]["relaxation_fit_points"] >= 3
    assert set(cfg["normalization"]) >= {
        "voltage",
        "gitt_rest_voltage",
        "gitt_pulse_drop",
        "gitt_relaxation_slope",
        "eis",
        "ocv",
    }
    joint = cfg["joint_fim"]
    assert joint["enabled"] is True
    assert joint["collinearity_warning_abs_correlation"] == pytest.approx(0.9)
    assert joint["robustness_rel_perturbations"] == [0.005, 0.01, 0.05]
    assert [p["label"] for p in joint["parameters"]] == ["D_neg", "j0_neg", "D_e"]
    assert joint["parameters"][0]["name"] == cfg["parameter"]
    assert joint["observables"]
    assert joint["outputs"]["report"].startswith("results/observables/")


def test_voltage_query_times_matches_committed_convention():
    mod = load_module()
    times = mod.voltage_query_times(1800.0, 24, 10.0)
    assert times.shape == (24,)
    assert times[0] == pytest.approx(10.0)
    assert times[-1] == pytest.approx(1800.0)


@pytest.mark.parametrize(
    "t_end,t_start,n",
    [(10.0, 10.0, 5), (5.0, 10.0, 5), (100.0, 10.0, 1)],
)
def test_voltage_query_times_rejects_invalid(t_end, t_start, n):
    mod = load_module()
    with pytest.raises(ValueError):
        mod.voltage_query_times(t_end, n, t_start)


# --------------------------------------------------------------------------
# Normalization and sensitivities
# --------------------------------------------------------------------------
def test_characteristic_scale_conventions():
    mod = load_module()
    y = np.array([1.0, 2.0, 3.0])
    assert mod.characteristic_scale(y, "std") == pytest.approx(np.std(y))
    assert mod.characteristic_scale(y, "mean_magnitude") == pytest.approx(2.0)
    with pytest.raises(ValueError):
        mod.characteristic_scale(y, "variance")


@pytest.mark.parametrize("bad", [np.zeros(4), np.full(4, 1e-15), np.array([])])
def test_characteristic_scale_rejects_degenerate(bad):
    mod = load_module()
    with pytest.raises(ValueError):
        mod.characteristic_scale(bad, "std")


def test_mean_abs_normalized_sensitivity_matches_manual_calculation():
    mod = load_module()
    # One parameter, two observation points.
    jacobian = np.array([[2.0], [-4.0]])
    x = np.array([1.0])
    y_scale = 2.0
    expected = (abs(2.0 / 2.0) + abs(-4.0 / 2.0)) / 2.0
    value = mod.mean_abs_normalized_sensitivity(jacobian, x, y_scale)
    assert value == pytest.approx(expected)


def test_implied_relative_standard_error():
    mod = load_module()
    assert mod.implied_relative_standard_error(np.array([[100.0]])) == pytest.approx(0.1)
    assert mod.implied_relative_standard_error(np.array([[0.0]])) == float("inf")
    with pytest.raises(ValueError):
        mod.implied_relative_standard_error(np.array([[1.0, 0.0], [0.0, 1.0]]))


# --------------------------------------------------------------------------
# Recorded observability rules
# --------------------------------------------------------------------------
def test_classify_observability_requires_both_rules():
    mod = load_module()
    # Below the sensitivity rule -> unobservable even with a tiny rel. SE.
    assert (
        mod.classify_observability(0.01, 0.001) == "UNOBSERVABLE"
    )
    # Above the sensitivity rule but a poor relative SE -> still unobservable.
    assert mod.classify_observability(0.2, 0.2) == "UNOBSERVABLE"
    # Both rules satisfied.
    assert mod.classify_observability(0.2, 0.01) == "OBSERVABLE"
    assert mod.classify_observability(0.01, float("inf")) == "UNOBSERVABLE"


def test_classify_information_requires_sensitivity_and_information():
    mod = load_module()
    # Small relative SE alone is not enough: no block clears mean |S| >= 0.05.
    assert mod.classify_information(0.01, 0.01) == "UNOBSERVABLE"
    # A sensitive block alone is not enough if the information rule fails.
    assert mod.classify_information(0.5, 0.2) == "UNOBSERVABLE"
    # Both rules satisfied -> observable.
    assert mod.classify_information(0.01, 0.2) == "OBSERVABLE"
    assert mod.classify_information(float("inf"), 0.2) == "UNOBSERVABLE"
    assert mod.classify_information(0.01, float("nan")) == "UNOBSERVABLE"


def test_thresholds_match_recorded_observability_rules():
    mod = load_module()
    from pybamm_closed_loop.assembly import observability

    assert (
        mod.SENSITIVITY_OBSERVABILITY_THRESHOLD
        == observability.SENSITIVITY_OBSERVABILITY_THRESHOLD
    )
    assert (
        mod.RELATIVE_STD_OBSERVABILITY_THRESHOLD
        == observability.BOOTSTRAP_REL_STD_OBSERVABILITY
    )


# --------------------------------------------------------------------------
# Baseline comparison and information gain
# --------------------------------------------------------------------------
def test_compare_voltage_block_to_baseline():
    mod = load_module()
    ok = mod.compare_voltage_block_to_baseline(0.0111, 0.0107, 0.005)
    assert ok["within_tolerance"] is True
    assert ok["absolute_delta"] == pytest.approx(0.0004)
    bad = mod.compare_voltage_block_to_baseline(0.02, 0.0107, 0.005)
    assert bad["within_tolerance"] is False


def test_information_ratio():
    mod = load_module()
    assert mod.information_ratio(np.array([[400.0]]), np.array([[100.0]])) == pytest.approx(2.0)
    assert mod.information_ratio(np.array([[0.0]]), np.array([[0.0]])) == float("inf")


# --------------------------------------------------------------------------
# Joint multi-parameter FIM helpers
# --------------------------------------------------------------------------
def test_marginal_relative_standard_errors():
    mod = load_module()
    diagonal = mod.marginal_relative_standard_errors(np.diag([4.0, 9.0]))
    assert diagonal == pytest.approx([0.5, 1.0 / 3.0])
    # Rank-deficient FIM: a finite pseudo-inverse diagonal would be misleading.
    rank_deficient = mod.marginal_relative_standard_errors(
        np.array([[1.0, 1.0], [1.0, 1.0]])
    )
    assert np.all(np.isinf(rank_deficient))
    with pytest.raises(ValueError):
        mod.marginal_relative_standard_errors(np.ones((2, 3)))


def test_parameter_correlation_matrix():
    mod = load_module()
    identity = mod.parameter_correlation_matrix(np.diag([4.0, 9.0]))
    assert identity == pytest.approx(np.eye(2))
    correlated = mod.parameter_correlation_matrix(np.array([[1.0, 0.5], [0.5, 1.0]]))
    assert correlated[0, 1] == pytest.approx(-0.5)
    assert correlated[1, 0] == pytest.approx(-0.5)
    assert np.all(np.isfinite(correlated))


def test_variance_inflation_factor_and_se_reduction():
    mod = load_module()
    assert mod.variance_inflation_factor(0.2, 0.1) == pytest.approx(4.0)
    assert mod.variance_inflation_factor(0.2, 0.2) == pytest.approx(1.0)
    assert mod.variance_inflation_factor(float("inf"), 0.1) == float("inf")
    assert mod.variance_inflation_factor(0.2, float("inf")) == float("inf")
    assert mod.variance_inflation_factor(0.2, 0.0) == float("inf")

    assert mod.standard_error_reduction(0.2, 0.1) == pytest.approx(2.0)
    assert mod.standard_error_reduction(0.2, float("inf")) == 0.0
    assert mod.standard_error_reduction(float("inf"), 0.1) == float("inf")


def test_joint_observable_specs_cover_every_configured_observable():
    mod = load_module()
    cfg = mod.load_config(CONFIG)
    specs = mod.joint_observable_specs(cfg, cfg["model_name"], eis_sigma=1e-3)
    assert set(cfg["joint_fim"]["observables"]) <= set(specs)
    assert specs["eis_re_impedance"]["sigma"] == pytest.approx(1e-3)
    for name in cfg["joint_fim"]["observables"]:
        assert callable(specs[name]["predict"])
        assert specs[name]["sigma"] > 0


# --------------------------------------------------------------------------
# GITT protocol guard (the defect that produced the 2026-11-27 correction)
# --------------------------------------------------------------------------
def test_gitt_protocol_warnings_flag_null_or_high_soc():
    mod = load_module()
    assert mod.gitt_protocol_warnings({"initial_soc": None})
    assert mod.gitt_protocol_warnings({"initial_soc": 0.95})
    assert mod.gitt_protocol_warnings({"initial_soc": 1.0})
    assert mod.gitt_protocol_warnings({"initial_soc": 0.2}) == []
    assert mod.gitt_protocol_warnings({"initial_soc": 0.5}) == []


# --------------------------------------------------------------------------
# A-priori diffusion scales
# --------------------------------------------------------------------------
def test_diffusion_frequency_arithmetic():
    mod = load_module()
    result = mod.diffusion_frequency(4.0, 2.0)
    assert result["diffusion_time_constant_s"] == pytest.approx(1.0)
    assert result["diffusion_frequency_Hz"] == pytest.approx(1.0 / (2.0 * np.pi))


@pytest.mark.parametrize("d,radius", [(0.0, 1.0), (1.0, 0.0), (-1.0, 1.0)])
def test_diffusion_frequency_rejects_non_positive(d, radius):
    mod = load_module()
    with pytest.raises(ValueError):
        mod.diffusion_frequency(d, radius)


def test_relative_change():
    mod = load_module()
    assert mod.relative_change([1.0, 2.0], [1.0, 2.0]) == 0.0
    assert mod.relative_change([1.0, 2.0], [1.0, 3.0]) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        mod.relative_change([1.0], [1.0, 2.0])


# --------------------------------------------------------------------------
# Summary rendering (no PyBaMM)
# --------------------------------------------------------------------------
def test_render_summary_marks_synthetic_and_limitations():
    mod = load_module()
    report = {
        "label": "SYNTHETIC TEST",
        "parameter": "p",
        "parameter_set": "Chen2020",
        "model_name": "DFN",
        "scale_factor": 1.0,
        "a_priori_diffusion_scales": {
            "diffusivity_m2_s": 3.3e-14,
            "particle_radius_m": 5.86e-6,
            "diffusion_time_constant_s": 1040.6,
            "diffusion_frequency_Hz": 1.53e-4,
            "eis_band_Hz": [1e-4, 1e1],
            "eis_band_covers_diffusion_frequency": True,
        },
        "gitt_protocol": {
            "initial_soc": 0.2,
            "current_A": 1.0,
            "current_C_rate": 0.2,
            "pulse_duration_s": 120.0,
            "rest_duration_s": 180.0,
            "n_pulses": 5,
            "relaxation_fit_points": 5,
        },
        "protocol_warnings": [],
        "per_observable": {
            "voltage_1C": {
                "n_points": 24,
                "normalization": "std",
                "sigma": 1e-3,
                "mean_abs_normalized_sensitivity": 0.0213,
                "implied_relative_standard_error": 0.0087,
                "classification": "UNOBSERVABLE",
            }
        },
        "voltage_only": {
            "fim": 1.0,
            "implied_relative_standard_error": 1.0,
            "classification": "UNOBSERVABLE",
            "strongest_block_mean_abs_normalized_sensitivity": 0.02,
            "classification_rule": "conjunction",
        },
        "observable_augmented": {
            "fim": 1.0,
            "implied_relative_standard_error": 1.0,
            "classification": "UNOBSERVABLE",
            "strongest_block_mean_abs_normalized_sensitivity": 0.02,
            "classification_rule": "conjunction",
        },
        "information_gain_sqrt_ratio": 1.0,
        "verdict": {
            "voltage_only_classification": "UNOBSERVABLE",
            "observable_augmented_classification": "UNOBSERVABLE",
            "flip": False,
            "statement": "no flip",
            "decision": "unchanged",
        },
        "eis_positive_control": {
            "parameter": "k",
            "factor": 10.0,
            "component": "z_re",
            "relative_impedance_change": 0.2,
            "interpretation": "control",
        },
        "baseline_comparison": {"note": "absent"},
        "limitations": ["SYNTHETIC ONLY"],
    }
    text = mod._render_summary(report)
    assert "SYNTHETIC TEST" in text
    assert "diagnostic only" in text
    assert "SYNTHETIC ONLY" in text
    assert "not** proof" in text or "not proof" in text


# --------------------------------------------------------------------------
# Committed artifacts (present after the benchmark run)
# --------------------------------------------------------------------------
def test_committed_report_is_labelled_and_non_decision_changing():
    report_path = REPO_ROOT / "results/observables/diffusivity_multi_observable_fim.json"
    if not report_path.exists():
        pytest.skip("committed diagnostic artifact absent")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["label"].startswith("SYNTHETIC")
    assert report["diagnostic_only"] is True
    assert report["decision_changed"] is False
    assert report["registry_write"] is False
    assert report["baseline_comparison"]["all_within_tolerance"] is True
    assert report["eis_positive_control"]["relative_impedance_change"] > 0.01
    assert "scientific_note" in report
    # 2026-11-27 correction: the committed protocol is the low-SOC one and its
    # GITT features must clear the recorded sensitivity bar.
    assert report["gitt_protocol"]["initial_soc"] == pytest.approx(0.20)
    assert report["protocol_warnings"] == []
    for name in ("gitt_d_pulse_drop", "gitt_d_relaxation_slope"):
        assert (
            report["per_observable"][name]["mean_abs_normalized_sensitivity"]
            > 0.05
        ), name
    assert report["verdict"]["flip"] is True
    joint = report["joint_fim"]
    assert joint["primary_parameter"] == "D_neg"
    assert joint["parameters"] == ["D_neg", "j0_neg", "D_e"]
    assert joint["survives_collinearity_check"] is True
    assert joint["single_parameter_cross_check_passed"] is True


# --------------------------------------------------------------------------
# Committed joint artifact (present after the benchmark run)
# --------------------------------------------------------------------------
def test_committed_joint_report_pins_collinearity_result():
    report_path = REPO_ROOT / "results/observables/joint_diffusivity_fim.json"
    if not report_path.exists():
        pytest.skip("committed joint diagnostic artifact absent")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["label"].startswith("SYNTHETIC")
    assert report["diagnostic_only"] is True
    assert report["decision_changed"] is False
    assert report["registry_write"] is False
    assert report["primary_parameter"] == "D_neg"
    assert [p["label"] for p in report["parameters"]] == ["D_neg", "j0_neg", "D_e"]
    assert report["single_parameter_cross_check"]["all_within_tolerance"] is True

    summary = report["primary_parameter_summary"]
    thresholds = report["thresholds"]
    assert summary["classification"] == "OBSERVABLE"
    assert summary["survives_collinearity_check"] is True
    assert (
        summary["marginal_relative_standard_error"]
        <= thresholds["relative_std_observability"]
    )
    assert (
        summary["strongest_mean_abs_normalized_sensitivity"]
        >= thresholds["sensitivity_observability"]
    )
    # Freeing parameters cannot reduce the marginal variance.
    assert summary["variance_inflation_factor"] >= 1.0
    for entry in summary["correlations"]:
        assert (
            abs(entry["correlation"])
            < thresholds["collinearity_warning_abs_correlation"]
        ), entry

    robustness = report["perturbation_robustness"]
    assert robustness["checks"]
    assert robustness["classification_stable"] is True
    # The conservative-classification caveat must stay in the artifact.
    assert "conservative" in report["interpretation"]
