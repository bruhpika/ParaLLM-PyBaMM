# v4a applicability mini-benchmark

**Status:** implemented (V2.7). The public case set is committed; the gold
answers stay private under `data/private_v4/` (decision D5). The answers are
**drafted** and pending owner review.

## What it measures

Given one or more candidate values for a parameter and a target cell
specification, does the deterministic applicability rubric resolve the
conflict the way the gold rule says it should?

The v4a set is a **conflict-resolution mini-benchmark**: every case is a
same-source conflict drawn from the committed parameter registry. No parameter
value is invented; the candidates are copied verbatim from the registry,
including the preserved alternative.

## Gold rule (`v4a-gold-1`)

For a same-source conflict, adopt the source's operative (parameterized) value
and preserve the competing value with its method. The decision is `FIX` when
the operative value is `ASSUMED` or `CALIBRATED` and `USE` otherwise.

This is a deterministic, evidence-grounded rule. It is **not** an independent
expert judgement, and agreement against it is a reproducibility/regression
check for the conflict-resolution rule — not the headline expert-agreement
metric of V2.1.

## Files

| File | Visibility | Content |
|---|---|---|
| `data/eval/applicability_benchmark_v4a.jsonl` | public | cases with candidates (no gold) |
| `data/private_v4/applicability_answers_v4a.jsonl` | private | gold answers, drafted |
| `configs/v2/v4a_split.json` | public | frozen dev/test split (seed 20261119) |
| `results/v2/applicability_v4a/agreement.json` | public | aggregate agreement |
| `results/v2/applicability_v4a/summary.md` | public | human-readable summary |

## Reproduce

```bash
.venv/bin/python benchmarks/v2/build_v4a_cases.py   # builds cases + split
.venv/bin/python benchmarks/v2/run_v4a.py           # scores against private gold
```

The builder is deterministic: re-running it on the same registry produces the
same case set and split. The private answer key is not published; a third
party can run the rubric on the public cases and compare with the published
aggregate, but cannot see the per-case gold.

## Limitations

1. Seven cases (the registry's same-source conflicts). The set is small and is
   expected to grow (roadmap D1).
2. Gold answers follow a deterministic rule, not independent expert review.
3. Cross-source and applicability-only cases are not yet included.
