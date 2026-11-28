"""Phase 5 integration: public-CLI chain from extraction into PyBaMM.

No extractor, validator or promoter output is edited. The only human-authored
files are clearly labelled SYNTHETIC review and gate files. The value is a
labelled synthetic assumption (300.15 K), deliberately different from the
Chen2020 default.
"""

from __future__ import annotations

import ast
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from pybamm_closed_loop.cli import main
from pybamm_closed_loop.pybamm_engine import apply_export_overlay

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "configs" / "v2" / "target_lgm50.yaml"
REGISTRY_DIR = ROOT / "data" / "registry"
SYNTHETIC_VALUE = 300.15
PYBAMM_NAME = "Ambient temperature [K]"


def _config(tmp_path):
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path):
    assert main([*_config(tmp_path), "init", "--workspace",
                 str(tmp_path / "ws"), "--non-interactive"]) == 0


def _cli_json(tmp_path, args) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main([*_config(tmp_path), "--quiet", "--json", *args])
    assert rc == 0, f"CLI failed: {args}: {buf.getvalue()}"
    output = buf.getvalue()
    return json.loads(output[output.index("{"):])


def _synthetic_document(tmp_path: Path) -> Path:
    source = tmp_path / "synthetic.txt"
    source.write_text(
        "SYNTHETIC FIXTURE -- NOT A REAL PAPER VALUE.\n"
        "Table I. The ambient temperature was assumed to be 300.15 K "
        "in a synthetic chamber at 25 C.\n",
        encoding="utf-8",
    )
    return source


def test_synthetic_chain_extract_to_pybamm(tmp_path):
    """extract -> validate -> review -> promote -> assemble -> approve -> export -> PyBaMM."""
    _init(tmp_path)
    source = _synthetic_document(tmp_path)

    # 1. extract (public CLI, offline provider)
    extracted = tmp_path / "extract"
    assert main([*_config(tmp_path), "--quiet", "extract", str(source),
                 "--out", str(extracted), "--parameter", "ambient_temperature"]) == 0
    candidates = extracted / "candidates.json"
    data = json.loads(candidates.read_text(encoding="utf-8"))
    assert data["n_candidates"] == 1

    # 2. validate --json: save the EXACT output, with no edits.
    envelope = _cli_json(tmp_path, [
        "validate", str(candidates),
        "--documents", str(extracted / "literature_store"),
        "--registry", str(REGISTRY_DIR),
    ])
    result = envelope["data"]["results"][0]
    assert result["state"] in ("ACCEPTED", "NEEDS_REVIEW")
    digest = result["candidate_hash"]
    validated_path = tmp_path / "validated.json"
    validated_path.write_text(json.dumps(envelope), encoding="utf-8")

    # 3. SYNTHETIC human review: binds the exact candidate hash and records why.
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps({"reviews": [{
        "parameter": "ambient_temperature",
        "candidate_hash": digest,
        "reviewer": "SYNTHETIC-OWNER",
        "decision": "APPROVED",
        "timestamp": "2026-11-28T00:00:00Z",
        "reason": "SYNTHETIC labelled fixture: assumed value accepted for the chain test",
    }]}), encoding="utf-8")

    # 4. promote: raw validate output, no unwrapping or editing by hand.
    registry_path = tmp_path / "new_registry.json"
    assert main([*_config(tmp_path), "--quiet", "promote", str(validated_path),
                 "--review", str(review_path),
                 "--documents", str(extracted / "literature_store"),
                 "--out", str(registry_path)]) == 0
    records = json.loads(registry_path.read_text(encoding="utf-8"))
    record = next(r for r in records if r["canonical_id"] == "ambient_temperature")
    assert record["value"] == SYNTHETIC_VALUE
    assert record["pybamm_names"] == [PYBAMM_NAME]

    # 5. assemble: writes the fail-closed pending gate.
    first = tmp_path / "assembly_first"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(registry_path), "--out", str(first)]) == 0
    report = json.loads((first / "report.json").read_text(encoding="utf-8"))
    dossier = next(d for d in report["parameters"] if d["parameter"] == "ambient_temperature")
    assert dossier["decision"] in ("USE", "FIX")
    pending = json.loads((first / "gate.pending.json").read_text(encoding="utf-8"))
    entry = next(r for r in pending["approvals"] if r["parameter"] == "ambient_temperature")
    assert entry["approved"] is False

    # 6. approve: SYNTHETIC gate file, edited only by the test as a human proxy.
    entry.update(approved=True, approver="SYNTHETIC-OWNER",
                 timestamp="2026-11-28T00:00:00Z",
                 note="SYNTHETIC approval of the labelled fixture")
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps({"approvals": [entry]}), encoding="utf-8")

    final = tmp_path / "assembly_final"
    assert main([*_config(tmp_path), "--quiet", "assemble", "--target", str(TARGET),
                 "--registry", str(registry_path), "--out", str(final),
                 "--gate", str(gate_path)]) == 0

    # 7. export --format pybamm, then load into pybamm.ParameterValues.
    overlay_file = tmp_path / "params.py"
    export_envelope = _cli_json(tmp_path, [
        "export", "--format", "pybamm", "--from", str(final),
        "--output", str(overlay_file),
    ])
    assert export_envelope["data"]["attestation"]["level"] == "ATTESTED"
    source_text = overlay_file.read_text(encoding="utf-8")
    assert source_text.startswith("PARAMETERS = ")
    overlay = ast.literal_eval(source_text.split("=", 1)[1].strip())
    assert overlay[PYBAMM_NAME] == SYNTHETIC_VALUE

    parameter_values = apply_export_overlay("Chen2020", overlay)
    assert float(parameter_values[PYBAMM_NAME]) == SYNTHETIC_VALUE
    # The synthetic value is not the installed Chen2020 default.
    baseline = apply_export_overlay("Chen2020", {})
    assert float(baseline[PYBAMM_NAME]) != SYNTHETIC_VALUE


def test_chain_rejects_tampered_candidate_hash(tmp_path):
    """A review hash that does not match the extracted candidate promotes nothing."""
    _init(tmp_path)
    source = _synthetic_document(tmp_path)
    extracted = tmp_path / "extract"
    assert main([*_config(tmp_path), "--quiet", "extract", str(source),
                 "--out", str(extracted), "--parameter", "ambient_temperature"]) == 0
    envelope = _cli_json(tmp_path, [
        "validate", str(extracted / "candidates.json"),
        "--documents", str(extracted / "literature_store"),
        "--registry", str(REGISTRY_DIR),
    ])
    validated_path = tmp_path / "validated.json"
    validated_path.write_text(json.dumps(envelope), encoding="utf-8")
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps({"reviews": [{
        "parameter": "ambient_temperature", "candidate_hash": "0" * 64,
        "reviewer": "SYNTHETIC-OWNER", "decision": "APPROVED",
        "timestamp": "2026-11-28T00:00:00Z", "reason": "SYNTHETIC mismatch test",
    }]}), encoding="utf-8")
    assert main([*_config(tmp_path), "--quiet", "promote", str(validated_path),
                 "--review", str(review_path),
                 "--documents", str(extracted / "literature_store"),
                 "--out", str(tmp_path / "should_not_exist.json")]) == 2
    assert not (tmp_path / "should_not_exist.json").exists()
