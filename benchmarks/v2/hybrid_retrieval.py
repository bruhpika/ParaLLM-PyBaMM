"""Optional dense/hybrid retrieval evaluation (no automatic model download).

Owner-approved model: sentence-transformers/all-MiniLM-L6-v2,
model.safetensors 90,868,376 bytes, apache-2.0, pinned commit
1110a243fdf4706b3f48f1d95db1a4f5529b4d41 (also in the cache key).

Usage: --preflight (segment lengths), --build-cache (explicit download),
then the comparison (dev then test once). This script does not download
anything unless --build-cache is given.
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
    MODEL_REVISION,
    MODEL_WEIGHT_BYTES,
    DenseEncoder,
    DenseUnavailable,
    dense_search,
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


def cache_vectors(
    index: BM25Index, sha_by_doc: dict[str, str], cache_dir: Path, model: DenseEncoder
):
    """Load all per-document caches, building any missing ones explicitly."""
    vectors: dict[str, list[float]] = {}
    by_doc: dict[str, list[Any]] = {}
    for segment in index.segments:
        by_doc.setdefault(segment.document_id, []).append(segment)
    for doc_id, segments in by_doc.items():
        sha = sha_by_doc.get(doc_id)
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


def build_cache(
    index: BM25Index, sha_by_doc: dict[str, str], cache_dir: Path, model: DenseEncoder
):
    by_doc: dict[str, list[Any]] = {}
    for segment in index.segments:
        by_doc.setdefault(segment.document_id, []).append(segment)
    for doc_id, segments in by_doc.items():
        sha = sha_by_doc.get(doc_id)
        if not sha:
            raise SystemExit(f"no recorded sha256 for {doc_id}")
        if load_cached(cache_dir, model.model_id, doc_id, sha) is not None:
            continue
        matrix, report = model.encode([s.text for s in segments], with_report=True)
        print(
            f"  {doc_id}: {report['n_chunked']}/{report['n_texts']} segments chunked "
            f"(max {report['max_seq_length']} tokens, budget {report['token_budget']})",
            flush=True,
        )
        save_cached(
            cache_dir,
            model.model_id,
            doc_id,
            sha,
            {s.segment_id: matrix[i] for i, s in enumerate(segments)},
        )
        print(f"cached {doc_id}: {len(segments)} segments", flush=True)


def preflight(
    corpora: dict[str, tuple], cache_dir: Path, model: DenseEncoder
) -> dict[str, Any]:
    """Report over-length segments before any comparison; never truncate."""
    encoder = model
    report: dict[str, Any] = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "model_id": model.model_id,
        "revision": MODEL_REVISION,
        "handling": (
            "over-length segments are split into token windows and their "
            "embeddings pooled; no silent truncation"
        ),
        "corpora": {},
    }
    _matrix, sample = encoder.encode(["length probe"], with_report=True)
    report["max_seq_length"] = sample["max_seq_length"]
    report["token_budget"] = sample["token_budget"]
    for name, (_by_id, _gold, index, _root) in corpora.items():
        texts = [s.text for s in index.segments]
        _vectors, stats = encoder.encode(texts, with_report=True)
        report["corpora"][name] = stats
        print(
            f"{name}: {stats['n_chunked']}/{stats['n_texts']} "
            f"({stats['fraction_chunked']:.3f}) segments exceed "
            f"{stats['token_budget']} tokens; longest {stats['longest_token_count']}",
            flush=True,
        )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "segment_length_preflight.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    lines = [
        "# Segment-length preflight (no silent truncation)",
        "",
        f"Model `{report['model_id']}` revision `{MODEL_REVISION}`; "
        f"max sequence length {report['max_seq_length']} "
        f"(budget {report['token_budget']} after CLS/SEP).",
        f"Handling: {report['handling']}.",
        "",
        "| corpus | segments | over-length | fraction | longest tokens |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, stats in report["corpora"].items():
        lines.append(
            f"| {name} | {stats['n_texts']} | {stats['n_chunked']} | "
            f"{stats['fraction_chunked']:.3f} | {stats['longest_token_count']} |"
        )
    lines.append("")
    (OUT_DIR / "segment_length_preflight.md").write_text("\n".join(lines))
    return report


def make_search(
    mode: str,
    vectors: dict[str, list[float]],
    query_vectors: dict[str, np.ndarray],
    tuned_index: BM25Index,
) -> Callable:
    def search(index: BM25Index, query: str, k: int, item: Any):
        bm25_hits = tuned_index.search(query, k=k)
        bm25_ids = [s.segment_id for s, _ in bm25_hits]
        if mode == "bm25":
            return bm25_hits
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
        f"licence {payload['model_licence']}), revision "
        f"`{payload['model_revision']}`.",
        f"BM25 leg uses the tuned config {payload['tuned_bm25_config']} from "
        f"`{payload['tuned_bm25_source']}`.",
        "No model weights are bundled; embedding cache is gitignored.",
        "",
    ]
    for mode, by_set in payload["modes"].items():
        lines += [f"## {mode}", ""]
        for key, splits in by_set.items():
            for split_name in ("dev", "test"):
                if split_name not in splits:
                    continue
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
    ap.add_argument(
        "--stage", choices=("dev", "test", "both"), default="both",
        help="evaluate dev only, test only, or both (default both)",
    )
    ap.add_argument("--preflight", action="store_true")
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
    sha_by_doc = {
        str(d.document_id): str(d.content_sha256)
        for d in [*main_store.documents(), *v4_store.documents()]
        if d.content_sha256
    }
    corpora = {
        "v3/full": (
            v3_by_id,
            protocol.load_gold(protocol.V3_AUDIT),
            BM25Index(main_store.segments()),
            sha_by_doc,
        ),
        "v4/small": (
            v4_by_id,
            protocol.load_gold(protocol.V4_SMALL_AUDIT),
            BM25Index(v4_store.segments()),
            sha_by_doc,
        ),
        "v4/full": (
            v4_by_id,
            protocol.load_gold(protocol.V4_FULL_AUDIT),
            BM25Index(v4_store.segments() + main_store.segments()),
            sha_by_doc,
        ),
    }

    if args.preflight:
        preflight(corpora, cache_dir, model)
        return 0

    if args.build_cache:
        for _name, (_by_id, _gold, index, sha_map) in corpora.items():
            build_cache(index, sha_map, cache_dir, model)
        return 0

    chosen = json.loads((REPO_ROOT / "configs/retrieval/lexical_config.json").read_text())
    tuned = chosen["config"]
    payload: dict[str, Any] = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "model_id": model.model_id,
        "model_revision": MODEL_REVISION,
        "model_weight_bytes": MODEL_WEIGHT_BYTES,
        "model_licence": MODEL_LICENCE,
        "seed": protocol.SEED,
        "split_source": "configs/retrieval/dev_test_split.json",
        "bm25_baseline_source": "results/v2/retrieval_improvement/baseline.json",
        "tuned_bm25_config": tuned,
        "tuned_bm25_source": "configs/retrieval/lexical_config.json",
        "modes": {},
    }
    for mode in ("bm25", "dense", "hybrid"):
        payload["modes"][mode] = {}
        for key, (by_id, gold, index, sha_map) in corpora.items():
            vectors = cache_vectors(index, sha_map, cache_dir, model)
            tuned_index = BM25Index(
                index.segments,
                k1=float(tuned.get("k1", 1.5)),
                b=float(tuned.get("b", 0.75)),
            )
            bench = "v3" if key.startswith("v3") else "v4"
            items = [by_id[i] for i in split["benchmarks"][bench]["dev"]]
            all_items = items + [
                by_id[i] for i in split["benchmarks"][bench]["test"]
            ]
            query_vectors = {
                str(it.item_id): model.encode([query_for_item(it)])[0] for it in all_items
            }
            payload["modes"][mode][key] = {}
            stages = (("dev", items), ("test", all_items[len(items) :]))
            if args.stage != "both":
                stages = tuple(s for s in stages if s[0] == args.stage)
            for split_name, subset in stages:
                stats, _rows = protocol.evaluate(
                    subset,
                    index,
                    gold,
                    search_fn=make_search(mode, vectors, query_vectors, tuned_index),
                )
                payload["modes"][mode][key][split_name] = stats
                protocol.log_config(
                    {
                        "generated": datetime.now(timezone.utc).isoformat(),
                        "configuration": f"hybrid_task3/{mode}/{key}/{split_name}",
                        "status": "ok",
                        "model_id": model.model_id,
                        "model_revision": MODEL_REVISION,
                        "tuned_bm25": tuned,
                        "n_items": stats["n_items"],
                    }
                )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / ("hybrid_dev.json" if args.stage == "dev" else "hybrid.json")
    md_path = OUT_DIR / ("hybrid_dev.md" if args.stage == "dev" else "hybrid.md")
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    md_path.write_text(_render(payload))
    print(f"wrote {json_path}, {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
