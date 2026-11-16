"""Run the PRIVATE v4 condition benchmark (V2.5 exit criterion).

Compares the evidence modes on the same private fixture:

  compact   v0.1 behaviour: +/-260-character window around the probe
  expanded  V2.5 slice 1: condition-aware window + document-level setup
  v25       V2.5 full: table-aware chunking + top-k multi-window + document
            level setup conditions

Metrics (frozen scorer in ``eval/benchmark_v4.py``):

* condition-field accuracy — per field (chemistry, cell, format,
  temperature, SOC, method, protocol), where a gold ``not_stated`` field is
  only matched by an extraction that reports nothing there;
* parameter value / unit accuracy;
* invented-condition rate — fields the source never states but the extraction
  fills anyway (always penalised);
* abstention rate.

Per-item results stay PRIVATE (``data/private_v4/results/``); only the
aggregate summary is written to ``results/v2/v4/``.

Usage:
    PYCL_LLM_API_KEY=... PYCL_LLM_BASE_URL=... PYCL_LLM_MODEL=... \
    .venv-ecosystem312/bin/python benchmarks/v2/run_v4_evaluation.py \
        --modes compact expanded v25 --repeats 1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.eval.benchmark_p5 import RobustLLMClient  # noqa: E402
from pybamm_closed_loop.eval.benchmark_p5 import _evidence_block  # noqa: E402
from pybamm_closed_loop.eval.benchmark_v4 import (  # noqa: E402
    aggregate,
    build_v4_prompt,
    coerce_candidates,
    load_items,
    score_item,
)
from pybamm_closed_loop.eval.benchmark_p5 import (  # noqa: E402
    candidates_from_raw,
)
from pybamm_closed_loop.literature.extraction import (  # noqa: E402
    OpenAICompatibleClient,
)
from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402

PRIVATE_ROOT = REPO_ROOT / "data/private_v4"
FIXTURE = PRIVATE_ROOT / "fixture/benchmark_v4.jsonl"
STORE_DIR = PRIVATE_ROOT / "store"
PRIVATE_RESULTS = PRIVATE_ROOT / "results"
PUBLIC_RESULTS = REPO_ROOT / "results/v2/v4"


def run_mode(items, store, mode: str, client, repeat: int, sleep_s: float = 0.0) -> dict:
    prompt = build_v4_prompt()
    rows = []
    raw_rows = []
    t0 = time.monotonic()
    for idx, item in enumerate(items, start=1):
        evidence = _evidence_block(item, store, mode)
        user_block = (
            "QUERY: extract the parameter value and its experimental conditions "
            "for this passage.\n\n"
            f"EVIDENCE:\n{evidence}\n"
        )
        try:
            raw = client.complete(prompt, user_block)
        except Exception as exc:  # transport failure -> recorded, not hidden
            raw = f"__ERROR__ {type(exc).__name__}: {exc}"
        if sleep_s:
            time.sleep(sleep_s)
        transport_error = raw.startswith("__ERROR__") if raw else True
        candidates: list[dict] = []
        n_coerced = 0
        if not transport_error:
            parsed = candidates_from_raw(raw)
            # deterministic numeric coercion (identical for every arm) so that a
            # printed value such as "9.61·10−15" is not dropped by the schema
            # validator before it can be scored
            coerced, n_coerced = coerce_candidates(parsed)
            candidates = [
                c
                for c in coerced
                if isinstance(c.get("value"), (int, float))
                and not isinstance(c.get("value"), bool)
            ]
        row = score_item(item, candidates, abstained=not candidates)
        row["transport_error"] = transport_error
        row["n_coerced"] = n_coerced
        row["evidence_chars"] = len(evidence)
        rows.append(row)
        raw_rows.append(
            {
                "item_id": item.item_id,
                "mode": mode,
                "repeat": repeat,
                "raw": raw,
                "evidence": evidence,
            }
        )
        tag = ("ERROR" if transport_error else ("abstain" if not candidates else f"{len(candidates)} cand"))
        print(f"  [{mode} r{repeat}] {idx}/{len(items)} {item.item_id}: {tag} "
              f"({time.monotonic() - t0:.0f}s)", flush=True)
    return {"mode": mode, "repeat": repeat, "rows": rows, "raw": raw_rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=["compact", "expanded", "v25"])
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--items", default=str(FIXTURE))
    ap.add_argument("--out", default=str(PUBLIC_RESULTS))
    ap.add_argument("--force", action="store_true", help="re-run arms whose raw file exists")
    ap.add_argument(
        "--sleep",
        type=float,
        default=4.0,
        help="seconds between model calls (free-tier rate limits)",
    )
    args = ap.parse_args()

    items = load_items(args.items)
    store = DocumentStore(STORE_DIR)
    inner = OpenAICompatibleClient()
    client = RobustLLMClient(inner, attempts=6, backoff_s=10.0)
    extractor = {
        "model": inner.model,
        "base_url": inner.base_url,
        "note": (
            "The extractor is held identical across evidence modes, so the arms are "
            "comparable with each other. Absolute numbers are NOT comparable with the "
            "v0.1/v3 results, which used a different (cloud) model."
        ),
    }
    print(f"private v4 fixture: {len(items)} items", flush=True)
    print(f"extractor: {extractor['model']} @ {extractor['base_url']}", flush=True)

    PRIVATE_RESULTS.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    summaries = {}
    for mode in args.modes:
        for repeat in range(args.repeats):
            tag = f"{mode}_r{repeat}"
            if not args.force and (PRIVATE_RESULTS / f"raw_{tag}.jsonl").exists():
                print(f"  [{tag}] raw file exists - skipping (use --force to re-run)", flush=True)
                rows = json.loads((PRIVATE_RESULTS / f"rows_{tag}.json").read_text())
                summaries[tag] = aggregate(rows)
                print(f"--- {tag}: {json.dumps(summaries[tag]['all'], sort_keys=True)}", flush=True)
                continue
            report = run_mode(items, store, mode, client, repeat, args.sleep)
            tag = f"{mode}_r{repeat}"
            (PRIVATE_RESULTS / f"rows_{tag}.json").write_text(
                json.dumps(report["rows"], indent=2, sort_keys=True)
            )
            (PRIVATE_RESULTS / f"raw_{tag}.jsonl").write_text(
                "\n".join(json.dumps(r, sort_keys=True) for r in report["raw"]) + "\n"
            )
            agg = aggregate(report["rows"])
            summaries[tag] = agg
            print(f"--- {tag}: {json.dumps(agg['all'], sort_keys=True)}", flush=True)

    # public aggregate only (no per-item detail: the fixture is private)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "extractor": extractor,
        "fixture": "PRIVATE v4 (30 items; fixture not published)",
        "n_items": len(items),
        "categories": {
            c: sum(1 for i in items if i.category == c)
            for c in sorted({i.category for i in items})
        },
        "repeats": args.repeats,
        "modes": args.modes,
        "summary": summaries,
        "note": (
            "Condition-field accuracy counts a gold 'not_stated' field as matched "
            "only when the extraction reports nothing there; invented conditions are "
            "always penalised. Per-item results stay private."
        ),
    }
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True))

    lines = [
        "# V2.5 — private v4 condition benchmark",
        "",
        f"extractor: `{extractor['model']}` @ `{extractor['base_url']}` "
        "(identical across arms; not comparable with the v0.1/v3 numbers, which "
        "used a different model)",
        "",
        f"{len(items)} items (PRIVATE fixture, not published), categories: "
        + ", ".join(f"{k}={v}" for k, v in payload["categories"].items()),
        "",
        "| metric | " + " | ".join(summaries) + " |",
        "|---|" + "---|" * len(summaries),
    ]
    for metric in ("condition_field_accuracy", "parameter_value_accuracy",
                   "parameter_unit_accuracy", "invented_condition_rate",
                   "abstention_rate"):
        row = [metric]
        for tag in summaries:
            v = summaries[tag]["all"].get(metric, float("nan"))
            row.append("n/a" if v != v else f"{v:.3f}")
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "",
        "Per-field accuracy:",
        "",
        "| field | " + " | ".join(summaries) + " |",
        "|---|" + "---|" * len(summaries),
    ]
    for fname in ("chemistry", "cell", "format", "temperature_k", "soc", "method", "protocol"):
        row = [fname]
        for tag in summaries:
            v = summaries[tag]["all"].get("per_field_accuracy", {}).get(fname, float("nan"))
            row.append("n/a" if v != v else f"{v:.3f}")
        lines.append("| " + " | ".join(row) + " |")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {out_dir}/summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
