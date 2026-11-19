"""Optional dense retrieval helpers: cache, RRF and missing-extra behaviour."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from pybamm_closed_loop.literature.dense import (
    MODEL_ID,
    MODEL_LICENCE,
    MODEL_WEIGHT_BYTES,
    DenseEncoder,
    DenseUnavailable,
    cache_path,
    dense_search,
    document_sha256,
    hybrid_ids,
    load_cached,
    reciprocal_rank_fusion,
    save_cached,
)


def test_core_import_does_not_load_sentence_transformers():
    assert "sentence_transformers" not in sys.modules


def test_dense_unavailable_message_names_model_and_licence():
    encoder = DenseEncoder()
    with pytest.raises(DenseUnavailable) as exc:
        encoder.encode(["example"])
    message = str(exc)
    assert MODEL_ID in message
    assert str(MODEL_WEIGHT_BYTES) in message
    assert MODEL_LICENCE in message


def test_cache_is_keyed_by_model_and_sha(tmp_path):
    sha = "a" * 64
    path = cache_path(tmp_path, MODEL_ID, "docA", sha)
    assert MODEL_ID.replace("/", "_") in str(path)
    assert sha[:16] in path.name
    save_cached(tmp_path, MODEL_ID, "docA", sha, {"docA#0": [0.1, 0.2]})
    assert load_cached(tmp_path, MODEL_ID, "docA", sha) == {"docA#0": [0.1, 0.2]}
    assert load_cached(tmp_path, MODEL_ID, "docA", "b" * 64) is None
    assert load_cached(tmp_path, "other/model", "docA", sha) is None


def test_document_sha_comes_from_manifest(tmp_path):
    (tmp_path / "documents.json").write_text(
        json.dumps([{"document_id": "docA", "content_sha256": "c" * 64}])
    )
    assert document_sha256(tmp_path, "docA") == "c" * 64
    assert document_sha256(tmp_path, "missing") is None


def test_dense_search_ranks_by_cosine():
    vectors = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
    hits = dense_search(np.array([1.0, 0.0]), ["a", "b"], vectors, k=2)
    assert [sid for sid, _ in hits] == ["a", "b"]


def test_rrf_and_hybrid_are_stable():
    assert reciprocal_rank_fusion([["a", "b"], ["b", "a"]])[:2] == ["a", "b"]
    assert hybrid_ids(["a", "b"], ["c", "a"])[0] == "a"


def test_fake_encoder_is_used_lazily(monkeypatch):
    calls: list[list[str]] = []

    class FakeModel:
        def encode(self, texts, **_kwargs):
            calls.append(list(texts))
            return np.ones((len(texts), 3))

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=lambda _model_id: FakeModel()),
    )
    encoder = DenseEncoder()
    assert calls == []
    result = encoder.encode(["x", "y"])
    assert result.shape == (2, 3)
    assert calls == [["x", "y"]]


def test_real_embedding_smoke():
    sentence_transformers = pytest.importorskip("sentence_transformers")
    assert hasattr(sentence_transformers, "SentenceTransformer")
