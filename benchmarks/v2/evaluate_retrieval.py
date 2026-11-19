"""Frozen retrieval evaluation protocol and BM25 baseline (no model calls).

The gold segment is taken from the frozen audit files *after* retrieval and is
never used in a query, query expansion, boost, prompt or configuration choice.
Tuning happens on dev only; the test split is reported once per configuration.

Outputs (script-generated only):
  configs/retrieval/dev_test_split.json          frozen stratified split + seed
  results/v2/retrieval_improvement/baseline.json / baseline.md
  results/v2/retrieval_improvement/config_log.jsonl
  data/private_v4/results/retrieval_improvement_baseline_audit.json (private)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.eval.benchmark_p5 import load_items_v3  # noqa: E402
from pybamm_closed_loop.eval.benchmark_v4 import load_items  # noqa: E402
from pybamm_closed_loop.eval.retrieval_arms import (  # noqa: E402
    RECALL_KS,
    query_for_item,
    recall_at_k,
)
from pybamm_closed_loop.literature.index import BM25Index, SYNONYMS  # noqa: E402
from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402
from pybamm_closed_loop.registry.textnorm import ascii_fold  # noqa: E402

V3_ITEMS = REPO_ROOT / "data/eval/extraction_benchmark_v3.jsonl"
V3_STORE = REPO_ROOT / "data/literature_store"
V3_AUDIT = REPO_ROOT / "results/p5/benchmark_v3/retrieval_recall_audit.json"
V4_ITEMS = REPO_ROOT / "data/private_v4/fixture/benchmark_v4.jsonl"
V4_STORE = REPO_ROOT / "data/private_v4/store"
V4_FULL_AUDIT = REPO_ROOT / "data/private_v4/results/retrieval_recall_full_audit.json"
V4_SMALL_AUDIT = REPO_ROOT / "data/private_v4/results/retrieval_recall_audit.json"
PRIVATE_OUT = REPO_ROOT / "data/private_v4/results/retrieval_improvement_baseline_audit.json"
SPLIT_PATH = REPO_ROOT / "configs/retrieval/dev_test_split.json"
OUT_DIR = REPO_ROOT / "results/v2/retrieval_improvement"
CONFIG_LOG = OUT_DIR / "config_log.jsonl"
SEED = 20261119
BOOTSTRAP_N = 2000
METRIC_KEYS = [f"recall@{k}" for k in RECALL_KS] + ["mrr"] + [
    f"document_recall@{k}" for k in RECALL_KS
]


def parameter_type(item: Any) -> str:
    """Stratum key from declared parameter description only (no gold data)."""
    if hasattr(item, "facets"):
        names = list(item.facets.get("parameter_names") or [])
        raw = str(names[0]) if names else ""
    else:
        raw = str((item.parameter or {}).get("name") or "")
    folded = ascii_fold(raw).lower()
    for key, aliases in SYNONYMS.items():
        specific = [a for a in aliases if len(a) > 4]
        if any(a in folded for a in specific):
            return key
    tokens = re.findall(r"[a-z]+", folded)
    return tokens[0] if tokens else "unknown"


def make_split(items: Sequence[Any], seed: int = SEED) -> dict[str, list[str]]:
    """Stratify by document and parameter type; seeded order within each cell."""
    groups: dict[tuple[str, str], list[Any]] = {}
    for item in items:
        groups.setdefault((str(item.document_id), parameter_type(item)), []).append(item)
    dev: list[str] = []
    test: list[str] = []
    for group_index, key in enumerate(sorted(groups)):
        bucket = sorted(
            groups[key],
            key=lambda it: hashlib.sha256(f"{seed}:{it.item_id}".encode()).hexdigest(),
        )
        # Alternate the first assignment across strata so singleton strata do
        # not all land in dev.
        for i, item in enumerate(bucket):
            (dev if (i + group_index) % 2 == 0 else test).append(str(item.item_id))
    return {"seed": seed, "dev": sorted(dev), "test": sorted(test)}


def load_split(*, write: bool = False) -> dict[str, Any]:
    if SPLIT_PATH.exists():
        return json.loads(SPLIT_PATH.read_text())
    if not write:
        raise SystemExit(f"missing frozen split {SPLIT_PATH}; run with --write-split")
    v3 = make_split(load_items_v3(V3_ITEMS))
    v4 = make_split(load_items(V4_ITEMS))
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "method": "stratified by (document_id, parameter_type); seeded sha256 order, alternating dev/test",
        "parameter_type_source": "declared facets / parameter name only; no probe or gold label",
        "benchmarks": {"v3": v3, "v4": v4},
    }
    SPLIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPLIT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def log_config(payload: dict[str, Any]) -> None:
    CONFIG_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_LOG.open("a") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def load_gold(path: Path) -> dict[str, dict[str, Any]]:
    return {row["item_id"]: row for row in json.loads(path.read_text())["per_item"]}


def bootstrap_ci(values: Sequence[float], seed: int) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return {"low": float("nan"), "high": float("nan")}
    rng = np.random.default_rng(seed)
    means = np.empty(BOOTSTRAP_N)
    for i in range(BOOTSTRAP_N):
        means[i] = arr[rng.integers(0, arr.size, arr.size)].mean()
    return {"low": float(np.percentile(means, 2.5)), "high": float(np.percentile(means, 97.5))}


def evaluate(
    items: Sequence[Any],
    index: BM25Index,
    gold: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    max_k = max(RECALL_KS)
    indexed_segments = {s.segment_id for s in index.segments}
    indexed_docs = {s.document_id for s in index.segments}
    rows: list[dict[str, Any]] = []
    for item in items:
        query = query_for_item(item)
        hits = index.search(query, k=max_k)
        hit_ids = [seg.segment_id for seg, _ in hits]
        hit_docs = [seg.document_id for seg, _ in hits]
        gold_ids = list(gold.get(str(item.item_id), {}).get("gold_segment_ids") or [])
        gold_doc = str(item.document_id)
        gold_set = set(gold_ids)
        reciprocal = 0.0
        for rank, sid in enumerate(hit_ids, 1):
            if sid in gold_set:
                reciprocal = 1.0 / rank
                break
        rows.append(
            {
                "item_id": str(item.item_id),
                "query": query,
                "gold_segment_ids": gold_ids,
                "gold_retrievable": bool(gold_set & indexed_segments)
                and gold_doc in indexed_docs,
                "query_matches_frozen_audit": (
                    query == gold.get(str(item.item_id), {}).get("query")
                ),
                "recall": {f"recall@{k}": recall_at_k(hit_ids, gold_ids, k) for k in RECALL_KS},
                "mrr": reciprocal,
                "document_recall": {
                    f"document_recall@{k}": float(gold_doc in hit_docs[:k]) for k in RECALL_KS
                },
            }
        )

    summary: dict[str, Any] = {}
    for key in METRIC_KEYS:
        prefix, k = key.split("@") if "@" in key else (key, None)
        values = [
            (r["recall"] if prefix == "recall" else r["document_recall"])[key]
            if k
            else r["mrr"]
            for r in rows
        ]
        summary[key] = {
            "mean": float(np.mean(values)) if values else None,
            "ci95": bootstrap_ci(values, SEED),
            "n": len(values),
        }
    return {
        "metrics": summary,
        "n_items": len(rows),
        "n_gold_retrievable": sum(1 for r in rows if r["gold_retrievable"]),
        "n_query_mismatches": sum(1 for r in rows if not r["query_matches_frozen_audit"]),
        "n_documents_indexed": len(indexed_docs),
        "n_segments_indexed": len(index.segments),
    }, rows


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# BM25 retrieval baseline — frozen dev/test protocol",
        "",
        f"Seed: {payload['seed']} (split `configs/retrieval/dev_test_split.json`).",
        f"Configurations logged so far: {payload['n_configurations_logged']} "
        "(`config_log.jsonl`, failures included).",
        "Tuning is dev-only; test is reported once per configuration family.",
        "Gold labels are frozen post-retrieval audit labels; no probe or gold",
        "information enters the query, expansion, boosts or configuration choice.",
        "",
    ]
    for bench, corpora in payload["benchmarks"].items():
        for corpus, splits in corpora.items():
            lines += [f"## {bench} / {corpus}", ""]
            lines.append(
                f"index: {splits['dev']['n_documents_indexed']} documents, "
                f"{splits['dev']['n_segments_indexed']} segments; "
                f"gold retrievable: dev {splits['dev']['n_gold_retrievable']}/"
                f"{splits['dev']['n_items']}, test "
                f"{splits['test']['n_gold_retrievable']}/{splits['test']['n_items']}"
            )
            lines += [
                "",
                "| metric | dev mean [95% CI] | test mean [95% CI] |",
                "|---|---:|---:|",
            ]
            for key in METRIC_KEYS:
                cells = []
                for split in ("dev", "test"):
                    m = splits[split]["metrics"][key]
                    cells.append(
                        f"{m['mean']:.3f} [{m['ci95']['low']:.3f}, {m['ci95']['high']:.3f}]"
                    )
                lines.append(f"| {key} | {cells[0]} | {cells[1]} |")
            lines.append("")
    lines += [
        "## Caveats",
        "",
        f"- {payload['corpus_note']}",
        "- The v4 corpus is small and private; v3 and v4 numbers are **not comparable**.",
        "- Item-level v4 rows stay private; this file reports aggregates only.",
        "- Query mismatches vs the frozen audits and unretrievable gold labels are",
        "  counted above; they are not silently dropped.",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-split", action="store_true")
    args = ap.parse_args(argv)

    split = load_split(write=args.write_split)
    v3_all = load_items_v3(V3_ITEMS)
    v4_all = load_items(V4_ITEMS)
    v3_by_id = {str(it.item_id): it for it in v3_all}
    v4_by_id = {str(it.item_id): it for it in v4_all}

    v3_gold = load_gold(V3_AUDIT)
    v4_small_gold = load_gold(V4_SMALL_AUDIT)
    v4_full_gold = load_gold(V4_FULL_AUDIT)

    main_store = DocumentStore(V3_STORE)
    v4_store = DocumentStore(V4_STORE)
    corpora = {
        "v3": {
            "full": (v3_by_id, v3_gold, BM25Index(main_store.segments())),
        },
        "v4": {
            "small": (v4_by_id, v4_small_gold, BM25Index(v4_store.segments())),
            "full": (
                v4_by_id,
                v4_full_gold,
                BM25Index(v4_store.segments() + main_store.segments()),
            ),
        },
    }

    payload: dict[str, Any] = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "corpus_note": (
            "Current local stores hold 4 documents for v3 and 8 for the v4 full "
            "corpus after the Chen2020 article text and supplement were "
            "untracked. The committed v3/v4 recall figures were produced with "
            "6 and 10 documents; the re-measured numbers here describe the "
            "current local corpus and are not directly comparable with them."
        ),
        "bootstrap_n": BOOTSTRAP_N,
        "bm25": {"k1": 1.5, "b": 0.75, "expansion": "SYNONYMS full-group (unchanged)"},
        "label_source": {
            "v3": str(V3_AUDIT.relative_to(REPO_ROOT)),
            "v4_small": "data/private_v4/results/retrieval_recall_audit.json",
            "v4_full": "data/private_v4/results/retrieval_recall_full_audit.json",
        },
        "benchmarks": {},
    }
    private_rows: dict[str, list[dict[str, Any]]] = {}
    for bench, by_corpus in corpora.items():
        payload["benchmarks"][bench] = {}
        for corpus, (by_id, gold, index) in by_corpus.items():
            for split_name in ("dev", "test"):
                ids = split["benchmarks"][bench][split_name]
                items = [by_id[i] for i in ids if i in by_id]
                if len(items) != len(ids):
                    raise SystemExit(f"{bench}: missing items in {split_name} split")
                stats, rows = evaluate(items, index, gold)
                payload["benchmarks"][bench][corpus] = payload["benchmarks"][bench].get(
                    corpus, {}
                )
                payload["benchmarks"][bench][corpus][split_name] = stats
                private_rows[f"{bench}/{corpus}/{split_name}"] = rows
                log_config(
                    {
                        "generated": datetime.now(timezone.utc).isoformat(),
                        "configuration": f"{bench}/{corpus}/{split_name}",
                        "status": "ok",
                        "k1": 1.5,
                        "b": 0.75,
                        "seed": SEED,
                        "n_items": stats["n_items"],
                        "n_gold_retrievable": stats["n_gold_retrievable"],
                    }
                )

    payload["n_configurations_logged"] = sum(1 for _ in CONFIG_LOG.open())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "baseline.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (OUT_DIR / "baseline.md").write_text(_render_md(payload))
    PRIVATE_OUT.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_OUT.write_text(json.dumps(private_rows, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT_DIR / 'baseline.json'}, {OUT_DIR / 'baseline.md'}")
    print(f"private per-item audit: {PRIVATE_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
