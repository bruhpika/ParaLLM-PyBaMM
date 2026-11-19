"""Corpus-size scaling of gold-passage recall (no new documents, no LLM).

Synthetic distractor documents are built by deterministically re-using text
segments from the already-local, licence-evidenced main store. No new
copyrighted full text is added to the repository, and no document is fetched.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "benchmarks/v2"))

import evaluate_retrieval as protocol  # noqa: E402
from matplotlib import pyplot as plt  # noqa: E402
from pybamm_closed_loop.eval.benchmark_v4 import load_items  # noqa: E402
from pybamm_closed_loop.literature.ingest import DocumentStore, Segment  # noqa: E402
from pybamm_closed_loop.literature.index import BM25Index  # noqa: E402

OUT_DIR = protocol.OUT_DIR
JSON_OUT = OUT_DIR / "corpus_scaling.json"
MD_OUT = OUT_DIR / "corpus_scaling.md"
FIG_OUT = OUT_DIR / "corpus_scaling.png"
SEED = 20261119
SEGMENTS_PER_DISTRACTOR = 20
# 4 docs (v4 small), 8 docs (current combined), then +2/+12/+32 synthetic docs
# to reach 10, 20 and 40 documents. N above 10 = 10, 30.
DISTRACTOR_DOCS = {10: 2, 20: 12, 40: 32}


def synthetic_distractors(
    pool: Sequence[Segment],
    n_docs: int,
    *,
    segments_per_doc: int = SEGMENTS_PER_DISTRACTOR,
    seed: int = SEED,
) -> list[Segment]:
    """Build deterministic distractor docs from permitted non-gold segments."""
    if not pool:
        raise ValueError("empty distractor pool")
    rng = np.random.default_rng(seed)
    out: list[Segment] = []
    for doc_index in range(n_docs):
        doc_id = f"synthetic_distractor_{doc_index:03d}"
        picks = rng.choice(len(pool), size=min(segments_per_doc, len(pool)), replace=False)
        for j, source_index in enumerate(picks):
            src = pool[int(source_index)]
            out.append(
                Segment(
                    segment_id=f"{doc_id}#seg{j:05d}",
                    document_id=doc_id,
                    char_start=src.char_start,
                    char_end=src.char_end,
                    page=src.page,
                    heading=src.heading,
                    text=src.text,
                )
            )
    return out


def _render(payload: dict[str, Any]) -> str:
    lines = [
        "# Recall vs corpus size (synthetic distractors)",
        "",
        f"Seed {payload['seed']}; BM25 config {payload['bm25_config']} "
        f"(`configs/retrieval/lexical_config.json`).",
        "Distractor documents re-use existing licence-evidenced text; no new",
        "documents were fetched and no gold passage was duplicated.",
        "",
        "| documents | segments | split | recall@1 | recall@3 | recall@5 | recall@10 |",
        "|---:|---:|---|---:|---:|---:|---:|",
    ]
    for row in payload["rows"]:
        m = row["metrics"]["metrics"]
        values = [m[f"recall@{k}"]["mean"] for k in (1, 3, 5, 10)]
        lines.append(
            f"| {row['n_documents']} | {row['n_segments']} | {row['split']} | "
            + " | ".join(f"{v:.3f}" for v in values)
            + " |"
        )
    lines += [
        "",
        "The v4 corpus is small and private; these numbers are not comparable",
        "with v3. Recall on synthetic distractors is a stress test, not a claim",
        "about any real four-/ten-paper corpus.",
        "",
    ]
    return "\n".join(lines)


def _plot(payload: dict[str, Any]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, split in zip(axes, ("dev", "test")):
        rows = [r for r in payload["rows"] if r["split"] == split]
        xs = [r["n_documents"] for r in rows]
        for k, marker in zip((1, 3, 5, 10), ("o", "s", "^", "D")):
            ys = [r["metrics"]["metrics"][f"recall@{k}"]["mean"] for r in rows]
            ax.plot(xs, ys, marker=marker, label=f"recall@{k}")
        ax.set_xlabel("documents (synthetic distractors included)")
        ax.set_ylabel("recall" if split == "dev" else "")
        ax.set_title(split)
        ax.set_ylim(-0.05, 1.05)
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_OUT, dpi=150)
    plt.close(fig)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=("dev", "test", "both"), default="both")
    args = ap.parse_args(argv)

    split = protocol.load_split()
    config = json.loads(
        (REPO_ROOT / "configs/retrieval/lexical_config.json").read_text()
    )["config"]
    items_all = load_items(protocol.V4_ITEMS)
    by_id = {str(it.item_id): it for it in items_all}
    gold = protocol.load_gold(protocol.V4_FULL_AUDIT)
    v4_store = DocumentStore(protocol.V4_STORE)
    main_store = DocumentStore(protocol.V3_STORE)
    base_segments = list(v4_store.segments())
    pool = list(main_store.segments())  # CC BY papers + PyBaMM docs only

    corpora: dict[int, list[Segment]] = {
        4: base_segments,
        8: base_segments + pool,
    }
    for target, extra in DISTRACTOR_DOCS.items():
        corpora[target] = base_segments + pool + synthetic_distractors(pool, extra)

    rows: list[dict[str, Any]] = []
    for n_docs, segments in sorted(corpora.items()):
        index = BM25Index(
            segments, k1=float(config.get("k1", 1.5)), b=float(config.get("b", 0.75))
        )
        for stage in ("dev", "test"):
            if args.stage != "both" and args.stage != stage:
                continue
            subset = [by_id[i] for i in split["benchmarks"]["v4"][stage]]
            stats, _detail = protocol.evaluate(subset, index, gold)
            rows.append(
                {
                    "n_documents": n_docs,
                    "n_segments": len(segments),
                    "split": stage,
                    "metrics": stats,
                }
            )
            protocol.log_config(
                {
                    "generated": datetime.now(timezone.utc).isoformat(),
                    "configuration": f"corpus_scaling/{n_docs}_docs/{stage}",
                    "status": "ok",
                    "bm25": config,
                    "n_segments": len(segments),
                    "n_items": stats["n_items"],
                }
            )

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "bm25_config": config,
        "split_source": "configs/retrieval/dev_test_split.json",
        "label_source": "data/private_v4/results/retrieval_recall_full_audit.json",
        "distractor_policy": (
            "synthetic documents built from existing licence-evidenced main-store "
            "segments; no new documents fetched, no gold passage duplicated"
        ),
        "rows": rows,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    MD_OUT.write_text(_render(payload))
    _plot(payload)
    print(f"wrote {JSON_OUT}, {MD_OUT}, {FIG_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
