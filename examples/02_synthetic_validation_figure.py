#!/usr/bin/env python
"""Example 2: regenerate the synthetic-validation RMSE figure.

Reads the committed V2.4 report files and writes the two-panel held-out RMSE
figure. No simulation, model download or network access. The output is a
SYNTHETIC method-check figure, not experimental validation.

Usage:
    .venv/bin/python examples/02_synthetic_validation_figure.py \
        --out-dir examples/output/02_synthetic_validation_figure
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/plot_synthetic_validation.py"
DEFAULT_OUT = REPO_ROOT / "examples/output/02_synthetic_validation_figure"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / "heldout_rmse.png"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out)],
        check=True,
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
