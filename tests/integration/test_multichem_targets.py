"""Integration tests for the v3 multi-chemistry targets.

Software correctness only: real PyBaMM parameter sets are loaded and short,
deterministic simulations are built through ``pybamm_engine``. No scientific
performance claim is made here (that belongs in benchmarks/).
"""

from __future__ import annotations

import numpy as np
import pytest

from pybamm_closed_loop.pybamm_engine import (
    BaselineRunConfig,
    build_parameter_values,
    build_simulation,
    installed_parameter_sets,
    parameter_set_chemistry,
    parameter_set_ocp_names,
    run,
    validate_model_options,
)
from pybamm_closed_loop.specifications import load_named_target

pytestmark = pytest.mark.integration

TARGET_IDS = (
    "lfp_graphite_prada2013",
    "nmc811_lgm50_oregan2022",
    "limetal_nmc_xu2019",
)


def config_for(target, *, options=None, steps=None):
    """Build a pinned, version-checked run config from a v3 target spec."""
    raw = {
        "run_id": f"test_{target.target_id}",
        "description": "short deterministic v3 multi-chemistry check",
        "pybamm": {
            "required_version": target.verification.get("pybamm_version", "26.8.0.0"),
            "model": {
                "family": "lithium_ion",
                "name": target.model,
                "options": dict(target.model_options if options is None else options),
            },
            "parameter_set": target.parameter_set,
            "solver": {"name": "idaklu", "rtol": 1e-6, "atol": 1e-6},
        },
        "experiment": {"steps": list(steps or ["Discharge at 1C for 30 s"])},
        "outputs": {
            "series": ["Terminal voltage [V]", "Current [A]"],
            "profile_variables": [],
            "profile_time_fractions": [0.5],
        },
    }
    return BaselineRunConfig.model_validate(raw)


@pytest.fixture(scope="module", params=TARGET_IDS, ids=TARGET_IDS)
def target(request):
    return load_named_target(request.param)


def test_parameter_set_is_installed(target):
    assert target.parameter_set in installed_parameter_sets()
    assert target.verification["parameter_set"] == target.parameter_set


def test_chemistry_field_matches_declared_provenance(target):
    assert parameter_set_chemistry(target.parameter_set) == target.verification["chemistry_field"]


def test_ocp_functions_match_declared_chemistry(target):
    names = parameter_set_ocp_names(target.parameter_set)
    assert names["positive"] == target.verification["positive_ocp_function"]
    if "negative_ocp_function" in target.verification:
        assert names["negative"] == target.verification["negative_ocp_function"]
    if "negative_ocp" in target.verification:
        assert names["negative"] == "0.0"


def test_declared_model_options_are_valid(target):
    assert validate_model_options(target.model, target.model_options) == []


def test_parameter_values_load_for_each_chemistry(target):
    pv = build_parameter_values(config_for(target))
    assert "Terminal voltage [V]" in pv.keys() or pv["Upper voltage cut-off [V]"] > pv[
        "Lower voltage cut-off [V]"
    ]
    assert pv["Reference temperature [K]"] == pytest.approx(target.temperature_k)


def test_short_discharge_solves_with_declared_options(target):
    result = run(config_for(target))
    voltage = result.extraction.series["Terminal voltage [V]"]
    assert voltage.shape[0] > 1
    assert np.all(np.isfinite(voltage))
    assert voltage[-1] < voltage[0]
    config_block = result.manifest["pybamm"]
    assert config_block["parameter_set"]["chemistry"] == "lithium_ion"
    assert config_block["parameter_set"]["name"] == target.parameter_set
    assert config_block["options_requested"] == target.model_options
    assert config_block["options_effective"]["working electrode"] == target.model_options.get(
        "working electrode", "both"
    )


def test_limetal_requires_working_electrode_option():
    """The Li-metal set has no negative-electrode intercalation parameters.

    With the default two-electrode option the build must fail; the option
    declared in the v3 target spec is therefore necessary, not cosmetic.
    """
    target = load_named_target("limetal_nmc_xu2019")
    assert validate_model_options(target.model, {}) == []  # model builds, but...
    with pytest.raises(Exception):
        build_simulation(config_for(target, options={})).solve()
    # ...the declared half-cell option makes the same set solvable.
    result = run(config_for(target))
    assert np.all(np.isfinite(result.extraction.series["Terminal voltage [V]"]))


def test_v02_target_still_builds_with_default_options():
    """Regression guard: the v0.2 LG M50 target still uses Chen2020 defaults."""
    from pathlib import Path

    from pybamm_closed_loop.cli_app.inputs import load_target

    root = Path(__file__).resolve().parents[2]
    legacy = load_target(root / "configs" / "v2" / "target_lgm50.yaml")
    assert legacy.parameter_set == "Chen2020"
    assert legacy.model_options == {}
    result = run(config_for(legacy))
    assert np.all(np.isfinite(result.extraction.series["Terminal voltage [V]"]))
