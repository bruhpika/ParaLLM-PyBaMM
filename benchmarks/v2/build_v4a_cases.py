#!/usr/bin/env python
"""Build the v4a applicability mini-benchmark case set.

Public cases go to ``data/eval/applicability_benchmark_v4a.jsonl`` (no gold
answers). The answer key stays private under ``data/private_v4/``. The dev/test
split is frozen in ``configs/v2/v4a_split.json``. No parameter value is
invented; candidates are copied from the committed registry.

Usage:
    .venv/bin/python benchmarks/v2/build_v4a_cases.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.eval.v4a_cases import (  # noqa: E402
    GOLD_RULE,
    GOLD_RULE_VERSION,
    build_dataset,
)

REGISTRY = REPO_ROOT / "data/registry/registry.json"
PUBLIC_OUT = REPO_ROOT / "data/eval/applicability_benchmark_v4a.jsonl"
PRIVATE_OUT = REPO_ROOT / "data/private_v4/applicability_answers_v4a.jsonl"
SPLIT_OUT = REPO_ROOT / "configs/v2/v4a_split.json"
SPLIT_SEED = 20261119


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def _split(case_ids: list[str]) -> dict:
    ordered = sorted(case_ids)
    test = [cid for i, cid in enumerate(ordered) if i % 3 == 0]
    dev = [cid for cid in ordered if cid not in set(test)]
    return {
        "benchmark": "v4a",
        "seed": SPLIT_SEED,
        "rule": "sorted case_id, every 3rd -> test",
        "dev": dev,
        "test": test,
    }


def main() -> int:
    records = json.loads(REGISTRY.read_text(encoding="utf-8"))
    public, answers = build_dataset(records)
    if not public:
        print("no same-source conflicts found in the registry")
        return 1

    _write_jsonl(PUBLIC_OUT, public)
    _write_jsonl(PRIVATE_OUT, answers)
    SPLIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    SPLIT_OUT.write_text(
        json.dumps(_split([row["case_id"] for row in public]), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(public)} public cases to {PUBLIC_OUT}")
    print(f"wrote {len(answers)} private answers to {PRIVATE_OUT}")
    print(f"wrote split to {SPLIT_OUT}")
    print(f"gold rule {GOLD_RULE_VERSION}: {GOLD_RULE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
