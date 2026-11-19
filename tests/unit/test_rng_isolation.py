"""Global numpy RNG state is never left modified by deterministic helpers."""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from pybamm_closed_loop.calibration.identifiability import sobol_indices
from pybamm_closed_loop.calibration.rng import isolated_numpy_seed, legacy_seed


def _states_equal(a, b) -> bool:
    return a[0] == b[0] and np.array_equal(a[1], b[1]) and a[2:] == b[2:]


def test_isolated_numpy_seed_restores_state():
    np.random.seed(2026)
    before = np.random.get_state()
    with isolated_numpy_seed(7):
        np.random.random(5)
        assert not _states_equal(np.random.get_state(), before)
    assert _states_equal(np.random.get_state(), before)


def test_isolated_numpy_seed_restores_state_on_exception():
    np.random.seed(5)
    before = np.random.get_state()
    with pytest.raises(ValueError):
        with isolated_numpy_seed(1):
            np.random.random()
            raise ValueError("boom")
    assert _states_equal(np.random.get_state(), before)


def test_legacy_seed_is_deterministic_and_condition_dependent():
    assert legacy_seed(np.random.default_rng(9)) == legacy_seed(np.random.default_rng(9))
    assert legacy_seed(np.random.default_rng(9)) != legacy_seed(np.random.default_rng(10))


def _fake_salib(monkeypatch):
    """Minimal SALib 1.6-style modules that record the global RNG at sample time."""
    seen: dict[str, float] = {}

    def sample(problem, N, calc_second_order=True, skip_values=None):
        seen["draw"] = float(np.random.random())
        return np.array([[0.1, 0.2], [0.3, 0.4]])

    def analyze(problem, Y, calc_second_order=True, print_to_console=False):
        return {"S1": np.array([0.1, 0.2]), "ST": np.array([0.3, 0.4])}

    salib = types.ModuleType("SALib")
    salib_sample = types.ModuleType("SALib.sample")
    salib_analyze = types.ModuleType("SALib.analyze")
    salib_sample.saltelli = types.SimpleNamespace(sample=sample)
    salib_analyze.sobol = types.SimpleNamespace(analyze=analyze)
    monkeypatch.setitem(sys.modules, "SALib", salib)
    monkeypatch.setitem(sys.modules, "SALib.sample", salib_sample)
    monkeypatch.setitem(sys.modules, "SALib.analyze", salib_analyze)
    return seen


def test_sobol_indices_restores_global_state(monkeypatch):
    seen = _fake_salib(monkeypatch)
    np.random.seed(31415)
    before = np.random.get_state()
    out = sobol_indices(
        lambda p: np.array([1.0, 2.0]),
        np.array([[0.0, 1.0], [0.0, 1.0]]),
        ["a", "b"],
        n_samples=4,
        seed=7,
    )
    assert _states_equal(np.random.get_state(), before)
    np.random.seed(7)
    assert seen["draw"] == float(np.random.random())
    assert out["seed"] == 7


def test_sobol_indices_explicit_generator_reproduces_and_isolates(monkeypatch):
    seen = _fake_salib(monkeypatch)
    kwargs = dict(n_samples=4, seed=0)

    def run():
        np.random.seed(777)
        before = np.random.get_state()
        out = sobol_indices(
            lambda p: np.array([1.0, 2.0]),
            np.array([[0.0, 1.0], [0.0, 1.0]]),
            ["a", "b"],
            rng=np.random.default_rng(42),
            **kwargs,
        )
        assert _states_equal(np.random.get_state(), before)
        return seen["draw"], out

    first, out1 = run()
    second, out2 = run()
    assert first == second
    assert out1["S1"].tolist() == out2["S1"].tolist()
