"""Assemble offline end-to-side side-by-side tables from committed run files.

No model calls, no re-running of harnesses, no hand-edited numbers.
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "results/v2/retrieval_improvement"
JSON_OUT = OUT_DIR / "offline_side_by_side.json"
MD_OUT = OUT_DIR / "offline_side_by_side.md"

V3 = REPO_ROOT / "results/p5/benchmark_v3"


def _metrics(path: Path, key: str | None = None) -> dict[str, float]:
    payload = json.loads(path.read_text())
    if key:
        if key in payload.get("summary", {}):
            payload = payload["summary"][key]
        else:
            payload = payload[key]
    for wrapper in ("metrics", "aggregate", "all"):
        while wrapper in payload and isinstance(payload[wrapper], dict):
            payload = payload[wrapper]
    out: dict[str, float] = {}
    for k, v in payload.items():
        if isinstance(v, (int, float)):
            out[k] = float(v)
        elif isinstance(v, dict) and isinstance(v.get("mean"), (int, float)):
            out[k] = float(v["mean"])
    return out


def _table(lines: list[str], title: str, arms: dict[str, dict[str, float]], keys: list[str]) -> None:
    lines += [f"### {title}", "", "| metric | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for key in keys:
        cells = [f"{arms[a].get(key, float('nan')):.3f}" for a in arms]
        lines.append(f"| {key} | " + " | ".join(cells) + " |")
    lines.append("")


def main() -> int:
    v3_arms = {
        "oracle-located (upper bound)": _metrics(V3 / "aggregate_offline.json"),
        "BM25 baseline": _metrics(V3 / "aggregate_offline_bm25.json"),
        "BM25 tuned (b=0.5)": _metrics(V3 / "report_offline_bm25_tuned_r0.json"),
    }
    v4_arms = {
        "oracle-located (upper bound)": _metrics(
            REPO_ROOT / "results/v2/v4_offline_oracle/summary.json", "compact_r0"
        ),
        "BM25 baseline": _metrics(
            REPO_ROOT / "results/v2/v4_offline_bm25/summary.json", "retrieval_r0"
        ),
        "BM25 tuned (b=0.5)": _metrics(
            REPO_ROOT / "results/v2/v4_offline_tuned/summary.json", "offline_bm25_tuned_r0"
        ),
    }
    lines = [
        "# Offline end-to-end side-by-side: oracle vs BM25 vs tuned BM25",
        "",
        "All arms use the deterministic offline extractor; no LLM call was made.",
        "",
        "## v3 (P5)",
        "",
        "Oracle and BM25 baseline are the committed 37-item aggregates; the tuned",
        "arm is the 22 locally available items after the Chen2020 texts were",
        "untracked. These numbers are **not directly comparable**.",
        "",
    ]
    _table(
        lines,
        "v3 metrics",
        v3_arms,
        [
            "parameter_identification_accuracy",
            "value_extraction_accuracy",
            "provenance_accuracy",
            "condition_completeness",
            "qualifier_classification_accuracy",
            "false_extraction_rate",
            "abstention_accuracy",
        ],
    )
    lines += [
        "## v4 (private)",
        "",
        "All three arms ran on the same 30 private items with the same offline",
        "extractor and the current 8-document full store. The v4 corpus is small",
        "and private; these numbers are not comparable with v3.",
        "",
    ]
    _table(
        lines,
        "v4 metrics",
        v4_arms,
        [
            "parameter_value_accuracy",
            "value_found_rate",
            "condition_field_accuracy",
            "invented_condition_rate",
            "abstention_rate",
            "quote_in_evidence_rate",
        ],
    )
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "v3_oracle": str((V3 / "aggregate_offline.json").relative_to(REPO_ROOT)),
            "v3_bm25": str((V3 / "aggregate_offline_bm25.json").relative_to(REPO_ROOT)),
            "v3_tuned": str(
                (V3 / "report_offline_bm25_tuned_r0.json").relative_to(REPO_ROOT)
            ),
            "v4_oracle": "results/v2/v4_offline_oracle/summary.json",
            "v4_bm25": "results/v2/v4_offline_bm25/summary.json",
            "v4_tuned": "results/v2/v4_offline_tuned/summary.json",
        },
        "v3": v3_arms,
        "v4": v4_arms,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    protocol = importlib.import_module("evaluate_retrieval")
    for bench, arms in (("v3", v3_arms), ("v4", v4_arms)):
        for name in arms:
            protocol.log_config(
                {
                    "generated": datetime.now(timezone.utc).isoformat(),
                    "configuration": f"offline_side_by_side/{bench}/{name}",
                    "status": "ok",
                    "note": "assembled from already-committed run files; no model call",
                }
            )
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    MD_OUT.write_text("\n".join(lines))
    print(f"wrote {JSON_OUT}, {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
