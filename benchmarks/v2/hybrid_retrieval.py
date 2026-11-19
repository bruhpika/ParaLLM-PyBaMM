"""Optional dense/hybrid retrieval evaluation (no model download by default).

Dense weights are loaded ONLY if a cache already exists. Building that cache
requires the owner-approved ``retrieval-dense`` extra and model download:
  sentence-transformers/all-MiniLM-L6-v2, 90,868,376 bytes, apache-2.0.
This script never downloads anything itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "benchmarks/v2"))

import evaluate_retrieval as protocol  # noqa: E402
from pybamm_closed_loop.eval.benchmark_p5 import load_items_v3  # noqa: E402
from pybamm_closed_loop.eval.benchmark_v4 import load_items  # noqa: E402
from pybamm_closed_loop.eval.retrieval_arms import query_for_item  # noqa: E402
from pybamm_closed_loop.literature.dense import (  # noqa: E402
    MODEL_ID,
    MODEL_LICENCE,
    MODEL_WEIGHT_BYTES,
    DenseEncoder,
    DenseUnavailable,
    dense_search,
    document_sha256,
    hybrid_ids,
    load_cached,
    save_cached,
)
from pybamm_closed_loop.literature.index import BM25Index  # noqa: E402
from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402

OUT_DIR = protocol.OUT_DIR
HYBRID_JSON = OUT_DIR / "hybrid.json"
HYBRID_MD = OUT_DIR / "hybrid.md"
DEFAULT_CACHE = REPO_ROOT / ".cache"


def cache_vectors(index: BM25Index, store_root: Path, cache_dir: Path, model: DenseEncoder):
    """Load all per-document caches, building any missing ones explicitly."""
    vectors: dict[str, list[float]] = {}
    by_doc: dict[str, list[Any]] = {}
    for segment in index.segments:
        by_doc.setdefault(segment.document_id, []).append(segment)
    for doc_id, segments in by_doc.items():
        sha = document_sha256(store_root, doc_id)
        if not sha:
            raise SystemExit(f"no recorded sha256 for {doc_id}")
        cached = load_cached(cache_dir, model.model_id, doc_id, sha)
        if cached is None:
            raise DenseUnavailable(
                f"missing dense cache for {doc_id} (model {model.model_id}); "
                f"build it after approving the {MODEL_WEIGHT_BYTES}-byte "
                f"{MODEL_LICENCE} model download"
            )
        for sid, vector in cached.items():
            vectors[sid] = vector
    return vectors


def build_cache(index: BM25Index, store_root: Path, cache_dir: Path, model: DenseEncoder):
    by_doc: dict[str, list[Any]] = {}
    for segment in index.segments:
        by_doc.setdefault(segment.document_id, []).append(segment)
    for doc_id, segments in by_doc.items():
        sha = document_sha256(store_root, doc_id)
        if not sha:
            raise SystemExit(f"no recorded sha256 for {doc_id}")
        if load_cached(cache_dir, model.model_id, doc_id, sha) is not None:
            continue
        matrix = model.encode([s.text for s in segments])
        save_cached(
            cache_dir,
            model.model_id,
            doc_id,
            sha,
            {s.segment_id: matrix[i] for i, s in enumerate(segments)},
        )
        print(f"cached {doc_id}: {len(segments)} segments", flush=True)


def make_search(
    mode: str,
    vectors: dict[str, list[float]],
    model: DenseEncoder,
    query_vectors: dict[str, np.ndarray],
) -> Callable:
    def search(index: BM25Index, query: str, k: int, item: Any):
        bm25_ids = [s.segment_id for s, _ in index.search(query, k=k)]
        if mode == "bm25":
            return index.search(query, k=k)
        qv = query_vectors[str(item.item_id)]
        dense = dense_search(qv, [s.segment_id for s in index.segments], vectors, k=k)
        dense_ids = [sid for sid, _ in dense]
        if mode == "dense":
            return [
                (next(s for s in index.segments if s.segment_id == sid), score)
                for sid, score in dense
            ]
        fused = hybrid_ids(bm25_ids, dense_ids)[:k]
        by_id = {s.segment_id: s for s in index.segments}
        return [(by_id[sid], float(i)) for i, sid in enumerate(fused)]

    return search


def _render(payload: dict[str, Any]) -> str:
    lines = [
        "# Dense / hybrid retrieval (optional extra)",
        "",
        f"Model: `{payload['model_id']}` ({payload['model_weight_bytes']} bytes, "
        f"licence {payload['model_licence']}).",
        "No model weights are bundled; embedding cache is gitignored.",
        "",
    ]
    for mode, by_set in payload["modes"].items():
        lines += [f"## {mode}", ""]
        for key, splits in by_set.items():
            for split_name in ("dev", "test"):
                m = splits[split_name]["metrics"]
                recalls = "/".join(f"{m[f'recall@{k}']['mean']:.3f}" for k in (1, 3, 5, 10))
                lines.append(f"- {key} {split_name}: recall@1/3/5/10 {recalls}")
        lines.append("")
    lines += [
        "The v4 corpus is small and private; v3 and v4 are not comparable.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build-cache", action="store_true")
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    ap.add_argument("--model", default=MODEL_ID)
    args = ap.parse_args(argv)

    cache_dir = Path(args.cache_dir)
    model = DenseEncoder(args.model)
    split = protocol.load_split()
    v3_by_id = {str(it.item_id): it for it in load_items_v3(protocol.V3_ITEMS)}
    v4_by_id = {str(it.item_id): it for it in load_items(protocol.V4_ITEMS)}
    main_store = DocumentStore(protocol.V3_STORE)
    v4_store = DocumentStore(protocol.V4_STORE)
    corpora = {
        "v3/full": (
            v3_by_id,
            protocol.load_gold(protocol.V3_AUDIT),
            BM25Index(main_store.segments()),
            protocol.V3_STORE,
        ),
        "v4/small": (
            v4_by_id,
            protocol.load_gold(protocol.V4_SMALL_AUDIT),
            BM25Index(v4_store.segments()),
            protocol.V4_STORE,
        ),
        "v4/full": (
            v4_by_id,
            protocol.load_gold(protocol.V4_FULL_AUDIT),
            BM25Index(v4_store.segments() + main_store.segments()),
            protocol.V4_STORE,
        ),
    }

    if args.build_cache:
        for _name, (_by_id, _gold, index, store_root) in corpora.items():
            build_cache(index, Path(store_root), cache_dir, model)
        return 0

    payload: dict[str, Any] = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "model_id": model.model_id,
        "model_weight_bytes": MODEL_WEIGHT_BYTES,
        "model_licence": MODEL_LICENCE,
        "seed": protocol.SEED,
        "modes": {},
    }
    for mode in ("bm25", "dense", "hybrid"):
        payload["modes"][mode] = {}
        for key, (by_id, gold, index, store_root) in corpora.items():
            vectors = cache_vectors(index, Path(store_root), cache_dir, model)
            bench = "v3" if key.startswith("v3") else "v4"
            items = [by_id[i] for i in split["benchmarks"][bench]["dev"]]
            all_items = items + [
                by_id[i] for i in split["benchmarks"][bench]["test"]
            ]
            query_vectors = {
                str(it.item_id): model.encode([query_for_item(it)])[0] for it in all_items
            }
            payload["modes"][mode][key] = {}
            for split_name, subset in (("dev", items), ("test", all_items[len(items) :])):
                stats, _rows = protocol.evaluate(
                    subset,
                    index,
                    gold,
                    search_fn=make_search(mode, vectors, model, query_vectors),
                )
                payload["modes"][mode][key][split_name] = stats
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    HYBRID_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    HYBRID_MD.write_text(_render(payload))
    print(f"wrote {HYBRID_JSON}, {HYBRID_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
