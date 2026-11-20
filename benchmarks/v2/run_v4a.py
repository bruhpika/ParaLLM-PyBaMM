#!/usr/bin/env python
"""Score the applicability rubric against the v4a mini-benchmark (gold: private).

Public cases come from ``data/eval/applicability_benchmark_v4a.jsonl``; the
gold answers stay in ``data/private_v4/applicability_answers_v4a.jsonl``. The
runner reports decision and choice agreement overall and by dev/test split.

Usage:
    .venv/bin/python benchmarks/v2/run_v4a.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.assembly import Rubric, TargetSpecification  # noqa: E402
from pybamm_closed_loop.eval.assembly_cases import (  # noqa: E402
    ApplicabilityCase,
    agreement,
    score_case,
)
from pybamm_closed_loop.eval.v4a_cases import (  # noqa: E402
    GOLD_RULE,
    GOLD_RULE_VERSION,
    TARGET_ID,
)

PUBLIC_CASES = REPO_ROOT / "data/eval/applicability_benchmark_v4a.jsonl"
PRIVATE_ANSWERS = REPO_ROOT / "data/private_v4/applicability_answers_v4a.jsonl"
SPLIT = REPO_ROOT / "configs/v2/v4a_split.json"
DEFAULT_OUT = REPO_ROOT / "results/v2/applicability_v4a"

TARGET = TargetSpecification(
    target_id=TARGET_ID,
    cell_product="LG M50",
    chemistry_families=("NMC", "graphite"),
    format="21700",
    temperature_k=298.15,
    soc="50%",
    electrolyte="1 mol dm-3 LiPF6 in EC:EMC (3:7 V/V), 1 wt% VC",
)


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _merge(cases: list[dict], answers: list[dict]) -> list[ApplicabilityCase]:
    by_id = {a["case_id"]: a for a in answers}
    merged: list[ApplicabilityCase] = []
    for case in cases:
        answer = by_id.get(case["case_id"])
        if answer is None:
            continue
        merged.append(
            ApplicabilityCase(
                case_id=case["case_id"],
                target_id=case["target_id"],
                parameter=case["parameter"],
                candidates=case["candidates"],
                expert_decision=answer["expert_decision"],
                expert_choice=answer.get("expert_choice"),
                expert_rationale=answer.get("expert_rationale", ""),
                ambiguous=bool(answer.get("ambiguous", False)),
                case_class=case.get("case_class", "conflict"),
                reviewed_by=answer.get("reviewed_by"),
            )
        )
    return merged


def _summary(rows: list[dict], split: dict | None) -> dict:
    agg = agreement(rows)
    out = {"all": agg.get("all", {}), "label_status": agg.get("label_status", {})}
    for cls in sorted(k for k in agg if k.startswith("class:")):
        out[cls] = agg[cls]
    if split:
        for name in ("dev", "test"):
            ids = set(split.get(name, []))
            subset = [r for r in rows if r["case_id"] in ids]
            if subset:
                out[name] = agreement(subset)["all"]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=PUBLIC_CASES)
    parser.add_argument("--answers", type=Path, default=PRIVATE_ANSWERS)
    parser.add_argument("--split", type=Path, default=SPLIT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--rubric-version", default="rubric-v2")
    args = parser.parse_args(argv)

    if not args.cases.exists():
        print(f"public case set not found: {args.cases}")
        return 1
    if not args.answers.exists():
        print(f"private answer key not found: {args.answers}")
        return 1

    cases = _load_jsonl(args.cases)
    answers = _load_jsonl(args.answers)
    merged = _merge(cases, answers)
    if not merged:
        print("no cases matched the answer key")
        return 1

    rubric = Rubric(args.rubric_version)
    rows = [score_case(case, rubric, TARGET) for case in merged]

    split = json.loads(args.split.read_text()) if args.split.exists() else None
    summary = _summary(rows, split)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "agreement.json").write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).isoformat(),
                "benchmark": "v4a",
                "rubric_version": args.rubric_version,
                "gold_rule_version": GOLD_RULE_VERSION,
                "gold_rule": GOLD_RULE,
                "n_cases": len(rows),
                "summary": summary,
                "split": split,
                "note": (
                    "Gold answers are drafted and kept private "
                    "(data/private_v4/applicability_answers_v4a.jsonl)."
                ),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    mismatches = [r for r in rows if not r["match"]]
    lines = [
        "# v4a — applicability mini-benchmark",
        "",
        f"rubric: `{args.rubric_version}` · cases: {len(rows)} "
        "(PUBLIC set, answers private)",
        "",
        f"gold rule `{GOLD_RULE_VERSION}`: {GOLD_RULE}",
        "",
        "| scope | n | decision agreement | full agreement | mismatched decisions |",
        "|---|---:|---:|---:|---:|",
    ]
    for scope in ["all", "dev", "test"] + sorted(k for k in summary if k.startswith("class:")):
        block = summary.get(scope)
        if not block:
            continue
        lines.append(
            f"| {scope} | {block['n_cases']} | {block['decision_agreement']:.3f} | "
            f"{block['full_agreement']:.3f} | {block['n_mismatched_decision']} |"
        )
    lines += ["", "## Mismatches", ""]
    for r in mismatches:
        lines.append(
            f"- `{r['case_id']}` ({r['parameter']}): expert "
            f"**{r['expert_decision']}** vs rubric **{r['rubric_decision']}**"
        )
    if not mismatches:
        lines.append("- none")
    (args.out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"agreement: {summary['all']['decision_agreement']:.3f} "
          f"({summary['all']['n_cases']} cases)")
    print(f"wrote {args.out}/agreement.json, summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
