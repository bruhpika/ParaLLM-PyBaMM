"""Unit tests for forward-observable extraction using fakes (no PyBaMM simulation).

These tests exercise only pure post-processing helpers. PyBaMM-facing wrappers
are covered by tests/integration/test_observables_pybamm.py.
"""

from __future__ import annotations

import numpy as np
import pytest

from pybamm_closed_loop.pybamm_engine.observables import (
    DqDvResult,
    GittdResult,
    dqdv_from_capacity_voltage,
    dqdv_from_solution,
    extract_eis_arrays,
    gitt_phase_labels,
    gitt_relaxation_summary,
    ocv_from_stoichiometries,
)


class FakeEisSolution:
    """Stand-in for the verified EISSolution dict interface."""

    def __init__(self, data, impedance=None):
        self._data = data
        if impedance is not None:
            self.impedance = np.asarray(impedance, dtype=complex)

    def get_data_dict(self):
        return self._data


class FakeSolution:
    def __init__(self, variables):
        self._variables = variables

    def __getitem__(self, name):
        value = self._variables[name]
        return type("Var", (), {"entries": np.asarray(value, dtype=float)})()


def test_ocv_from_stoichiometries_with_fake_ocp_functions():
    x = np.array([0.1, 0.5])
    y = np.array([0.8, 0.4])
    negative = lambda sto: 0.1 + 0.2 * sto
    positive = lambda sto: 4.2 - 0.3 * sto
    ocv = ocv_from_stoichiometries(x, y, negative, positive)
    np.testing.assert_allclose(
        ocv,
        [4.2 - 0.3 * 0.8 - (0.1 + 0.2 * 0.1), 4.2 - 0.3 * 0.4 - (0.1 + 0.2 * 0.5)],
    )


def test_ocv_from_stoichiometries_rejects_mismatched_shapes():
    with pytest.raises(ValueError, match="same shape"):
        ocv_from_stoichiometries([0.1, 0.2], [0.3], lambda s: s, lambda s: s)


def test_dqdv_linear_curve_matches_analytic_derivative():
    q = np.linspace(0.0, 5.0, 51)
    v = 4.2 - 0.1 * q  # dQ/dV = -10 Ah/V (discharge convention)
    result = dqdv_from_capacity_voltage(q, v)
    assert isinstance(result, DqDvResult)
    assert result.metadata["direction"] == "discharge"
    np.testing.assert_allclose(result.dqdv_Ah_per_V, -10.0, rtol=1e-10)
    assert result.metadata["sign_convention"] == "gradient(Q, V): negative on discharge"


def test_dqdv_charge_branch_has_positive_slope():
    q = np.linspace(0.0, 2.0, 21)
    v = 3.5 + 0.25 * q
    result = dqdv_from_capacity_voltage(q, v)
    assert result.metadata["direction"] == "charge"
    np.testing.assert_allclose(result.dqdv_Ah_per_V, 4.0, rtol=1e-10)


@pytest.mark.parametrize(
    "q, v, match",
    [
        ([0, 0, 1], [4, 3, 2], "strictly increasing"),
        ([0, 1, 2], [4, 3, 4], "monotonic"),
        ([0, 1, 2], [4, 4, 3], "flat"),
        ([0, 1], [4, 3], "at least 3"),
        ([0, 1, 2], [4, np.nan, 3], "non-finite"),
    ],
)
def test_dqdv_rejects_invalid_curves(q, v, match):
    with pytest.raises(ValueError, match=match):
        dqdv_from_capacity_voltage(q, v)


def test_dqdv_from_solution_uses_verified_variable_names():
    q = np.linspace(0.0, 1.0, 11)
    v = 4.1 - 0.2 * q
    sol = FakeSolution({"Discharge capacity [A.h]": q, "Terminal voltage [V]": v})
    result = dqdv_from_solution(sol)
    np.testing.assert_allclose(result.dqdv_Ah_per_V, -5.0, rtol=1e-10)
    assert "Discharge capacity [A.h]" in result.metadata["source"]


def test_extract_eis_arrays_uses_verified_keys_and_complex_array():
    freq = np.array([0.1, 1.0, 10.0])
    re = np.array([0.03, 0.02, 0.01])
    im = np.array([-0.01, -0.02, -0.03])
    sol = FakeEisSolution(
        {"Frequency [Hz]": freq, "Z_re [Ohm]": re, "Z_im [Ohm]": im},
        impedance=re + 1j * im,
    )
    result = extract_eis_arrays(sol)
    np.testing.assert_array_equal(result.frequencies_Hz, freq)
    np.testing.assert_array_equal(result.z_re_Ohm, re)
    np.testing.assert_allclose(result.impedance_Ohm, re + 1j * im)
    assert result.metadata["complex_impedance_source"] == "EISSolution.impedance"


def test_extract_eis_arrays_falls_back_to_re_im_without_complex_attribute():
    data = {
        "Frequency [Hz]": [1.0, 10.0],
        "Z_re [Ohm]": [0.02, 0.01],
        "Z_im [Ohm]": [-0.01, -0.02],
    }
    result = extract_eis_arrays(FakeEisSolution(data))
    np.testing.assert_allclose(result.impedance_Ohm, [0.02 - 0.01j, 0.01 - 0.02j])
    assert "get_data_dict" in result.metadata["complex_impedance_source"]


def test_extract_eis_arrays_reports_missing_verified_key():
    sol = FakeEisSolution({"Frequency [Hz]": [1.0], "Z_re [Ohm]": [0.02]})
    with pytest.raises(KeyError, match="Z_im"):
        extract_eis_arrays(sol)


def test_gitt_phase_labels_track_pulses_and_titrations():
    phases, indices = gitt_phase_labels([1.0, 1.0, 0.0, 0.0, 1.0, 0.0])
    assert phases == ["pulse", "pulse", "rest", "rest", "pulse", "rest"]
    np.testing.assert_array_equal(indices, [0, 0, 0, 0, 1, 1])


def test_gitt_relaxation_summary_takes_last_rest_point_per_titration():
    result = GittdResult(
        time_s=np.array([0.0, 5.0, 10.0, 15.0, 20.0, 25.0]),
        voltage_V=np.array([4.2, 4.1, 4.15, 4.05, 4.1, 4.12]),
        current_A=np.array([0.5, 0.5, 0.0, 0.5, 0.0, 0.0]),
        capacity_Ah=np.array([0.0, 0.01, 0.01, 0.02, 0.02, 0.02]),
        phase=["pulse", "pulse", "rest", "pulse", "rest", "rest"],
        titration_index=np.array([0, 0, 0, 1, 1, 1]),
        metadata={"soc_estimate_from_capacity": np.array([1.0, 0.99, 0.99, 0.98, 0.98, 0.98])},
    )
    summary = gitt_relaxation_summary(result)
    assert [s["titration_index"] for s in summary] == [0, 1]
    assert summary[0]["voltage_V"] == pytest.approx(4.15)
    assert summary[1]["voltage_V"] == pytest.approx(4.12)
    assert summary[1]["soc_estimate"] == pytest.approx(0.98)
