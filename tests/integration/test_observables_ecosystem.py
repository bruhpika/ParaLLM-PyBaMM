"""Ecosystem-gated integration test for forward observables.

Skipped unless PyBOP is importable (use the .venv-ecosystem312 interpreter).
The check only confirms that observable arrays can be packaged as PyBOP
datasets; it is not a fit and never constitutes experimental validation.
"""

from __future__ import annotations

import numpy as np
import pytest

pybamm = pytest.importorskip("pybamm")
pybop = pytest.importorskip("pybop")

from pybamm_closed_loop.pybamm_engine.observables import (  # noqa: E402
    compute_eis,
    compute_ocv_vs_soc,
)


def test_observable_arrays_package_as_pybop_datasets():
    pv = pybamm.ParameterValues("Chen2020")

    eis = compute_eis("SPM", pv, np.array([1.0, 10.0]), initial_soc=0.5)
    eis_dataset = pybop.Dataset(
        {
            "Frequency [Hz]": eis.frequencies_Hz,
            "Z_re [Ohm]": eis.z_re_Ohm,
            "Z_im [Ohm]": eis.z_im_Ohm,
        }
    )
    assert set(eis_dataset.data) == {"Frequency [Hz]", "Z_re [Ohm]", "Z_im [Ohm]"}

    ocv = compute_ocv_vs_soc(pv, np.array([0.0, 0.5, 1.0]))
    ocv_dataset = pybop.Dataset({"SOC": ocv.soc, "Voltage [V]": ocv.ocv_V})
    assert np.asarray(ocv_dataset.data["Voltage [V]"]).shape == (3,)

    # Provenance: model-generated only, with pinned versions recorded.
    assert eis.metadata["synthetic_only"] is True
    assert ocv.metadata["synthetic_only"] is True
    assert eis.metadata["pybamm_version"] == "26.8.0.0"
    assert pybop.__version__
