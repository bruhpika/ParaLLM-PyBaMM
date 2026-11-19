"""Optional dense retrieval helpers (no weights bundled, no download here).

The core install stays light: importing this module never imports
``sentence_transformers``. A model is loaded only inside ``DenseEncoder`` and
only when the caller has explicitly installed the ``retrieval-dense`` extra.
Embeddings are cached on disk under a path keyed by model id and document
sha256, so reruns are offline and deterministic once the cache exists.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_WEIGHT_BYTES = 90_868_376  # model.safetensors, HF API 2026-11-19
MODEL_LICENCE = "apache-2.0"  # HF cardData licence / API tag
CACHE_SUBDIR = "dense_retrieval"


class DenseUnavailable(RuntimeError):
    """Raised when dense retrieval is requested without the optional extra."""


def safe_model_id(model_id: str) -> str:
    """Filesystem-safe model id."""
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in model_id)


def cache_path(
    cache_dir: str | Path, model_id: str, document_id: str, content_sha256: str
) -> Path:
    return (
        Path(cache_dir)
        / CACHE_SUBDIR
        / safe_model_id(model_id)
        / f"{document_id}_{content_sha256[:16]}.json"
    )


def load_cached(
    cache_dir: str | Path, model_id: str, document_id: str, content_sha256: str
) -> dict[str, list[float]] | None:
    path = cache_path(cache_dir, model_id, document_id, content_sha256)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text())
    if payload.get("model_id") != model_id or payload.get("sha256") != content_sha256:
        return None
    return {str(k): [float(v) for v in vec] for k, vec in payload["vectors"].items()}


def save_cached(
    cache_dir: str | Path,
    model_id: str,
    document_id: str,
    content_sha256: str,
    vectors: Mapping[str, Sequence[float]],
) -> Path:
    path = cache_path(cache_dir, model_id, document_id, content_sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "model_id": model_id,
                "document_id": document_id,
                "sha256": content_sha256,
                "vectors": {str(k): list(map(float, v)) for k, v in vectors.items()},
            },
            sort_keys=True,
        )
    )
    return path


class DenseEncoder:
    """Lazy sentence-transformers wrapper; imports the extra only on use."""

    def __init__(self, model_id: str = MODEL_ID) -> None:
        self.model_id = model_id
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise DenseUnavailable(
                    "dense retrieval needs the optional extra: "
                    "pip install 'parallm-pybamm[retrieval-dense]' "
                    f"(model {self.model_id}, {MODEL_WEIGHT_BYTES} bytes, "
                    f"licence {MODEL_LICENCE})"
                ) from exc
            self._model = SentenceTransformer(self.model_id)
        return self._model

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        return np.asarray(
            self._load().encode(
                list(texts),
                batch_size=32,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ),
            dtype=float,
        )


def dense_search(
    query_vector: np.ndarray,
    segment_ids: Sequence[str],
    vectors: Mapping[str, Sequence[float]],
    *,
    k: int,
) -> list[tuple[str, float]]:
    """Cosine ranking over cached segment vectors (model-independent)."""
    available = [sid for sid in segment_ids if sid in vectors]
    if not available:
        return []
    matrix = np.asarray([vectors[sid] for sid in available], dtype=float)
    query = np.asarray(query_vector, dtype=float).reshape(-1)
    scores = matrix @ query / (
        np.linalg.norm(matrix, axis=1) * np.linalg.norm(query) + 1e-12
    )
    order = np.argsort(-scores)[:k]
    return [(available[i], float(scores[i])) for i in order]


def reciprocal_rank_fusion(
    rankings: Iterable[Sequence[str]], *, k: int = 60
) -> list[str]:
    """RRF over ranked id lists; stable and deterministic."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, 1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda sid: (-scores[sid], sid))


def hybrid_ids(
    bm25_ids: Sequence[str], dense_ids: Sequence[str], *, k: int = 60
) -> list[str]:
    return reciprocal_rank_fusion([list(bm25_ids), list(dense_ids)], k=k)


def document_sha256(root: str | Path, document_id: str) -> str | None:
    """Recorded sha256 for a document in a DocumentStore manifest."""
    path = Path(root) / "documents.json"
    if not path.is_file():
        return None
    for record in json.loads(path.read_text()):
        if record.get("document_id") == document_id:
            return str(record.get("content_sha256") or "") or None
    return None


def cache_key(parts: Sequence[str]) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()
