"""Report gold-passage recall@k for the real-retrieval arm (no model calls).

``evaluate_recall`` uses the probe only as an evaluation label after BM25 has
run. The retrieval query itself is built from v3 retrieval facets or the v4
parameter name/unit, never from the probe, gold passage, target document or
gold conditions.

Usage:
    .venv/bin/python benchmarks/v2/report_retrieval_recall.py --benchmark v3
    .venv/bin/python benchmarks/v2/report_retrieval_recall.py --benchmark v4
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.eval.benchmark_p5 import load_items_v3  # noqa: E402
from pybamm_closed_loop.eval.benchmark_v4 import load_items  # noqa: E402
from pybamm_closed_loop.eval.retrieval_arms import (  # noqa: E402
    DEFAULT_RETRIEVAL_K,
    RECALL_KS,
    REAL_RETRIEVAL_LABEL,
    evaluate_recall,
)
from pybamm_closed_loop.literature.index import BM25Index  # noqa: E402
from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402

V3_ITEMS = REPO_ROOT / "data/eval/extraction_benchmark_v3.jsonl"
V3_STORE = REPO_ROOT / "data/literature_store"
V3_OUT = REPO_ROOT / "results/p5/benchmark_v3"

V4_ITEMS = REPO_ROOT / "data/private_v4/fixture/benchmark_v4.jsonl"
V4_STORE = REPO_ROOT / "data/private_v4/store"
V4_OUT = REPO_ROOT / "results/v2/v4"
V4_PRIVATE_AUDIT = REPO_ROOT / "data/private_v4/results/retrieval_recall_audit.json"


def _write_report(summary: dict, out_dir: Path, benchmark: str, query_rule: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "benchmark": benchmark,
        "arm": REAL_RETRIEVAL_LABEL,
        "query_rule": query_rule,
        "index": "BM25 over the complete document store; no document filter",
        "gold_label": "segment(s) containing the fixture probe, applied after retrieval",
        **summary,
    }
    (out_dir / "retrieval_recall.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True)
    )
    lines = [
        f"# {benchmark} — real-retrieval gold-passage recall",
        "",
        f"arm: {REAL_RETRIEVAL_LABEL}",
        "",
        f"query rule: {query_rule}",
        "",
        "BM25 searches the complete document store. The probe is used only as the "
        "post-retrieval evaluation label, never in the query or evidence selection.",
        "",
        f"items: {summary['n_items']}; evidence shown to extractor: top "
        f"{summary['evidence_k']} segments",
        "",
        "| k | recall |",
        "|---:|---:|",
    ]
    for k in summary["k_values"]:
        value = summary["recall"][f"recall@{k}"]
        lines.append(f"| {k} | {value:.3f} |")
    lines.append("")
    (out_dir / "retrieval_recall.md").write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", choices=["v3", "v4"], required=True)
    args = ap.parse_args()

    if args.benchmark == "v3":
        items = load_items_v3(V3_ITEMS)
        store = DocumentStore(V3_STORE)
        out_dir = V3_OUT
        query_rule = "v3 RetrievalFacets (parameter names, materials, cell, conditions, techniques)"
        audit_path = out_dir / "retrieval_recall_audit.json"
    else:
        items = load_items(V4_ITEMS)
        store = DocumentStore(V4_STORE)
        out_dir = V4_OUT
        query_rule = "v4 parameter name and unit only"
        audit_path = V4_PRIVATE_AUDIT

    summary, rows = evaluate_recall(
        items,
        store,
        index=BM25Index(store.segments()),
        k_values=RECALL_KS,
        evidence_k=DEFAULT_RETRIEVAL_K,
    )
    _write_report(summary, out_dir, args.benchmark, query_rule)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(
            {
                "benchmark": args.benchmark,
                "generated": datetime.now(timezone.utc).isoformat(),
                "per_item": rows,
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(json.dumps(summary["recall"], indent=2, sort_keys=True))
    print(f"wrote {out_dir / 'retrieval_recall.md'} and {audit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
