#!/usr/bin/env python
"""Plot held-out voltage RMSE for the synthetic validation runs.

Reads committed ``report.json`` files only: no simulation, model download or
network access. These are SYNTHETIC method checks (data generated and fitted
with the same model family), not experimental validation.

Usage:
    .venv/bin/python scripts/plot_synthetic_validation.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_REPORT = REPO_ROOT / "results/v2/synthetic_validation/report.json"
MISMATCH_REPORT = REPO_ROOT / "results/v2/synthetic_validation_mismatch/report.json"
DEFAULT_OUT = REPO_ROOT / "results/v2/synthetic_validation/heldout_rmse.png"

ARMS = (
    ("baseline", "Baseline", "#4d4d4d", "o"),
    ("positive_control", "Positive control", "#1f77b4", "s"),
    ("negative_control", "Negative control", "#d62728", "x"),
)


def _load_report(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_main_series(path: Path) -> dict[str, list[float]]:
    """Return per-seed held-out RMSE in mV for the three V2.4 arms."""
    rows = _load_report(path)["stability"]["per_seed"]
    return {
        "seeds": [int(row["seed"]) for row in rows],
        "baseline": [1000.0 * float(row["baseline_mean_V"]) for row in rows],
        "positive_control": [1000.0 * float(row["positive_mean_V"]) for row in rows],
        "negative_control": [1000.0 * float(row["negative_mean_V"]) for row in rows],
    }


def load_mismatch_series(path: Path) -> dict[str, list[float]]:
    """Return per-run held-out RMSE in mV for the harder mismatch arms."""
    rows = _load_report(path)["per_run"]
    return {
        "seeds": [int(row["seed"]) for row in rows],
        "baseline": [1000.0 * float(row["baseline_mean_V"]) for row in rows],
        "positive_control": [1000.0 * float(row["positive_mean_V"]) for row in rows],
        "negative_control": [1000.0 * float(row["negative_mean_V"]) for row in rows],
    }


def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    return float(array.mean()), float(array.std())


def _draw_means(ax, series: dict[str, list[float]], *, annotate: bool) -> None:
    positions = np.arange(len(ARMS), dtype=float)
    for i, (key, label, color, marker) in enumerate(ARMS):
        mean, std = _mean_std(series[key])
        ax.errorbar(
            positions[i],
            mean,
            yerr=std,
            fmt=marker,
            color=color,
            capsize=4,
            markersize=6,
            linestyle="none",
            zorder=3,
            label=label,
        )
        if annotate:
            ax.annotate(
                f"{mean:.2f}",
                (positions[i], mean),
                textcoords="offset points",
                xytext=(0, 10),
                ha="center",
                fontsize=8,
                color=color,
            )
    ax.set_xticks(positions, [label for _, label, _, _ in ARMS])


def plot_overview(
    main: dict[str, list[float]],
    mismatch: dict[str, list[float]],
    out_path: Path,
) -> Path:
    """Write a two-panel overview figure and return the output path."""
    fig, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(10.0, 4.2), constrained_layout=True
    )
    positions = np.arange(len(ARMS), dtype=float)

    n_seeds = len(main["baseline"])
    for i in range(n_seeds):
        values = [main[key][i] for key, _, _, _ in ARMS]
        ax_left.plot(
            positions,
            values,
            color="0.75",
            linewidth=0.8,
            marker="o",
            markersize=3,
            zorder=1,
        )
    _draw_means(ax_left, main, annotate=True)
    ax_left.set_ylabel("Held-out voltage RMSE [mV]")
    ax_left.set_title(f"V2.4 stability ({n_seeds} seeds)")
    ax_left.grid(axis="y", alpha=0.3)
    ax_left.legend(loc="upper right", fontsize=8, frameon=False)
    ax_left.text(
        0.02,
        0.95,
        "SYNTHETIC; not experimental validation",
        transform=ax_left.transAxes,
        va="top",
        fontsize=8,
        color="0.3",
    )

    n_runs = len(mismatch["baseline"])
    jitter = np.linspace(-0.06, 0.06, n_runs)
    for i, (key, _, color, marker) in enumerate(ARMS):
        ax_right.scatter(
            positions[i] + jitter,
            mismatch[key],
            s=18,
            color=color,
            marker=marker,
            alpha=0.75,
            linewidths=0.8,
            zorder=2,
        )
    _draw_means(ax_right, mismatch, annotate=False)
    ax_right.set_title(f"V2.4 mismatch ({n_runs} runs)")
    ax_right.grid(axis="y", alpha=0.3)
    ax_right.text(
        0.02,
        0.95,
        "positive beats baseline 15/18; negative 0/18",
        transform=ax_right.transAxes,
        va="top",
        fontsize=8,
        color="0.3",
    )

    values = [v for key, _, _, _ in ARMS for v in main[key] + mismatch[key]]
    top = max(values) * 1.25
    ax_left.set_ylim(0, top)
    ax_right.set_ylim(0, top)
    fig.suptitle("Held-out voltage RMSE: synthetic method check, not experimental validation")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-report", type=Path, default=MAIN_REPORT)
    parser.add_argument("--mismatch-report", type=Path, default=MISMATCH_REPORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    main_series = load_main_series(args.main_report)
    mismatch_series = load_mismatch_series(args.mismatch_report)
    path = plot_overview(main_series, mismatch_series, args.out)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
