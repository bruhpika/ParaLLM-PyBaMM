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
V4_FULL_AUDIT = REPO_ROOT / "data/private_v4/results/retrieval_recall_full_audit.json"
MAIN_STORE = REPO_ROOT / "data/literature_store"


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


def _write_stress_report(
    small: dict, full: dict, out_dir: Path, query_rule: str, n_docs: tuple[int, int]
) -> None:
    """Write the small-vs-full corpus recall comparison (new files, no clobber)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "benchmark": "v4",
        "arm": REAL_RETRIEVAL_LABEL,
        "query_rule": query_rule,
        "gold_label": "segment(s) containing the fixture probe, applied after retrieval",
        "small_corpus": {"documents": n_docs[0], **small},
        "full_corpus": {
            "documents": n_docs[1],
            "description": "v4 private store plus every document in data/literature_store",
            **full,
        },
        "note": (
            "Small-corpus recall overstates retrieval quality: with only the v4 "
            "papers indexed there are few distractors. The full corpus adds the "
            "other ingested papers and the PyBaMM documentation."
        ),
    }
    (out_dir / "retrieval_recall_distractors.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True)
    )
    lines = [
        "# v4 — real-retrieval recall: small vs full corpus (distractor stress)",
        "",
        f"arm: {REAL_RETRIEVAL_LABEL}",
        "",
        f"query rule: {query_rule}",
        "",
        "The probe is used only as a post-retrieval evaluation label, never in the "
        "query or evidence selection. No model call is made.",
        "",
        f"items: {small['n_items']}; evidence shown to extractor: top "
        f"{small['evidence_k']} segments",
        "",
        f"- small corpus: {n_docs[0]} documents (private v4 store)",
        f"- full corpus: {n_docs[1]} documents (v4 store + all ingested papers "
        "and PyBaMM docs)",
        "",
        "| k | small corpus | full corpus (distractors) |",
        "|---:|---:|---:|",
    ]
    for k in small["k_values"]:
        lines.append(
            f"| {k} | {small['recall'][f'recall@{k}']:.3f} | "
            f"{full['recall'][f'recall@{k}']:.3f} |"
        )
    lines += [
        "",
        "Small-corpus recall overstates retrieval quality: fewer distractors make "
        "the same query easier. The higher v4 numbers must be read with that in "
        "mind (no experimental claim).",
        "",
    ]
    (out_dir / "retrieval_recall_distractors.md").write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", choices=["v3", "v4"], required=True)
    ap.add_argument(
        "--stress",
        action="store_true",
        help="v4 only: also evaluate against a full corpus containing all "
        "ingested documents as distractors; writes new *_distractors files",
    )
    args = ap.parse_args()
    if args.stress and args.benchmark != "v4":
        raise SystemExit("--stress is only supported for --benchmark v4")

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
        full_store = DocumentStore(MAIN_STORE) if args.stress else None

    summary, rows = evaluate_recall(
        items,
        store,
        index=BM25Index(store.segments()),
        k_values=RECALL_KS,
        evidence_k=DEFAULT_RETRIEVAL_K,
    )
    if not args.stress:
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
    if args.stress:
        assert full_store is not None
        all_segments = list(store.segments()) + list(full_store.segments())
        full_summary, full_rows = evaluate_recall(
            items,
            store,
            index=BM25Index(all_segments),
            k_values=RECALL_KS,
            evidence_k=DEFAULT_RETRIEVAL_K,
        )
        small_docs = {s.document_id for s in store.segments()}
        all_docs = {s.document_id for s in all_segments}
        _write_stress_report(
            summary, full_summary, out_dir, query_rule, (len(small_docs), len(all_docs))
        )
        V4_FULL_AUDIT.parent.mkdir(parents=True, exist_ok=True)
        V4_FULL_AUDIT.write_text(
            json.dumps(
                {
                    "benchmark": "v4",
                    "corpus": "small + all ingested documents",
                    "generated": datetime.now(timezone.utc).isoformat(),
                    "per_item": full_rows,
                },
                indent=2,
                sort_keys=True,
            )
        )
        print(json.dumps(full_summary["recall"], indent=2, sort_keys=True))
        print(f"wrote {out_dir / 'retrieval_recall_distractors.md'} and {V4_FULL_AUDIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
