"""Fetch-free, hash-verified local ingest of the Chen2020 article PDF."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "fetch_chen2020", REPO_ROOT / "scripts/fetch_chen2020.py"
)
assert _SPEC and _SPEC.loader
MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MOD)

TODO_TEXT = "Chen2020 article PDF sha256: TODO (owner to fill)"
GOOD_HASH = "a" * 64
BAD_HASH = "b" * 64


def _provenance(tmp_path: Path, line: str) -> Path:
    path = tmp_path / "DATA_PROVENANCE.md"
    path.write_text(line + "\n")
    return path


class _FakeStore:
    instances: list["_FakeStore"] = []

    def __init__(self, root: Path):
        self.root = root
        self.raw_dir = root / "raw"
        self.segments_dir = root / "segments"
        self.calls: list[tuple] = []
        _FakeStore.instances.append(self)

    def ingest_pdf(self, *args, **kwargs):
        self.calls.append((args, kwargs))

        class _Rec:
            n_segments = 108

        return _Rec()


def test_expected_hash_parsing(tmp_path):
    assert MOD.expected_pdf_sha256(TODO_TEXT) is None
    path = _provenance(tmp_path, f"Chen2020 article PDF sha256: {GOOD_HASH}")
    assert MOD.expected_pdf_sha256(path.read_text()) == GOOD_HASH


def test_owner_todo_refuses_ingest(tmp_path, monkeypatch, capsys):
    _FakeStore.instances = []
    monkeypatch.setattr(MOD, "DocumentStore", _FakeStore)
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"pdf")
    prov = _provenance(tmp_path, TODO_TEXT)
    rc = MOD.main(
        [
            "--pdf",
            str(pdf),
            "--provenance",
            str(prov),
            "--store",
            str(tmp_path / "store"),
        ]
    )
    assert rc == 1
    assert "owner-to-fill" in capsys.readouterr().err
    assert _FakeStore.instances == []


def test_hash_mismatch_refuses_ingest(tmp_path, monkeypatch, capsys):
    _FakeStore.instances = []
    monkeypatch.setattr(MOD, "DocumentStore", _FakeStore)
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"not the recorded pdf")
    prov = _provenance(tmp_path, f"Chen2020 article PDF sha256: {GOOD_HASH}")
    rc = MOD.main(
        [
            "--pdf",
            str(pdf),
            "--provenance",
            str(prov),
            "--store",
            str(tmp_path / "store"),
        ]
    )
    assert rc == 2
    assert "sha256 mismatch" in capsys.readouterr().err
    assert _FakeStore.instances == []


def test_verified_hash_ingests_locally(tmp_path, monkeypatch):
    _FakeStore.instances = []
    monkeypatch.setattr(MOD, "DocumentStore", _FakeStore)
    pdf = tmp_path / "paper.pdf"
    content = b"%PDF-1.4 local copy"
    pdf.write_bytes(content)
    import hashlib

    prov = _provenance(
        tmp_path, f"Chen2020 article PDF sha256: {hashlib.sha256(content).hexdigest()}"
    )
    rc = MOD.main(
        [
            "--pdf",
            str(pdf),
            "--provenance",
            str(prov),
            "--store",
            str(tmp_path / "store"),
            "--retrieved",
            "2026-11-19",
        ]
    )
    assert rc == 0
    assert len(_FakeStore.instances) == 1
    args, kwargs = _FakeStore.instances[0].calls[0]
    assert args[0] == "chen2020_jes_167_080534"
    assert kwargs["kind"] == "paper"
    assert kwargs["retrieved"] == "2026-11-19"


def test_script_makes_no_network_call():
    source = (REPO_ROOT / "scripts/fetch_chen2020.py").read_text()
    assert "urlopen" not in source
    assert "requests" not in source
    assert "httpx" not in source
    assert "urllib" not in source
