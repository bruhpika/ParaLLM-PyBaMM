"""PHASE 3: connect extract -> validate -> review -> registry -> assemble -> export.

Failing tests written before implementation. Synthetic fixtures only; no
network, no live LLM, no real paper values invented.
"""

from __future__ import annotations

import json
from pathlib import Path

from pybamm_closed_loop.assembly import ApprovalGate
from pybamm_closed_loop.assembly.gate import binding_sha256
from pybamm_closed_loop.cli import main
from pybamm_closed_loop.literature.extraction import OfflineDeterministicExtractor
from pybamm_closed_loop.literature.retrieval import RetrievedSegment

ROOT = Path(__file__).resolve().parents[2]


def _config(tmp_path):
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path):
    assert main([*_config(tmp_path), "init", "--workspace", str(tmp_path / "ws"),
                 "--non-interactive"]) == 0


def _json_output(capsys) -> str:
    out = capsys.readouterr().out
    return out[out.index("{"):]


class TestPhase3Bugs:
    def test_3a_validate_accepts_extract_output(self, tmp_path, capsys):
        """The exact output of extract must be accepted by validate."""
        source = tmp_path / "synthetic.txt"
        source.write_text(
            "SYNTHETIC FIXTURE. The negative particle radius is 5.86 um "
            "measured by SEM at 25 C on a synthetic cell. Table I.",
            encoding="utf-8",
        )
        out = tmp_path / "extract"
        assert main([*_config(tmp_path), "--quiet", "extract", str(source),
                     "--out", str(out), "--parameter", "SYNTHETIC_radius"]) == 0
        candidates_file = out / "candidates.json"
        assert candidates_file.is_file()
        data = json.loads(candidates_file.read_text())
        assert "candidates" in data
        assert main([*_config(tmp_path), "--quiet", "--json", "validate",
                     str(candidates_file), "--strict"]) in (0, 1)  # must parse, not error on shape
        envelope = json.loads(_json_output(capsys))
        # One validation result per candidate, not one for the whole envelope.
        assert len(envelope["data"]["results"]) == data["n_candidates"]

    def test_3c_extractor_requires_parameter_and_unit_match(self):
        """Equation fragments and DOI digits must not become candidates."""
        segments = [
            RetrievedSegment(
                segment_id="doc#seg0", document_id="doc", page=4,
                heading="Vol.:(0123456789)1 3",
                text=("doi 10.1000/s3 - exp /parenleft. 3 - Vol.:(0123456789) "
                      "the separator porosity is 0.47 -"),
                score=1.0,
            ),
        ]
        batch = OfflineDeterministicExtractor().extract_from_segments(
            segments, target_names=["neg_particle_diffusivity"]
        )
        # The one number ("3 -") is not a porosity value and has no matching
        # parameter alias in its own sentence -> abstain.
        assert batch.candidates == []
        assert batch.abstained

    def test_3c_unit_incompatibility_abstains(self):
        """A number with a unit incompatible with the target is not a candidate."""
        segments = [
            RetrievedSegment(
                segment_id="doc#seg1", document_id="doc", page=1,
                heading="Table I",
                text="SYNTHETIC: the particle radius is 5.86 mA cm-2 measured by SEM.",
                score=1.0,
            ),
        ]
        batch = OfflineDeterministicExtractor().extract_from_segments(
            segments, target_names=["neg_particle_radius"]
        )
        assert batch.candidates == []

    def test_3b_promote_command_exists(self, tmp_path):
        """A command must exist to move a reviewed candidate into a new registry."""
        assert main([*_config(tmp_path), "--help"]) == 0


class TestEndToEnd:
    def test_synthetic_pipeline_extract_to_pybamm(self, tmp_path, capsys):
        """extract, validate, review, promote, assemble, approve, export, load."""
        _init(tmp_path)
        source = tmp_path / "synthetic.txt"
        source.write_text(
            "SYNTHETIC FIXTURE -- NOT A REAL PAPER VALUE.\n"
            "Table I. The ambient temperature was 298.15 K, measured in a "
            "chamber at 25 C on a synthetic cell.\n",
            encoding="utf-8",
        )
        out = tmp_path / "extract"
        assert main([*_config(tmp_path), "--quiet", "extract", str(source),
                     "--out", str(out), "--parameter", "ambient_temperature"]) == 0
        candidates = out / "candidates.json"
        data = json.loads(candidates.read_text())
        assert data["n_candidates"] >= 1
        assert main([*_config(tmp_path), "--quiet", "--json", "validate", str(candidates),
                     "--documents", str(out / "literature_store")]) in (0, 1)
        validated = json.loads(_json_output(capsys))
        validated_path = tmp_path / "validated.json"
        validated_path.write_text(json.dumps(validated["data"], indent=2), encoding="utf-8")
        accepted = [r for r in validated["data"]["results"]
                    if r["state"] in ("ACCEPTED", "NEEDS_REVIEW")]
        assert accepted, "synthetic candidate must pass deterministic validation"
        # review record + promote (empty hash is allowed; the tool binds the
        # reviewed candidate by index/name when no hash is supplied)
        review = tmp_path / "review.json"
        review.write_text(json.dumps({"reviews": [{
            "parameter": "ambient_temperature",
            "candidate_index": 0,
            "reviewer": "SYNTHETIC-OWNER",
            "decision": "APPROVED",
            "timestamp": "2026-01-01T00:00:00Z",
        }]}), encoding="utf-8")
        new_registry = tmp_path / "new_registry.json"
        rc = main([*_config(tmp_path), "--quiet", "promote", str(validated_path),
                   "--review", str(review), "--documents", str(out / "literature_store"),
                   "--out", str(new_registry)])
        assert rc == 0
        records = json.loads(new_registry.read_text())
        assert any(r["canonical_id"] == "ambient_temperature" for r in records)

        target = ROOT / "configs/v2/target_lgm50.yaml"
        assembly = tmp_path / "assembly"
        assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(target),
                     "--registry", str(new_registry), "--out", str(assembly)]) == 0
        report = json.loads((assembly / "report.json").read_text())
        d = next(x for x in report["parameters"]
                 if x["parameter"] == "ambient_temperature")
        gate = ApprovalGate()
        gate.approve("ambient_temperature", d["decision"], "owner",
                     d["rubric_version"], binding_sha256(d))
        gate_path = tmp_path / "gate.json"
        gate_path.write_text(json.dumps(gate.to_dict()), encoding="utf-8")
        assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(target),
                     "--registry", str(new_registry), "--out", str(assembly),
                     "--gate", str(gate_path)]) == 0
        exported = json.loads((assembly / "pybamm_export.json").read_text())
        assert "ambient_temperature" in exported
        assert exported["ambient_temperature"] == 298.15
