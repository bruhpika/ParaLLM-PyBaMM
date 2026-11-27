"""Unit tests for combining forward-observable sensitivities (fakes only)."""

from __future__ import annotations

import numpy as np
import pytest

from pybamm_closed_loop.calibration.identifiability import multi_observable_fim


def test_combining_two_observables_recovers_full_rank_fim():
    x = np.array([1.0, 2.0])
    # EIS-like observable informs parameter 0; GITT-like informs parameter 1.
    spec = {
        "eis": {
            "jacobian": np.array([[1.0, 0.0], [2.0, 0.0]]),
            "sigma": 0.01,
            "y_scale": 0.1,
        },
        "gitt_d": {
            "jacobian": np.array([[0.0, 3.0], [0.0, 1.0]]),
            "sigma": 0.02,
            "y_scale": 4.0,
        },
    }
    result = multi_observable_fim(spec, x)
    assert result["stacked_jacobian_shape"] == [4, 2]
    assert np.isfinite(result["condition_number"])
    assert set(result["per_observable"]) == {"eis", "gitt_d"}
    assert result["synthetic_only"] is True


def test_single_rank_deficient_observable_is_flagged():
    x = np.array([1.0, 2.0])
    result = multi_observable_fim(
        {
            "ocv_soc": {
                "jacobian": np.array([[1.0, 2.0], [2.0, 4.0]]),
                "sigma": 0.01,
                "y_scale": 4.0,
            }
        },
        x,
    )
    assert result["condition_number"] == float("inf")


@pytest.mark.parametrize(
    "bad, match",
    [
        ({"a": {"jacobian": np.ones((2, 1)), "sigma": 0.01, "y_scale": 1.0}}, "columns"),
        ({"a": {"jacobian": np.ones((2, 2)), "sigma": 0.0, "y_scale": 1.0}}, "sigma"),
        ({"a": {"jacobian": np.ones((2, 2)), "sigma": 0.01, "y_scale": -1.0}}, "y_scale"),
    ],
)
def test_multi_observable_fim_rejects_invalid_inputs(bad, match):
    with pytest.raises(ValueError, match=match):
        multi_observable_fim(bad, np.array([1.0, 2.0]))
