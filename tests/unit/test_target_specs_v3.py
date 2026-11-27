"""Unit tests for the v3 multi-chemistry target-spec catalog (no PyBaMM).

Software correctness only: these tests parse YAML and exercise the auditable
lexicon/rubric. Scientific set/option verification lives in the integration
test (tests/integration/test_multichem_targets.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pybamm_closed_loop.assembly import (
    ConditionFacts,
    MethodClass,
    Rubric,
)
from pybamm_closed_loop.cli_app.inputs import load_target
from pybamm_closed_loop.specifications import (
    TargetSpecError,
    default_catalog_dir,
    load_named_target,
    load_target_catalog,
)

ROOT = Path(__file__).resolve().parents[2]
V3 = ROOT / "configs" / "v3"
V0_2_TARGET = ROOT / "configs" / "v2" / "target_lgm50.yaml"

EXPECTED = {
    "lfp_graphite_prada2013": {
        "families": {"LFP", "graphite"},
        "parameter_set": "Prada2013",
        "model_options": {},
        "nmc_composition": None,
        "positive_ocp": "LFP_ocp_Afshar2017",
    },
    "nmc811_lgm50_oregan2022": {
        "families": {"NMC", "graphite"},
        "parameter_set": "ORegan2022",
        "model_options": {},
        "nmc_composition": "811",
        "positive_ocp": "nmc_LGM50_ocp_Chen2020",
    },
    "limetal_nmc_xu2019": {
        "families": {"NMC", "Li-metal"},
        "parameter_set": "Xu2019",
        "model_options": {"working electrode": "positive"},
        "nmc_composition": None,
        "positive_ocp": "nmc_ocp_Xu2019",
    },
}


class TestV3Catalog:
    def test_default_catalog_dir_is_repo_configs_v3(self):
        assert default_catalog_dir() == V3

    def test_catalog_loads_three_targets_deterministically(self):
        specs = load_target_catalog()
        assert [s.target_id for s in specs] == sorted(EXPECTED)
        assert len(specs) == 3

    def test_each_target_has_verified_provenance(self):
        for spec in load_target_catalog():
            expected = EXPECTED[spec.target_id]
            assert set(spec.chemistry_families) == expected["families"]
            assert spec.parameter_set == expected["parameter_set"]
            assert spec.model == "DFN"
            assert spec.model_options == expected["model_options"]
            assert spec.nmc_composition == expected["nmc_composition"]
            assert spec.verification["pybamm_version"] == "26.8.0.0"
            assert spec.verification["parameter_set"] == expected["parameter_set"]
            assert spec.verification["positive_ocp_function"] == expected["positive_ocp"]
            assert spec.verification["extraction_status"] == "verified_by_introspection"
            assert spec.verification["source_location"]

    def test_load_named_target(self):
        spec = load_named_target("limetal_nmc_xu2019")
        assert spec.parameter_set == "Xu2019"
        assert spec.model_options["working electrode"] == "positive"
        with pytest.raises(TargetSpecError, match="not found"):
            load_named_target("no_such_target")

    def test_coverage_meta_is_not_loaded_as_a_target(self):
        assert (V3 / "chemistry_coverage.meta.yaml").is_file()
        assert all(s.target_id != "coverage" for s in load_target_catalog())

    def test_coverage_record_declares_no_fabricated_set(self):
        raw = yaml.safe_load((V3 / "chemistry_coverage.meta.yaml").read_text())
        assert raw["pybamm_version"] == "26.8.0.0"
        assert {entry["parameter_set"] for entry in raw["coverage"]} == {
            spec.parameter_set for spec in load_target_catalog()
        }
        unresolved = {entry["item"] for entry in raw["unresolved"]}
        assert any("NMC811" in item for item in unresolved)
        assert all(entry["status"] == "UNRESOLVED" for entry in raw["unresolved"])


class TestV02Compatibility:
    def test_v02_target_still_loads_with_legacy_defaults(self):
        spec = load_target(V0_2_TARGET)
        assert spec.target_id == "lgm50_chen2020_dfn"
        assert spec.parameter_set == "Chen2020"
        assert set(spec.chemistry_families) == {"NMC", "graphite"}
        assert spec.model_options == {}
        assert spec.nmc_composition is None
        assert spec.verification == {}

    def test_v02_target_is_not_changed_by_catalog_loading(self):
        before = (V0_2_TARGET).read_text(encoding="utf-8")
        load_target_catalog()
        assert (V0_2_TARGET).read_text(encoding="utf-8") == before


class TestCatalogValidation:
    def _write(self, tmp_path, data, name="target_bad.yaml"):
        path = tmp_path / name
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return path

    def test_unknown_chemistry_family_rejected(self, tmp_path):
        self._write(
            tmp_path,
            {
                "target": {
                    "target_id": "bad_family",
                    "cell_product": "X",
                    "chemistry_families": ["UNKNOWN_FAMILY"],
                    "parameter_set": "Chen2020",
                }
            },
        )
        with pytest.raises(TargetSpecError, match="unknown chemistry family"):
            load_target_catalog(tmp_path)

    def test_duplicate_target_id_rejected(self, tmp_path):
        body = {
            "target": {
                "target_id": "duplicate",
                "cell_product": "X",
                "chemistry_families": ["NMC"],
                "parameter_set": "Chen2020",
            }
        }
        self._write(tmp_path, body, "target_a.yaml")
        self._write(tmp_path, body, "target_b.yaml")
        with pytest.raises(TargetSpecError, match="duplicate target_id"):
            load_target_catalog(tmp_path)

    def test_invalid_nmc_composition_rejected(self, tmp_path):
        self._write(
            tmp_path,
            {
                "target": {
                    "target_id": "bad_comp",
                    "cell_product": "X",
                    "chemistry_families": ["NMC"],
                    "parameter_set": "Chen2020",
                    "nmc_composition": "not-a-number",
                }
            },
        )
        with pytest.raises(TargetSpecError, match="nmc_composition"):
            load_target_catalog(tmp_path)

    def test_bad_model_options_mapping_rejected(self, tmp_path):
        path = self._write(
            tmp_path,
            {
                "target": {
                    "target_id": "bad_options",
                    "cell_product": "X",
                    "chemistry_families": ["NMC"],
                    "parameter_set": "Chen2020",
                    "model_options": {"working electrode": 5},
                }
            },
        )
        with pytest.raises(SystemExit, match="strings to strings"):
            load_target(path)


class TestNMC811Applicability:
    """The composition label must affect applicability without blocking family matches."""

    @staticmethod
    def _candidate(composition_text):
        from pybamm_closed_loop.assembly import CandidateValue

        return CandidateValue(
            canonical_id="positive_particle_diffusivity",
            value=1.0,
            unit="m2.s-1",
            canonical_value=1.0,
            canonical_unit="m2.s-1",
            method_class=MethodClass.MEASURED,
            method="test method",
            status="LITERATURE_DERIVED",
            conditions=ConditionFacts(
                cell_product=None,
                format=None,
                chemistry_families=("NMC", "graphite"),
                temperature_k=298.15,
                raw={"chemistry": composition_text},
            ),
            source_id="doc-a",
            source_document="doc-a",
            source_locator="Table 1",
            quote_present=False,
        )

    def test_nmc111_candidate_is_downgraded_for_nmc811_target(self):
        target = load_named_target("nmc811_lgm50_oregan2022")
        rubric = Rubric("rubric-v3-unit")
        matching = rubric.evaluate(self._candidate("NMC811"), target)
        different = rubric.evaluate(self._candidate("NMC111"), target)
        assert matching.dimension_scores["chemistry"] == pytest.approx(0.6)
        assert different.dimension_scores["chemistry"] == pytest.approx(0.25)
        assert different.total < matching.total
        assert not different.blockers  # composition mismatch is not a blocker

    def test_family_mismatch_still_blocks(self):
        target = load_named_target("nmc811_lgm50_oregan2022")
        candidate = self._candidate("NMC811")
        candidate.conditions = ConditionFacts(
            cell_product=None,
            chemistry_families=("LCO",),  # no overlap with {NMC, graphite}
            temperature_k=298.15,
        )
        outcome = Rubric("rubric-v3-unit").evaluate(candidate, target)
        assert outcome.dimension_scores["chemistry"] == 0.0
        assert outcome.blockers
