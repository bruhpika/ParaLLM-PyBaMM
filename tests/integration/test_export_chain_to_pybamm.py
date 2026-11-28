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


# --- Step 1: SI conversion on export ---------------------------------------

def _candidate_from_quote(name: str, value, unit: str, quote: str, **extra) -> dict:
    """A clearly labelled synthetic candidate payload for a public-CLI chain."""
    payload = {
        "parameter_name": name,
        "value": value,
        "unit": unit,
        "definition": f"SYNTHETIC definition for {name}",
        "material": "graphite-SiOx (SYNTHETIC fixture)" if name.startswith("neg_") else "SYNTHETIC",
        "temperature": 298.15,
        "cell_config": "LG M50 21700 (SYNTHETIC fixture)",
        "measurement_method": "measured by SEM (SYNTHETIC fixture)",
        "qualifier": "measured",
        "context": quote,
        "source": {
            "document_id": "synth", "locator": "Synthetic line 1", "quote": quote,
        },
        "reported_uncertainty": None,
    }
    payload.update(extra)
    return payload


def _chain_to_pybamm(tmp_path: Path, candidate: dict, quote: str,
                     target: Path = TARGET, *, export_schema: int = 1):
    """validate -> review -> promote -> assemble -> approve -> export -> PyBaMM.

    Human actions are simulated only by clearly labelled SYNTHETIC review and
    gate files. No validator or promoter output is edited.
    """
    cfg = _config(tmp_path)
    docs = tmp_path / "docs" / "synth"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "synth_fulltext.txt").write_text(
        f"SYNTHETIC FIXTURE -- NOT A REAL PAPER VALUE.\n{quote}.\n", encoding="utf-8"
    )
    candidates = tmp_path / "candidates.json"
    candidates.write_text(json.dumps({"candidates": [{"payload": candidate}]}), encoding="utf-8")
    envelope = _cli_json(tmp_path, [
        "validate", str(candidates), "--documents", str(tmp_path / "docs"),
        "--registry", str(REGISTRY_DIR),
    ])
    result = envelope["data"]["results"][0]
    assert result["state"] in ("ACCEPTED", "NEEDS_REVIEW")
    digest = result["candidate_hash"]
    validated = tmp_path / "validated.json"
    validated.write_text(json.dumps(envelope), encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"reviews": [{
        "parameter": candidate["parameter_name"], "candidate_hash": digest,
        "reviewer": "SYNTHETIC-OWNER", "decision": "APPROVED",
        "timestamp": "2026-11-28T00:00:00Z",
        "reason": "SYNTHETIC labelled fixture for export-conversion test",
    }]}), encoding="utf-8")
    registry = tmp_path / "new_registry.json"
    assert main([*cfg, "--quiet", "promote", str(validated), "--review", str(review),
                 "--documents", str(tmp_path / "docs"), "--out", str(registry)]) == 0

    first = tmp_path / "assembly_first"
    assert main([*cfg, "--quiet", "assemble", "--target", str(target),
                 "--registry", str(registry), "--out", str(first)]) == 0
    pending = json.loads((first / "gate.pending.json").read_text(encoding="utf-8"))
    gate_entry = next(
        (r for r in pending["approvals"] if r["parameter"] == candidate["parameter_name"]),
        None,
    )
    assert gate_entry is not None, "candidate decision is not exportable"
    gate_entry.update(approved=True, approver="SYNTHETIC-OWNER",
                      timestamp="2026-11-28T00:00:00Z",
                      note="SYNTHETIC approval of labelled fixture")
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"approvals": [gate_entry]}), encoding="utf-8")
    final = tmp_path / "assembly_final"
    assert main([*cfg, "--quiet", "assemble", "--target", str(target),
                 "--registry", str(registry), "--out", str(final),
                 "--gate", str(gate)]) == 0

    overlay_file = tmp_path / "params.py"
    env = _cli_json(tmp_path, [
        "export", "--format", "pybamm", "--from", str(final), "--output", str(overlay_file),
    ])
    assert env["data"]["attestation"]["level"] == "ATTESTED"
    text = overlay_file.read_text(encoding="utf-8")
    return ast.literal_eval(text.split("=", 1)[1].strip()), final


def test_um_particle_radius_exports_converted_si_value(tmp_path):
    """5.86 um in the registry must reach PyBaMM as 5.86e-06 m, not 5.86."""
    _init(tmp_path)
    quote = "the negative particle radius is 5.86 um measured by SEM"
    candidate = _candidate_from_quote("neg_particle_radius", 5.86, "um", quote)
    overlay, _ = _chain_to_pybamm(tmp_path, candidate, quote)
    assert overlay["Negative particle radius [m]"] == 5.86e-06


def test_second_non_si_unit_exports_converted_si_value(tmp_path):
    """A second non-SI unit (cm) must also be converted on export."""
    _init(tmp_path)
    quote = "the electrode height is 6.5 cm measured on a synthetic cell"
    candidate = _candidate_from_quote("cell_electrode_height", 6.5, "cm", quote)
    overlay, _ = _chain_to_pybamm(tmp_path, candidate, quote)
    assert overlay["Electrode height [m]"] == 0.065


def test_reexport_preserves_converted_si_value(tmp_path):
    """A v2 exported artifact re-exports the converted value, still attested."""
    _init(tmp_path)
    quote = "the negative particle radius is 5.86 um measured by SEM"
    candidate = _candidate_from_quote("neg_particle_radius", 5.86, "um", quote)
    overlay, final = _chain_to_pybamm(tmp_path, candidate, quote, export_schema=2)
    assert overlay["Negative particle radius [m]"] == 5.86e-06
