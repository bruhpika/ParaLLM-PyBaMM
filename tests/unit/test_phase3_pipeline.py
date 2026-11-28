"""Unit checks for extraction/validation behaviour (Phase 3 bugs).

The full public-CLI chain into PyBaMM lives in
tests/integration/test_export_chain_to_pybamm.py.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from pybamm_closed_loop.cli import main
from pybamm_closed_loop.literature.extraction import OfflineDeterministicExtractor
from pybamm_closed_loop.literature.retrieval import RetrievedSegment

ROOT = Path(__file__).resolve().parents[2]


def _cli_json(tmp_path, args) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main([*_config(tmp_path), "--quiet", "--json", *args])
    assert rc == 0, f"CLI failed: {args}: {buf.getvalue()}"
    output = buf.getvalue()
    return json.loads(output[output.index("{"):])


def _config(tmp_path):
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path):
    assert main([*_config(tmp_path), "init", "--workspace",
                 str(tmp_path / "ws"), "--non-interactive"]) == 0


class TestPhase3Bugs:
    def test_3a_validate_accepts_extract_output(self, tmp_path):
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
        envelope = _cli_json(tmp_path, ["validate", str(candidates_file), "--strict"])
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
