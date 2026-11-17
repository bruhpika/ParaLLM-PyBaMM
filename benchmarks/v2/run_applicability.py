"""Measure expert agreement of the applicability rubric (V2.1 acceptance).

Runs the deterministic rubric over the **private** applicability case set and
compares each decision with the expert label. The headline number is the
agreement rate; mismatches are listed so every disagreement can be inspected.

Label status matters: until the project owner has reviewed the labels, the
number is *agreement with drafted labels*, not with expert judgement. The
runner reports that status explicitly.

Usage:
    .venv-ecosystem312/bin/python benchmarks/v2/run_applicability.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.eval.assembly_cases import (  # noqa: E402
    agreement,
    load_cases,
    score_case,
)
from pybamm_closed_loop.assembly import Rubric, TargetSpecification  # noqa: E402

DEFAULT_CASES = REPO_ROOT / "data/private_v4/applicability_cases_v1.jsonl"
DEFAULT_OUT = REPO_ROOT / "results/v2/applicability"
TARGET = TargetSpecification(
    target_id="lgm50_chen2020_dfn",
    cell_product="LG M50",
    chemistry_families=("NMC", "graphite"),
    format="21700",
    temperature_k=298.15,
    soc="50%",
    electrolyte="1 mol dm-3 LiPF6 in EC:EMC (3:7 V/V), 1 wt% VC",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(DEFAULT_CASES))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--rubric-version", default="rubric-v2")
    args = ap.parse_args()

    cases_path = Path(args.cases)
    if not cases_path.exists():
        print(f"private case set not found: {cases_path}")
        print("build it with: .venv-ecosystem312/bin/python "
              "data/private_v4/build_applicability_cases.py")
        return 1

    cases = load_cases(cases_path)
    rubric = Rubric(args.rubric_version)

    rows = [score_case(case, rubric, TARGET) for case in cases]
    agg = agreement(rows)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "agreement.json").write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).isoformat(),
                "rubric_version": args.rubric_version,
                "n_cases": len(cases),
                "agreement": agg,
                "label_status": agg.get("label_status"),
                "note": (
                    "Labels are drafted by the assistant until the project owner "
                    "reviews them; agreement against drafted labels is not yet "
                    "agreement with expert judgement."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    # per-case detail stays private
    (out_dir.parent.parent / "private_v4" / "results").mkdir(parents=True, exist_ok=True)
    (out_dir.parent.parent / "private_v4" / "results" / "applicability_rows.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True)
    )

    mismatches = [r for r in rows if not r["match"]]
    lines = [
        "# V2.1 — expert agreement of the applicability rubric",
        "",
        f"rubric: `{args.rubric_version}` · cases: {len(cases)} (PRIVATE set, "
        "labels drafted, pending owner review)",
        "",
        "| scope | n | decision agreement | full agreement | ambiguous | mismatched decisions |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for scope in ["all"] + [k for k in agg if k.startswith("class:")]:
        b = agg[scope]
        lines.append(
            f"| {scope} | {b['n_cases']} | {b['decision_agreement']:.3f} | "
            f"{b['full_agreement']:.3f} | {b['n_ambiguous']} | "
            f"{b['n_mismatched_decision']} |"
        )
    lines += [
        "",
        f"Label status: {agg.get('label_status', {}).get('drafted', 0)} drafted, "
        f"{agg.get('label_status', {}).get('reviewed', 0)} reviewed.",
        "",
        "## Mismatches",
        "",
    ]
    for r in mismatches:
        lines.append(
            f"- `{r['case_id']}` ({r['case_class']}, {r['parameter']}): expert "
            f"**{r['expert_decision']}** vs rubric **{r['rubric_decision']}**"
        )
    if not mismatches:
        lines.append("- none")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")

    print(json.dumps(agg, indent=2, sort_keys=True))
    print(f"wrote {out_dir}/summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
