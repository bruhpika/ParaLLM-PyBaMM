"""Unit tests for the synthetic GITT recovery / profile-likelihood study.

Pure helpers and an analytic toy problem only; the PyBaMM-backed dry-run lives
in ``tests/integration/test_diffusivity_recovery_pybamm.py``. The toy problem
is the end-to-end proof that the declared recovery and profile rules behave
correctly on a problem whose answer is known by construction.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH = REPO_ROOT / "benchmarks/observables/diffusivity_gitt_recovery.py"
CONFIG = REPO_ROOT / "configs/v03/diffusivity_recovery.yaml"


def load_module():
    spec = importlib.util.spec_from_file_location("diffusivity_gitt_recovery", BENCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Config validation
# --------------------------------------------------------------------------
def test_committed_config_is_valid_and_matches_spec_27():
    mod = load_module()
    cfg = mod.load_config(CONFIG)
    mod.validate_config(cfg)  # must not raise
    assert cfg["gitt_d"]["initial_soc"] == pytest.approx(0.20)
    assert cfg["gitt_d"]["current_A"] == pytest.approx(1.0)
    assert cfg["gitt_d"]["pulse_duration_s"] == pytest.approx(120.0)
    assert cfg["gitt_d"]["rest_duration_s"] == pytest.approx(180.0)
    assert cfg["gitt_d"]["n_pulses"] == 5
    assert cfg["noise_sigma_V"] == pytest.approx(1.0e-3)
    assert cfg["truth_scale_factors"]["D_neg"] != 1.0
    assert cfg["profile"]["fixed_parameter"] == "D_neg"
    assert len(cfg["multi_start"]) >= 2
    assert cfg["outputs"]["report"].startswith("results/observables/")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.pop("seed"),
        lambda c: c.update(truth_scale_factors={"D_neg": 0.5}),
        lambda c: c.update(multi_start=[]),
        lambda c: c.update(multi_start=[[1.0, 1.0]]),
        lambda c: c.update(multi_start=[[50.0, 1.0, 1.0]]),
        lambda c: c["profile"].update(grid=[0.2, 0.2, 0.5]),
        lambda c: c["profile"].update(fixed_parameter="nope"),
        lambda c: c["recovery"].update(z_score_threshold=0.0),
    ],
)
def test_validate_config_rejects_broken_studies(mutate):
    mod = load_module()
    cfg = mod.load_config(CONFIG)
    mutate(cfg)
    with pytest.raises((KeyError, ValueError)):
        mod.validate_config(cfg)


# --------------------------------------------------------------------------
# Pure statistics helpers
# --------------------------------------------------------------------------
def test_parameter_standard_errors_flags_null_space_parameters():
    mod = load_module()
    se, unconstrained = mod.parameter_standard_errors(np.diag([4.0, 9.0, 0.0]))
    assert se == pytest.approx([0.5, 1.0 / 3.0, np.inf])
    assert unconstrained.tolist() == [False, False, True]

    se2, unconstrained2 = mod.parameter_standard_errors(np.diag([4.0, 0.0, 0.0]))
    assert se2[0] == pytest.approx(0.5)
    assert np.isinf(se2[1]) and np.isinf(se2[2])
    assert unconstrained2.tolist() == [False, True, True]

    with pytest.raises(ValueError):
        mod.parameter_standard_errors(np.ones((2, 3)))


def test_z_score_and_spread():
    mod = load_module()
    assert mod.z_score(1.1, 1.0, 0.1) == pytest.approx(1.0)
    assert mod.z_score(1.1, 1.0, float("inf")) == float("inf")
    assert mod.estimate_spread_ratio([1.0, 1.05, 0.98]) == pytest.approx(1.05 / 0.98)
    with pytest.raises(ValueError):
        mod.estimate_spread_ratio([1.0, 0.0])


def test_recovery_status_rule():
    mod = load_module()
    ok = mod.recovery_status(
        {"a": 0.5, "b": -1.0}, {"a": 1.0, "b": 1.02}, 3.0, 1.05
    )
    assert ok["recovered"] is True
    assert ok["per_parameter"]["b"]["recovered"] is True
    bad_z = mod.recovery_status(
        {"a": 3.5}, {"a": 1.0}, 3.0, 1.05
    )
    assert bad_z["recovered"] is False
    bad_spread = mod.recovery_status(
        {"a": 0.1}, {"a": 1.2}, 3.0, 1.05
    )
    assert bad_spread["recovered"] is False


def test_profile_verdict_closed_and_unbounded():
    mod = load_module()
    grid = np.array([0.5, 0.75, 1.0, 1.25, 1.5])
    parabola = (grid - 1.0) ** 2 * 100.0
    closed = mod.profile_verdict(grid, parabola, 3.841)
    assert closed["closed_at_delta_chi2"] is True
    lo, hi = closed["ci95"]
    assert lo < 1.0 < hi
    # Crossings are linearly interpolated between grid points: on this grid the
    # 3.841 crossing is between (0.75, 6.25) and (1.0, 0), i.e. 0.84636, and
    # mirrored at 1.15364. A coarse grid underestimates a convex profile's
    # interval relative to the continuous solution (1.0 +- 0.196); refine the
    # grid near the crossing for tighter bounds.
    assert lo == pytest.approx(0.84636, abs=1e-4)
    assert hi == pytest.approx(1.15364, abs=1e-4)
    # Documented coarse-grid effect: the interpolated interval is narrower than
    # the continuous solution's, because the parabola is convex.
    continuous_lo = 1.0 - np.sqrt(3.841 / 100.0)
    continuous_hi = 1.0 + np.sqrt(3.841 / 100.0)
    assert continuous_lo < lo < 1.0 < hi < continuous_hi

    flat_right = np.array([20.0, 5.0, 0.0, 0.0, 0.0])
    open_profile = mod.profile_verdict(grid, flat_right, 3.841)
    assert open_profile["closed_at_delta_chi2"] is False
    assert open_profile["unbounded_sides"] == ["high"]
    assert open_profile["ci95"] is None

    # A minimum at the grid edge can never be closed.
    edge_min = mod.profile_verdict(grid, np.array([0.0, 20.0, 21.0, 21.0, 21.0]), 3.841)
    assert edge_min["closed_at_delta_chi2"] is False
    assert edge_min["unbounded_sides"] == ["low"]

    with pytest.raises(ValueError):
        mod.profile_verdict(grid, np.array([0.0, 1.0]), 3.841)
    with pytest.raises(ValueError):
        mod.profile_verdict(np.array([1.0, 0.5, 2.0]), parabola[:3], 3.841)


def test_chi_square_and_residual():
    mod = load_module()
    assert mod.chi_square(np.array([3.0, 4.0])) == pytest.approx(25.0)
    predict = lambda x: np.array([x[0], 2.0 * x[0]])  # noqa: E731
    residual = mod.weighted_residual(predict, np.array([1.0, 2.0]), 0.5, np.array([1.0]))
    assert residual == pytest.approx([0.0, 0.0])
    with pytest.raises(ValueError):
        mod.weighted_residual(predict, np.array([1.0, 2.0]), 0.0, np.array([1.0]))


# --------------------------------------------------------------------------
# Committed artifact (present after the dry-run)
# --------------------------------------------------------------------------
def test_committed_recovery_artifact_is_honest_and_non_decision_changing():
    path = REPO_ROOT / "results/observables/diffusivity_gitt_recovery.json"
    if not path.exists():
        pytest.skip("committed recovery artifact absent")

    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["label"].startswith("SYNTHETIC")
    assert report["synthetic_only"] is True
    assert report["diagnostic_only"] is True
    assert report["decision_changed"] is False
    assert report["registry_write"] is False
    assert report["seed"] >= 0
    assert [p["label"] for p in report["parameters"]] == ["D_neg", "j0_neg", "D_e"]

    recovery = report["recovery"]
    for label, entry in recovery["per_parameter"].items():
        se = recovery["predicted_standard_error"][label]
        if label in recovery["unconstrained_parameters"]:
            # An unconstrained parameter must never be reported as recovered.
            assert not np.isfinite(se)
            assert entry["recovered"] is False
        else:
            expected = (
                abs(entry["z_score"]) <= 3.0
                and entry["multi_start_spread_ratio"] <= 1.05
            )
            assert entry["recovered"] is expected

    profile = report["profile_likelihood"]
    assert profile["fixed_parameter"] == "D_neg"
    assert min(profile["delta_chi_square"]) == pytest.approx(0.0, abs=1e-9)
    if profile["closed_at_delta_chi2"]:
        lo, hi = profile["ci95"]
        assert lo <= profile["minimum_grid_value"] <= hi

    assert "rule 7" in report["scientific_note"] or "identifiability" in report[
        "scientific_note"
    ]
def test_toy_recovery_and_profile_machinery():
    mod = load_module()
    rng = np.random.default_rng(7)
    t = np.linspace(0.0, 1.0, 40)
    truth = np.array([0.8, 1.4, 0.6])
    sigma = 0.01

    def predict(x: np.ndarray) -> np.ndarray:
        a, b, c = (float(v) for v in x)
        return a * np.sin(3.0 * t) + b * t**2 + c

    data = predict(truth) + rng.normal(0.0, sigma, size=t.size)

    fits = [
        mod.run_fit(predict, data, sigma, np.array(start), (0.1, 5.0), "trf", 200)
        for start in ([1.0, 1.0, 1.0], [0.2, 3.0, 1.5], [2.0, 0.5, 0.2])
    ]
    assert all(rep["success"] for rep in fits)
    best = min(fits, key=lambda rep: rep["chi_square"])
    estimate = np.array(best["estimate"])

    se, corr, unconstrained = mod.predicted_standard_errors(predict, truth, sigma, 0.02)
    assert np.all(np.isfinite(se))
    assert not np.any(unconstrained)
    assert np.allclose(np.diag(corr), 1.0)

    z = {
        name: mod.z_score(estimate[i], truth[i], se[i])
        for i, name in enumerate("abc")
    }
    spread = {
        name: mod.estimate_spread_ratio([rep["estimate"][i] for rep in fits])
        for i, name in enumerate("abc")
    }
    status = mod.recovery_status(z, spread, 3.0, 1.05)
    assert status["recovered"] is True, status

    grid = np.linspace(0.5, 1.1, 13)
    costs = []
    for value in grid:

        def pinned(x_free: np.ndarray, fixed: float = float(value)) -> np.ndarray:
            return predict(np.array([fixed, x_free[0], x_free[1]]))

        rep = mod.run_fit(
            pinned, data, sigma, np.array([1.0, 1.0]), (0.1, 5.0), "trf", 200
        )
        costs.append(rep["chi_square"])
    minimum = min(costs)
    profile = mod.profile_verdict(
        grid, np.array(costs) - minimum, 3.841
    )
    assert profile["closed_at_delta_chi2"] is True, profile
    lo, hi = profile["ci95"]
    assert lo < 0.8 < hi
    assert hi - lo < 0.3  # the toy is well constrained; a flat profile would fail
