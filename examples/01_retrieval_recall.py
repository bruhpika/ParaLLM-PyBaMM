#!/usr/bin/env python
"""Example 1: gold-passage recall for the real BM25 retrieval arm (v3).

Builds a BM25 index over the committed literature store and reports recall@k
for the public v3 benchmark. No network access and no model call; the fixture
probe is used only as a post-retrieval evaluation label.

Usage:
    .venv/bin/python examples/01_retrieval_recall.py \
        --out-dir examples/output/01_retrieval_recall
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.eval.benchmark_p5 import load_items_v3  # noqa: E402
from pybamm_closed_loop.eval.retrieval_arms import evaluate_recall  # noqa: E402
from pybamm_closed_loop.literature.availability import (  # noqa: E402
    without_article_items,
    without_supplement_items,
)
from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402

V3_ITEMS = REPO_ROOT / "data/eval/extraction_benchmark_v3.jsonl"
V3_STORE = REPO_ROOT / "data/literature_store"
DEFAULT_OUT = REPO_ROOT / "examples/output/01_retrieval_recall"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    items = load_items_v3(V3_ITEMS)
    items = without_supplement_items(items, V3_STORE, log=print)
    items = without_article_items(items, V3_STORE, log=print)
    store = DocumentStore(V3_STORE)
    summary, rows = evaluate_recall(items, store)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "rows": rows}
    (args.out_dir / "retrieval_recall.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    for k in summary["k_values"]:
        value = summary["recall"][f"recall@{k}"]
        print(f"recall@{k}: {value:.3f}")
    print(f"wrote {args.out_dir / 'retrieval_recall.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
