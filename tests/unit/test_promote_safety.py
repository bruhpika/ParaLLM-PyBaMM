"""Phase 3 regression: promote must re-validate and bind reviews to candidates.

Bugs reproduced here (all synthetic, labelled fixtures; no live LLM):
- a value edited after validation was promoted with its original quote;
- a hand-written validation report with unit 'banana' was promoted;
- promote rejects the raw JSON emitted by `validate --json`;
- reviews without a candidate hash matched by parameter name;
- promoted records carried no PyBaMM names.
"""

from __future__ import annotations

import json
from pathlib import Path

from pybamm_closed_loop.cli import main
from pybamm_closed_loop.cli_app.commands.promote import _candidate_hash

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = ROOT / "data" / "registry"


def _config(tmp_path: Path) -> list[str]:
    return ["--config", str(tmp_path / "config.toml")]


def _init(tmp_path: Path) -> None:
    assert main([*_config(tmp_path), "init", "--workspace",
                 str(tmp_path / "ws"), "--non-interactive"]) == 0


def _envelope(capsys) -> dict:
    out = capsys.readouterr().out
    return json.loads(out[out.index("{"):])


def _documents(tmp_path: Path, quote: str = "ambient temperature was 298.15 K") -> Path:
    folder = tmp_path / "docs" / "synth"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "synth_fulltext.txt").write_text(
        f"SYNTHETIC FIXTURE -- NOT A REAL PAPER VALUE.\n{quote}.\n", encoding="utf-8"
    )
    return tmp_path / "docs"


def _candidate(value: float = 298.15, unit: str = "K",
               quote: str = "ambient temperature was 298.15 K") -> dict:
    return {
        "parameter_name": "ambient_temperature",
        "value": value,
        "unit": unit,
        "definition": "Ambient temperature",
        "material": "SYNTHETIC",
        "temperature": 298.15,
        "cell_config": "SYNTHETIC",
        "measurement_method": "measured in a chamber",
        "qualifier": "measured",
        "context": "synthetic fixture",
        "source": {"document_id": "synth", "locator": "Synthetic line 1", "quote": quote},
        "reported_uncertainty": None,
    }


def _write_envelope(tmp_path: Path, candidates: list[dict], documents: Path,
                    *, forge_state: str | None = None,
                    raw: bool = False, allow_failed: bool = False) -> tuple[Path, dict]:
    """Run validate with captured JSON and write its data (or raw envelope)."""
    import io
    from contextlib import redirect_stdout

    source = tmp_path / "candidates.json"
    source.write_text(json.dumps({"candidates": [{"payload": c} for c in candidates]}),
                      encoding="utf-8")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main([*_config(tmp_path), "--quiet", "--json", "validate", str(source),
                   "--documents", str(documents), "--registry", str(REGISTRY_DIR)])
    assert rc == 0 or (allow_failed and rc == 1), f"validate failed: {rc}"
    output = buf.getvalue()
    envelope = json.loads(output[output.index("{"):])
    if forge_state is not None:
        envelope["data"]["results"][0]["state"] = forge_state
    path = tmp_path / "validated.json"
    path.write_text(json.dumps(envelope if raw else envelope["data"], indent=2), encoding="utf-8")
    return path, envelope


def _review(tmp_path: Path, candidates: list[dict], *, hash_value: str | None = None,
            reason: str = "SYNTHETIC human review of a labelled fixture",
            decision: str = "APPROVED") -> Path:
    records = []
    for candidate in candidates:
        record = {
            "parameter": candidate["parameter_name"],
            "candidate_hash": _candidate_hash(candidate) if hash_value is None else hash_value,
            "reviewer": "SYNTHETIC-OWNER",
            "decision": decision,
            "timestamp": "2026-11-28T00:00:00Z",
            "reason": reason,
        }
        records.append(record)
    path = tmp_path / "review.json"
    path.write_text(json.dumps({"reviews": records}), encoding="utf-8")
    return path


def _promote(tmp_path: Path, validated: Path, review: Path, documents: Path,
             out_name: str = "registry.json") -> int:
    return main([*_config(tmp_path), "--quiet", "--json", "promote", str(validated),
                 "--review", str(review), "--documents", str(documents),
                 "--out", str(tmp_path / out_name)])


def test_validate_emits_candidate_hash(tmp_path, capsys):
    """validate --json must expose the hash a human can put in a review."""
    _init(tmp_path)
    documents = _documents(tmp_path)
    _, envelope = _write_envelope(tmp_path, [_candidate()], documents)
    result = envelope["data"]["results"][0]
    assert result.get("candidate_hash") == _candidate_hash(_candidate())


def test_promote_accepts_raw_validate_json(tmp_path):
    """The exact JSON emitted by validate --json must be accepted as-is."""
    _init(tmp_path)
    documents = _documents(tmp_path)
    validated, _ = _write_envelope(tmp_path, [_candidate()], documents, raw=True)
    review = _review(tmp_path, [_candidate()])
    assert _promote(tmp_path, validated, review, documents) == 0
    records = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))
    assert records[0]["canonical_id"] == "ambient_temperature"


def test_promote_rejects_value_edited_after_validation(tmp_path, capsys):
    """A value edited after validation is not supported by the original quote."""
    _init(tmp_path)
    documents = _documents(tmp_path)
    validated, _ = _write_envelope(tmp_path, [_candidate()], documents)
    payload = json.loads(validated.read_text(encoding="utf-8"))
    # Edit only the value; the reported state, quote and hash claim stay put.
    payload["candidates"][0]["value"] = 299.15  # plausible, but not in the quote
    validated.write_text(json.dumps(payload), encoding="utf-8")
    tampered = _candidate(value=299.15)
    review = _review(tmp_path, [tampered])
    assert _promote(tmp_path, validated, review, documents) == 2
    text = json.dumps(_envelope(capsys)["diagnostics"])
    assert "value is not supported by the recorded quote" in text


def test_promote_rejects_unknown_unit(tmp_path):
    """An unknown unit must never be promoted."""
    _init(tmp_path)
    documents = _documents(tmp_path, "ambient temperature was 298.15 banana")
    bad = _candidate(unit="banana", quote="ambient temperature was 298.15 banana")
    validated, _ = _write_envelope(tmp_path, [bad], documents, allow_failed=True)
    review = _review(tmp_path, [bad])
    assert _promote(tmp_path, validated, review, documents) == 2


def test_promote_reruns_validation_ignoring_input_state(tmp_path):
    """A hand-written ACCEPTED state cannot override deterministic validation."""
    _init(tmp_path)
    documents = _documents(tmp_path, "ambient temperature was 298.15 banana")
    bad = _candidate(unit="banana", quote="ambient temperature was 298.15 banana")
    validated, _ = _write_envelope(tmp_path, [bad], documents, forge_state="ACCEPTED",
                                   allow_failed=True)
    review = _review(tmp_path, [bad])
    assert _promote(tmp_path, validated, review, documents) == 2


def test_promote_requires_nonempty_candidate_hash(tmp_path):
    """A review without a candidate hash must be rejected."""
    _init(tmp_path)
    documents = _documents(tmp_path)
    validated, _ = _write_envelope(tmp_path, [_candidate()], documents)
    review = _review(tmp_path, [_candidate()], hash_value="")
    assert _promote(tmp_path, validated, review, documents) == 2


def test_promote_requires_exactly_one_matching_candidate(tmp_path, capsys):
    """A review hash must match exactly one candidate (no matches)."""
    _init(tmp_path)
    documents = _documents(tmp_path)
    validated, _ = _write_envelope(tmp_path, [_candidate()], documents)
    review = _review(tmp_path, [_candidate()], hash_value="f" * 64)
    assert _promote(tmp_path, validated, review, documents) == 2
    text = json.dumps(_envelope(capsys)["diagnostics"])
    assert "non-empty candidate_hash" in text


def test_promote_rejects_ambiguous_review_hash(tmp_path, capsys):
    """Two review records with the same hash approve nothing."""
    _init(tmp_path)
    documents = _documents(tmp_path)
    validated, _ = _write_envelope(tmp_path, [_candidate()], documents)
    review = _review(tmp_path, [_candidate(), _candidate()])
    assert _promote(tmp_path, validated, review, documents) == 2
    text = json.dumps(_envelope(capsys)["diagnostics"])
    assert "more than one review" in text


def test_promote_records_human_reason_for_needs_review(tmp_path):
    """NEEDS_REVIEW is never stored as ACCEPTED without the human's reason."""
    _init(tmp_path)
    documents = _documents(tmp_path)
    candidate = _candidate()
    validated, _ = _write_envelope(tmp_path, [candidate], documents, forge_state="NEEDS_REVIEW")
    review = _review(tmp_path, [candidate], reason="SYNTHETIC reason: chamber log checked")
    assert _promote(tmp_path, validated, review, documents) == 0
    record = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))[0]
    assert record["validation_state"] in ("NEEDS_REVIEW", "ACCEPTED")
    assert "SYNTHETIC reason: chamber log checked" in json.dumps(record)


def test_promote_refuses_unmapped_parameter(tmp_path):
    """A parameter absent from the explicit mapping must be refused."""
    _init(tmp_path)
    documents = _documents(tmp_path, "SYNTHETIC value was 1 measured")
    candidate = _candidate()
    candidate["parameter_name"] = "SYNTHETIC_unmapped"
    validated, _ = _write_envelope(tmp_path, [candidate], documents, allow_failed=True)
    review = _review(tmp_path, [candidate])
    assert _promote(tmp_path, validated, review, documents) == 2


def test_promote_refuses_uncheckable_table_quote(tmp_path, capsys):
    """A table row with no recoverable header must be refused, not guessed."""
    _init(tmp_path)
    quote = "ambient temperature 298.15 0.47 synthetic"
    documents = _documents(tmp_path, quote)
    candidate = _candidate(quote=quote)
    candidate["source"]["locator"] = "Table I"
    validated, _ = _write_envelope(tmp_path, [candidate], documents)
    review = _review(tmp_path, [candidate])
    assert _promote(tmp_path, validated, review, documents) == 2
    text = json.dumps(_envelope(capsys)["diagnostics"])
    assert "table quote cannot be checked" in text


def test_promoted_record_has_verified_pybamm_names(tmp_path):
    """Promoted records carry mapped, installed PyBaMM names."""
    _init(tmp_path)
    documents = _documents(tmp_path)
    validated, _ = _write_envelope(tmp_path, [_candidate()], documents)
    review = _review(tmp_path, [_candidate()])
    assert _promote(tmp_path, validated, review, documents) == 0
    record = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))[0]
    assert record["pybamm_names"] == ["Ambient temperature [K]"]
