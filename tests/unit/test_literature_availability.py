"""Local-availability skips for non-redistributable supplementary text."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]

from pybamm_closed_loop.literature.availability import (
    SUPPLEMENT_DOCUMENT_ID,
    SUPPLEMENT_MISSING_REASON,
    supplement_text_available,
    supplement_text_path,
    without_supplement_items,
)


def test_path_and_availability(tmp_path):
    path = supplement_text_path(tmp_path)
    assert path == tmp_path / "raw" / f"{SUPPLEMENT_DOCUMENT_ID}.txt"
    assert supplement_text_available(tmp_path) is False
    path.parent.mkdir(parents=True)
    path.write_text("local only")
    assert supplement_text_available(tmp_path) is True


def test_items_are_filtered_with_explicit_reason(tmp_path):
    items = [
        SimpleNamespace(item_id="keep", document_id="other"),
        SimpleNamespace(item_id="drop", document_id=SUPPLEMENT_DOCUMENT_ID),
    ]
    logged: list[str] = []
    kept = without_supplement_items(items, tmp_path, log=logged.append)
    assert [i.item_id for i in kept] == ["keep"]
    assert len(logged) == 1
    assert "SKIP 1 supplement item(s)" in logged[0]
    assert SUPPLEMENT_MISSING_REASON in logged[0]


def test_dict_items_and_present_text(tmp_path):
    rows = [
        {"item_id": "drop", "document_id": SUPPLEMENT_DOCUMENT_ID},
        {"item_id": "keep", "document_id": "other"},
    ]
    kept = without_supplement_items(
        rows, tmp_path, log=lambda _message: None, document_id_of=lambda r: r["document_id"]
    )
    assert [r["item_id"] for r in kept] == ["keep"]
    supplement_text_path(tmp_path).parent.mkdir(parents=True)
    supplement_text_path(tmp_path).write_text("locally ingested")
    assert without_supplement_items(
        rows, tmp_path, document_id_of=lambda r: r["document_id"]
    ) == rows


def test_p4_ensure_documents_skips_absent_supplement_pdf(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "p4_runner", REPO_ROOT / "benchmarks/p4/run_llm_evaluation.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    from pybamm_closed_loop.literature.ingest import DocumentStore

    messages: list[str] = []
    monkeypatch.setattr(
        module, "print", lambda msg, **_kwargs: messages.append(msg), raising=False
    )
    monkeypatch.setattr(
        module,
        "DOCS",
        [{"document_id": SUPPLEMENT_DOCUMENT_ID, "pdf": tmp_path / "absent.pdf"}],
    )
    store = DocumentStore(tmp_path / "store")
    module.ensure_documents(store)
    assert store.documents() == []
    assert any("SKIP chen2020_supplement_s1" in m for m in messages)
