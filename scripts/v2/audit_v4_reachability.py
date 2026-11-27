"""Audit which private-v4 gold conditions are present in the evidence window.

This is a **diagnostic**, not a re-score: it makes no model calls and never
touches the frozen scorer. A gold field that is absent from the evidence cannot
be recovered without importing outside knowledge, which the extraction prompt
forbids. The audit therefore reports an upper bound ("evidence ceiling") so a
missed benchmark criterion is not misattributed to the extractor.

Public output is aggregate only. Per-item unreachable fields contain private
gold labels and are written under ``data/private_v4/``.

Usage:
    .venv/bin/python scripts/v2/audit_v4_reachability.py --split all
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
import sys  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.eval.benchmark_v4 import (  # noqa: E402
    CONDITION_FIELDS,
    evidence_ceiling,
    load_items,
)

FIXTURE = REPO_ROOT / "data/private_v4/fixture/benchmark_v4.jsonl"
SPLIT_CONFIG = REPO_ROOT / "configs/retrieval/dev_test_split.json"
DEFAULT_EVIDENCE = REPO_ROOT / "data/private_v4/results/raw_v25_r0.jsonl"
DEFAULT_OUT = REPO_ROOT / "results/v2/v4_reachability"
DEFAULT_PRIVATE_DETAIL = (
    REPO_ROOT / "data/private_v4/results/reachability_detail.json"
)


def load_evidence(path: Path) -> dict[str, str]:
    """Evidence windows from one frozen raw run (identical across repeats)."""
    out: dict[str, str] = {}
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            out[row["item_id"]] = row["evidence"]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("all", "dev", "test"), default="all")
    parser.add_argument("--evidence-from", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--private-detail", type=Path, default=DEFAULT_PRIVATE_DETAIL
    )
    args = parser.parse_args(argv)

    if not FIXTURE.exists():
        parser.error(f"private fixture missing: {FIXTURE}")
    if not args.evidence_from.exists():
        parser.error(f"frozen raw file missing: {args.evidence_from}")

    items = load_items(FIXTURE)
    split = json.loads(SPLIT_CONFIG.read_text())["benchmarks"]["v4"]
    split_ids = split.get(args.split) if args.split != "all" else None
    result = evidence_ceiling(items, load_evidence(args.evidence_from), split_ids)

    summary = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "fixture": "PRIVATE v4 (30 items; fixture not published)",
        "split": args.split,
        "split_seed": split["seed"],
        "evidence_source": str(
            args.evidence_from.relative_to(REPO_ROOT)
            if args.evidence_from.is_relative_to(REPO_ROOT)
            else args.evidence_from
        ),
        "n_items": result["n_items"],
        "n_fields": result["n_fields"],
        "n_reachable_fields": result["n_reachable_fields"],
        "condition_field_ceiling": result["condition_field_ceiling"],
        "per_field_ceiling": result["per_field_ceiling"],
        "fields": list(CONDITION_FIELDS),
        "note": (
            "Diagnostic upper bound only: a not_stated gold is reachable by "
            "abstaining; a stated gold absent from the evidence window cannot "
            "be recovered without importing outside knowledge."
        ),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True)
    )
    lines = [
        "# Private v4 — evidence reachability (diagnostic)",
        "",
        f"split: `{args.split}` (seed {split['seed']}); evidence from "
        f"`{summary['evidence_source']}`; no model calls.",
        "",
        f"Reachable gold fields: **{result['n_reachable_fields']}/"
        f"{result['n_fields']}** = "
        f"**{result['condition_field_ceiling']:.3f}** "
        "(upper bound for condition-field accuracy).",
        "",
        "| field | reachable / total | ceiling |",
        "| --- | ---: | ---: |",
    ]
    for field in CONDITION_FIELDS:
        name = field.replace("|", "\\|")
        lines.append(
            f"| {name} | "
            f"{summary['per_field_ceiling'][field] * result['n_items']:.0f} / "
            f"{result['n_items']} | "
            f"{summary['per_field_ceiling'][field]:.3f} |"
        )
    lines += [
        "",
        "Per-item unreachable fields stay private: "
        "`data/private_v4/results/reachability_detail.json`.",
    ]
    (args.out / "summary.md").write_text("\n".join(lines) + "\n")

    args.private_detail.parent.mkdir(parents=True, exist_ok=True)
    args.private_detail.write_text(
        json.dumps(
            {
                "generated": summary["generated"],
                "split": args.split,
                "unreachable": result["unreachable"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(
        f"evidence ceiling ({args.split}): "
        f"{result['n_reachable_fields']}/{result['n_fields']} = "
        f"{result['condition_field_ceiling']:.3f}; "
        f"wrote {args.out / 'summary.md'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
