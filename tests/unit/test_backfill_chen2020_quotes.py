"""Unit tests: deterministic Chen2020 quote backfill script (V2.2)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from pybamm_closed_loop.literature.availability import (
    ARTICLE_MISSING_REASON,
    article_source_text_available,
)
from pybamm_closed_loop.registry.seed import SPEC

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "backfill_chen2020_quotes", REPO_ROOT / "scripts/backfill_chen2020_quotes.py"
)
assert _SPEC and _SPEC.loader
MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MOD)

FLAGGED = MOD.EXPECTED_IDS


def test_scope_is_the_seventeen_flagged_records():
    assert len(FLAGGED) == 17
    assert len(set(FLAGGED)) == 17


def test_every_flagged_spec_carries_a_probe():
    for cid in FLAGGED:
        probe = (SPEC.get(cid, {}).get("paper") or {}).get("probe")
        assert probe, f"SPEC[{cid}] lost its backfill probe"


def test_script_makes_no_network_call():
    source = (REPO_ROOT / "scripts/backfill_chen2020_quotes.py").read_text()
    assert "urlopen" not in source
    assert "requests" not in source
    assert "httpx" not in source
    assert "urllib" not in source


def test_missing_text_refuses(tmp_path, capsys):
    rc = MOD.main(["--registry", str(tmp_path), "--text", str(tmp_path / "nope.txt")])
    assert rc == 1
    assert "No quote was invented" in capsys.readouterr().err


def test_text_hash_mismatch_refuses(tmp_path, capsys):
    text = tmp_path / "fulltext.txt"
    text.write_text("not the recorded extract")
    rc = MOD.main(["--registry", str(tmp_path), "--text", str(text)])
    assert rc == 2
    assert "sha256 mismatch" in capsys.readouterr().err


def test_backfill_fills_and_is_idempotent(tmp_path):
    if not article_source_text_available():
        pytest.skip(f"SKIP: {ARTICLE_MISSING_REASON}")
    registry = tmp_path / "registry"
    registry.mkdir()
    # simulate the pre-backfill state: the 17 flagged records carry no quote
    records = json.loads(
        (REPO_ROOT / "data/registry/registry.json").read_text()
    )
    for record in records:
        if record["canonical_id"] in FLAGGED:
            source = record["evidence"]["source"]
            source["quote"] = None
            source["char_start"] = None
            source["char_end"] = None
    (registry / "registry.json").write_text(
        json.dumps(records, indent=2, sort_keys=True)
    )
    argv = ["--registry", str(registry)]
    assert MOD.main(argv) == 0

    records = json.loads((registry / "registry.json").read_text())
    by_id = {r["canonical_id"]: r for r in records}
    for cid in FLAGGED:
        src = by_id[cid]["evidence"]["source"]
        assert src["quote"], cid
        assert src["char_start"] is not None
        assert src["char_end"] is not None

    revisions = (registry / "revisions.jsonl").read_text().splitlines()
    assert len(revisions) == 17
    for line in revisions:
        entry = json.loads(line)
        assert entry["actor"] == MOD.ACTOR
        assert "previous" in entry

    # second run: nothing to fill, nothing overwritten
    assert MOD.main(argv) == 0
    revisions = (registry / "revisions.jsonl").read_text().splitlines()
    assert len(revisions) == 17
    records = json.loads((registry / "registry.json").read_text())
    by_id = {r["canonical_id"]: r for r in records}
    for cid in FLAGGED:
        assert by_id[cid]["evidence"]["source"]["quote"]
