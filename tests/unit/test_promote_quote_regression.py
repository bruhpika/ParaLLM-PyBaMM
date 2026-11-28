"""Step 3 regressions: promote quote/value association.

These are direct tests of the deterministic quote check; no model calls and no
data/results edits. All quote strings are labelled synthetic fixtures.
"""

from __future__ import annotations

import pytest

from pybamm_closed_loop.cli_app.commands.promote import _quote_supports


def _check(name: str, value, unit: str, quote: str, expected_unit: str):
    payload = {"parameter_name": name, "value": value, "unit": unit,
               "source": {"quote": quote, "document_id": "synthetic"}}
    return _quote_supports(payload, quote, expected_unit)


ACCEPT = [
    ("neg_particle_radius", 5.86, "um", "The negative particle radius is 5.86 um.", "m"),
    ("cation_transference_number", 0.26, "dimensionless",
     "The cation transference number is 0.26 in this electrolyte.", "dimensionless"),
    ("neg_electrode_porosity", 0.25, "%",
     "The negative electrode porosity is 25 % in this cell.", "fraction"),
    ("neg_electrode_porosity", 0.25, "dimensionless",
     "The negative electrode porosity is 0.25.", "dimensionless"),
    ("neg_particle_radius", 5.86, "um",
     "The radius of the negative electrode particles is 5.86 um.", "m"),
    ("neg_particle_diffusivity", 3.3e-14, "m2 s-1",
     "negative particle diffusivity is 3.3e-14 m2 s-1.", "m2.s-1"),
    ("neg_particle_diffusivity", 3.3e-14, "m2 s-1",
     "negative particle diffusivity is 3.3 x 10-14 m2 s-1.", "m2.s-1"),
    ("neg_particle_diffusivity", 3.3e-14, "m2 s-1",
     "negative particle diffusivity is 3.3 x 10^-14 m2 s-1.", "m2.s-1"),
]


REFUSE = [
    ("neg_particle_radius", 5.86, "mm", "The negative particle radius is 5.86 um.", "m"),
    ("pos_particle_radius", 5.86, "um", "The particle radius is 5.86 um", "m"),
    ("neg_particle_radius", 5.86, "um", "5.86 um and 9.50 um", "m"),
    ("neg_particle_radius", 5.86, "um", "5.22 and 5.86 um", "m"),
    ("neg_particle_radius", 5.86, "um", "between 5.86 and 9.50 um", "m"),
    ("ambient_temperature", 298.15, "K", "ambient 300.15 K and reference 298.15 K", "K"),
]


@pytest.mark.parametrize("name,value,unit,quote,expected", ACCEPT)
def test_accepted_quotes(name, value, unit, quote, expected):
    ok, why = _check(name, value, unit, quote, expected)
    assert ok, why


@pytest.mark.parametrize("name,value,unit,quote,expected", REFUSE)
def test_refused_quotes(name, value, unit, quote, expected):
    ok, why = _check(name, value, unit, quote, expected)
    assert not ok, f"unexpectedly accepted: {quote}"
