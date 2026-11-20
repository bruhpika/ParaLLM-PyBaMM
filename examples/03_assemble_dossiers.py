#!/usr/bin/env python
"""Example 3: assemble per-parameter dossiers for the LG M50 target.

Runs the deterministic assembly CLI over the committed registry. Quote
verification is skipped when the Chen2020 article text is absent locally;
traceability warnings/failures are printed but do not fail this example.

Usage:
    .venv/bin/python examples/03_assemble_dossiers.py \
        --out-dir examples/output/03_assemble
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.cli import main as assemble_main  # noqa: E402

TARGET = REPO_ROOT / "configs/v2/target_lgm50.yaml"
REGISTRY = REPO_ROOT / "data/registry/registry.json"
DOCUMENTS = REPO_ROOT / "data/raw_documents"
P2_RESULTS = REPO_ROOT / "results/p2"
DEFAULT_OUT = REPO_ROOT / "examples/output/03_assemble"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    rc = assemble_main(
        [
            "assemble",
            "--target", str(TARGET),
            "--registry", str(REGISTRY),
            "--out", str(args.out_dir),
            "--documents", str(DOCUMENTS),
            "--p2-results", str(P2_RESULTS),
        ]
    )
    if rc != 0:
        print(
            "note: traceability flags are expected without the Chen2020 "
            "article; see report.json"
        )
    print(f"wrote {args.out_dir}/report.json, report.md, manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
