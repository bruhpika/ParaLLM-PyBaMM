"""Unit tests for extraction, validation, evidence, provenance and export commands."""

from __future__ import annotations

import json

from pybamm_closed_loop.cli import main

QUOTE = "The mean particle radius is 5.86 um by SEM."


def _config(tmp_path):
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path):
    assert main([*_config(tmp_path), "init", "--workspace", str(tmp_path / "ws"), "--non-interactive"]) == 0


def _registry(tmp_path):
    record = {
        "canonical_id": "neg_particle_radius",
        "definition": "negative particle radius",
        "value": 5.86e-6,
        "value_unit": "m",
        "normalized_value": 5.86e-6,
        "normalized_value_unit": "m",
        "status": "LITERATURE_DERIVED",
        "method": "SEM measurement",
        "source_id": "paper",
        "source_location": "Table II",
        "conditions": {"temperature_k": 298.15, "cell": "LG M50"},
        "pybamm_names": ["Negative particle radius [m]"],
        "evidence": {
            "value": 5.86e-6,
            "unit": "m",
            "kind": "LITERATURE_DERIVED",
            "source": {"document_id": "paper", "locator": "Table II", "page": None, "quote": QUOTE},
            "review_state": "ACCEPTED",
            "conditions": {},
        },
        "conflicts": [],
        "compatibility": {},
        "validation_state": "ACCEPTED",
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps([record]), encoding="utf-8")
    return path, record


def _payload():
    return {
        "parameter_name": "mean particle radius",
        "value": 5.86,
        "unit": "um",
        "definition": "particle radius",
        "material": "graphite",
        "temperature": 298.15,
        "cell_config": "LG M50",
        "measurement_method": "SEM",
        "qualifier": "measured",
        "context": QUOTE,
        "source": {"document_id": "paper", "locator": "Table II", "quote": QUOTE},
        "reported_uncertainty": None,
    }


def test_extract_text_then_validate_with_quote(tmp_path, capsys):
    _init(tmp_path)
    paper = tmp_path / "paper.txt"
    paper.write_text(QUOTE + "\n", encoding="utf-8")
    out = tmp_path / "extract"
    assert main([*_config(tmp_path), "extract", str(paper), "--out", str(out), "--parameter", "mean particle radius"]) == 0
    capsys.readouterr()
    candidates = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert candidates["n_candidates"] >= 1
    assert candidates["n_schema_valid"] >= 1
    assert all("CANDIDATES ONLY" not in str(c) for c in candidates["candidates"])

    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps([_payload()]), encoding="utf-8")
    assert main([
        *_config(tmp_path), "--json", "validate", str(payload_file),
        "--documents", str(out / "literature_store"),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    checks = {c["name"]: c["level"] for c in result["data"]["results"][0]["checks"]}
    assert checks["check_provenance"] == "PASSED"
    assert checks["schema"] == "PASSED"


def test_validate_without_documents_marks_provenance_not_checked(tmp_path, capsys):
    _init(tmp_path)
    capsys.readouterr()
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(_payload()), encoding="utf-8")
    assert main([*_config(tmp_path), "--json", "validate", str(payload_file)]) == 0
    result = json.loads(capsys.readouterr().out)
    checks = {c["name"]: c["level"] for c in result["data"]["results"][0]["checks"]}
    assert checks["check_provenance"] == "NOT CHECKED"
    assert result["data"]["summary"]["FAILED"] == 0


def test_validate_strict_fails_on_review(capsys):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "payload.json"
        path.write_text(json.dumps(_payload()), encoding="utf-8")
        assert main(["--json", "validate", str(path), "--strict"]) == 1
        result = json.loads(capsys.readouterr().out)
        assert result["data"]["results"][0]["state"] == "NEEDS_REVIEW"


def test_evidence_list_inspect_and_explain_use_real_fields(tmp_path):
    _init(tmp_path)
    registry, _ = _registry(tmp_path)
    assert main([*_config(tmp_path), "evidence", "list", "--registry", str(registry)]) == 0
    assert main([*_config(tmp_path), "evidence", "inspect", "neg_particle_radius", "--registry", str(registry)]) == 0
    assert main([*_config(tmp_path), "explain", "neg_particle_radius", "--registry", str(registry)]) == 0
    assert main([*_config(tmp_path), "--json", "explain", "missing", "--registry", str(registry)]) == 2


def test_export_refuses_overwrite_and_exports_only_approved(tmp_path, capsys):
    _init(tmp_path)
    capsys.readouterr()
    registry, record = _registry(tmp_path)
    source = tmp_path / "assembly"
    source.mkdir()
    (source / "pybamm_export.json").write_text(json.dumps({"neg_particle_radius": 5.86e-6}), encoding="utf-8")
    output = tmp_path / "export.json"
    args = [*_config(tmp_path), "--json", "export", "--from", str(source), "--output", str(output)]
    assert main(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload["data"]["parameters"]) == {"neg_particle_radius"}
    assert output.is_file()
    assert main([*_config(tmp_path), "export", "--from", str(source), "--output", str(output)]) == 2


def test_export_registry_requires_gate(tmp_path):
    _init(tmp_path)
    registry, _ = _registry(tmp_path)
    assert main([*_config(tmp_path), "export", "--from", str(registry), "--output", str(tmp_path / "no.json")]) == 2


def test_calibrate_reports_recorded_runs(capsys):
    assert main(["--json", "calibrate", "report", "--results", "results/p2"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["reports"]
    assert all("report" in item for item in payload["data"]["reports"])
