"""Integration tests for forward observables against pinned PyBaMM 26.8.0.0.

Short protocols only: these run under the default (fast) pytest selection.
Every result is model-generated; no experimental data is claimed.
"""

from __future__ import annotations

import numpy as np
import pytest

pybamm = pytest.importorskip("pybamm")

from pybamm_closed_loop.pybamm_engine.observables import (  # noqa: E402
    compute_eis,
    compute_ocv_vs_soc,
    dqdv_from_solution,
    gitt_relaxation_summary,
    run_gitt_d,
    verified_api_signatures,
)

PARAMETER_SET = "Chen2020"


def test_verified_api_signatures_are_live_and_version_pinned():
    signatures = verified_api_signatures()
    assert signatures["pybamm.__version__"] == "26.8.0.0"
    assert signatures["EISSimulation.solve"].startswith(
        "EISSimulation.solve(self, frequencies, inputs=None, initial_soc=None)"
    )
    assert "get_initial_stoichiometries" in signatures


def test_eis_observable_on_installed_parameter_set():
    frequencies = np.logspace(-1, 2, 6)
    result = compute_eis(
        "SPM", pybamm.ParameterValues(PARAMETER_SET), frequencies, initial_soc=0.5
    )
    assert result.frequencies_Hz.shape == frequencies.shape
    assert np.all(np.isfinite(result.z_re_Ohm)) and np.all(np.isfinite(result.z_im_Ohm))
    assert np.all(result.z_re_Ohm > 0)
    assert np.all(result.z_im_Ohm < 0)
    np.testing.assert_allclose(result.impedance_Ohm.real, result.z_re_Ohm)
    assert result.metadata["pybamm_version"] == "26.8.0.0"
    assert result.metadata["synthetic_only"] is True


def test_ocv_soc_matches_parameter_set_endpoints_and_is_monotonic():
    pv = pybamm.ParameterValues(PARAMETER_SET)
    result = compute_ocv_vs_soc(pv, np.linspace(0.0, 1.0, 11))
    assert result.ocv_V.shape == (11,)
    assert np.all(np.diff(result.ocv_V) > 0)
    assert result.ocv_V[0] == pytest.approx(pv["Open-circuit voltage at 0% SOC [V]"], abs=1e-6)
    assert result.ocv_V[-1] == pytest.approx(pv["Open-circuit voltage at 100% SOC [V]"], abs=1e-6)
    assert np.all((result.x_negative >= 0) & (result.x_negative <= 1))
    assert np.all((result.y_positive >= 0) & (result.y_positive <= 1))
    assert result.metadata["synthetic_only"] is True


def test_dqdv_from_short_galvanostatic_discharge():
    model = pybamm.lithium_ion.SPM()
    experiment = pybamm.Experiment(["Discharge at 1C for 120 s"], period="10 s")
    sim = pybamm.Simulation(
        model, experiment=experiment, parameter_values=pybamm.ParameterValues(PARAMETER_SET)
    )
    solution = sim.solve()
    result = dqdv_from_solution(solution)
    assert result.dqdv_Ah_per_V.shape == result.capacity_Ah.shape
    assert np.all(np.isfinite(result.dqdv_Ah_per_V))
    assert result.metadata["direction"] == "discharge"
    assert result.capacity_Ah[0] < result.capacity_Ah[-1]


def test_gitt_d_short_protocol_and_relaxation_summary():
    result = run_gitt_d(
        pybamm.ParameterValues(PARAMETER_SET),
        current_A=0.5,
        pulse_duration_s=20.0,
        rest_duration_s=20.0,
        n_pulses=2,
        period_s=5.0,
    )
    assert result.time_s.shape == result.voltage_V.shape
    assert result.phase.count("pulse") > 0 and result.phase.count("rest") > 0
    assert set(int(i) for i in result.titration_index if i >= 0) == {0, 1}
    assert result.capacity_Ah[-1] > result.capacity_Ah[0]
    assert result.metadata["soc_estimate_from_capacity"] is not None
    summary = gitt_relaxation_summary(result)
    assert [row["titration_index"] for row in summary] == [0, 1]
    assert all(np.isfinite(row["voltage_V"]) for row in summary)
    assert result.metadata["synthetic_only"] is True
