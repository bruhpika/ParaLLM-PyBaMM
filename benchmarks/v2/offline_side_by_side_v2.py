"""Clarified v4 offline side-by-side: evidence volume and dev/test splits.

New outputs only; the committed offline_side_by_side.{json,md} is left intact.
The oracle arm locates the gold passage from the probe but receives a much
smaller evidence block, so it is NOT a performance upper bound in this
offline comparison.
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.eval.benchmark_v4 import aggregate  # noqa: E402

OUT_DIR = REPO_ROOT / "results/v2/retrieval_improvement"
JSON_OUT = OUT_DIR / "offline_side_by_side_v2.json"
MD_OUT = OUT_DIR / "offline_side_by_side_v2.md"
SPLIT = REPO_ROOT / "configs/retrieval/dev_test_split.json"
PRIVATE = REPO_ROOT / "data/private_v4/results"
ORACLE_LABEL_CLARIFIED = "oracle-located (probe window; NOT a performance upper bound)"
ARMS = {
    "oracle compact": ("rows_offline_compact_r0.json", "raw_offline_compact_r0.jsonl"),
    "BM25 baseline": (
        "rows_offline_retrieval_r0.json",
        "raw_offline_retrieval_r0.jsonl",
    ),
    "BM25 tuned (b=0.5)": (
        "rows_offline_bm25_tuned_r0.json",
        "raw_offline_bm25_tuned_r0.jsonl",
    ),
}


def _evidence_stats(raw_path: Path) -> dict[str, float]:
    rows = [json.loads(line) for line in raw_path.read_text().splitlines() if line.strip()]
    lengths = [len(str(row.get("evidence") or "")) for row in rows]
    return {
        "n_items": len(lengths),
        "mean_chars": float(statistics.mean(lengths)) if lengths else 0.0,
        "median_chars": float(statistics.median(lengths)) if lengths else 0.0,
        "min_chars": float(min(lengths)) if lengths else 0.0,
        "max_chars": float(max(lengths)) if lengths else 0.0,
    }


def _render(payload: dict[str, Any]) -> str:
    ev = payload["evidence_volume"]
    lines = [
        "# v4 offline side-by-side (clarified label, split metrics)",
        "",
        f"Oracle label: **{payload['oracle_label']}**.",
        "It locates the gold passage from the fixture probe, but its evidence",
        "block is a small probe window rather than the 8-segment BM25 block.",
        "The arms are therefore **not comparable as an upper-bound vs lower-bound",
        "pair**, and oracle value accuracy must not be read as a ceiling.",
        "",
        "## Evidence volume handed to the extractor",
        "",
        "| arm | items | mean chars | median chars | min | max |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm, stats in ev.items():
        lines.append(
            f"| {arm} | {stats['n_items']} | {stats['mean_chars']:.0f} | "
            f"{stats['median_chars']:.0f} | {stats['min_chars']:.0f} | "
            f"{stats['max_chars']:.0f} |"
        )
    lines += [
        "",
        f"BM25 arms show ~{ev['BM25 tuned (b=0.5)']['mean_chars'] / ev['oracle compact']['mean_chars']:.0f}x"
        " more evidence text than the oracle window (8 segments).",
        "",
    ]
    for split in ("dev", "test"):
        lines += [
            f"## {split} split (n={payload['n_items'][split]})",
            "",
            "| arm | value found | condition accuracy | invented-condition rate | abstention |",
            "|---|---:|---:|---:|---:|",
        ]
        for arm, stats in payload[split].items():
            lines.append(
                f"| {arm} | {stats['value_found_rate']:.3f} | "
                f"{stats['condition_field_accuracy']:.3f} | "
                f"{stats['invented_condition_rate']:.3f} | "
                f"{stats['abstention_rate']:.3f} |"
            )
        lines.append("")
    lines += [
        "Private per-item rows stay under `data/private_v4/results/`; the v4",
        "corpus is small and private and is not comparable with v3.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    split = json.loads(SPLIT.read_text())["benchmarks"]["v4"]
    payload: dict[str, Any] = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "oracle_label": ORACLE_LABEL_CLARIFIED,
        "comparability_note": (
            "oracle compact supplies one ~560-char probe window; BM25 supplies "
            "8 segments (~43-46k chars). Not a matched evidence-volume comparison."
        ),
        "n_items": {k: len(split[k]) for k in ("dev", "test")},
        "evidence_volume": {},
        "dev": {},
        "test": {},
    }
    for arm, (rows_name, raw_name) in ARMS.items():
        payload["evidence_volume"][arm] = _evidence_stats(PRIVATE / raw_name)
        rows = json.loads((PRIVATE / rows_name).read_text())
        for split_name in ("dev", "test"):
            ids = set(split[split_name])
            subset = [row for row in rows if row["item_id"] in ids]
            payload[split_name][arm] = aggregate(subset)["all"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    MD_OUT.write_text(_render(payload))
    print(f"wrote {JSON_OUT}, {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
