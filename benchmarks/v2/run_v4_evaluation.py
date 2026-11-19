"""Run the PRIVATE v4 condition benchmark (V2.5 exit criterion).

Compares the evidence arms on the same private fixture:

  compact    ORACLE-LOCATED (UPPER BOUND): +/-260-character window around probe
  expanded   ORACLE-LOCATED: condition-aware window + document-level setup
  v25        ORACLE-LOCATED: expanded + table-aware chunking + top-k multi-window
  retrieval  REAL RETRIEVAL: BM25 over the full store, query from parameter
             name/unit only (no probe, target document or gold conditions)

The first three arms search for the fixture's hand-written probe; they are an
upper bound and are labelled as such in every output. Only ``retrieval`` is a
retrieval result.

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
import os
import statistics
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
    score_with_discipline,
)
from pybamm_closed_loop.eval.benchmark_p5 import (  # noqa: E402
    candidates_from_raw,
)
from pybamm_closed_loop.eval.retrieval_arms import (  # noqa: E402
    DEFAULT_RETRIEVAL_K,
    ORACLE_LABEL,
    REAL_RETRIEVAL_LABEL,
    retrieval_context_for_item,
)
from pybamm_closed_loop.literature.extraction import (  # noqa: E402
    OpenAICompatibleClient,
)
from pybamm_closed_loop.literature.index import BM25Index  # noqa: E402
from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402

PRIVATE_ROOT = REPO_ROOT / "data/private_v4"
FIXTURE = PRIVATE_ROOT / "fixture/benchmark_v4.jsonl"
STORE_DIR = PRIVATE_ROOT / "store"
PRIVATE_RESULTS = PRIVATE_ROOT / "results"
PUBLIC_RESULTS = REPO_ROOT / "results/v2/v4"

ORACLE_MODES = ("compact", "expanded", "v25")
RETRIEVAL_MODE = "retrieval"


def _is_retrieval_mode(mode: str) -> bool:
    return mode in (RETRIEVAL_MODE, "real_retrieval", "bm25")


def _arm_label(mode: str) -> str:
    if _is_retrieval_mode(mode):
        return f"{REAL_RETRIEVAL_LABEL}: {mode}"
    return f"{ORACLE_LABEL}: {mode}"


def _tag_label(tag: str) -> str:
    mode = tag.rsplit("_r", 1)[0]
    return f"{_arm_label(mode)} ({tag.rsplit('_r', 1)[-1]})"


def run_mode(
    items,
    store,
    mode: str,
    client,
    repeat: int,
    sleep_s: float = 0.0,
    *,
    index: BM25Index | None = None,
    retrieval_k: int = DEFAULT_RETRIEVAL_K,
) -> dict:
    prompt = build_v4_prompt()
    rows = []
    raw_rows = []
    retrieval_audits = []
    t0 = time.monotonic()
    for idx, item in enumerate(items, start=1):
        retrieval_audit = None
        if _is_retrieval_mode(mode):
            context = retrieval_context_for_item(
                item, store, k=retrieval_k, index=index
            )
            evidence = context.to_evidence_block()
            retrieval_audit = {
                "item_id": item.item_id,
                "query": context.query,
                "retrieved_segment_ids": [
                    segment.segment_id for segment in context.segments
                ],
                "retrieved_documents": list(context.retrieved_from),
                "n_segments": len(context.segments),
            }
            retrieval_audits.append(retrieval_audit)
        else:
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
        # verification pass + deterministic `not_stated` discipline (shared
        # with the offline re-score path so both arms apply the same rules)
        row = score_with_discipline(
            item, evidence, candidates, transport_error, n_coerced
        )
        rows.append(row)
        raw_rows.append(
            {
                "item_id": item.item_id,
                "mode": mode,
                "repeat": repeat,
                "raw": raw,
                "evidence": evidence,
                "evidence_source": (
                    "retrieval" if _is_retrieval_mode(mode) else "oracle"
                ),
                "retrieval": retrieval_audit,
            }
        )
        tag = ("ERROR" if transport_error else ("abstain" if not candidates else f"{len(candidates)} cand"))
        print(f"  [{mode} r{repeat}] {idx}/{len(items)} {item.item_id}: {tag} "
              f"({time.monotonic() - t0:.0f}s)", flush=True)
    return {
        "mode": mode,
        "repeat": repeat,
        "evidence_source": (
            "retrieval" if _is_retrieval_mode(mode) else "oracle"
        ),
        "retrieval_audits": retrieval_audits,
        "rows": rows,
        "raw": raw_rows,
    }


def rescore_from_raw(items, mode: str, repeat: int, raw_path: Path) -> list[dict]:
    """Re-score preserved raw outputs with the discipline pass — no model calls.

    The raw file stores {item_id, raw, evidence}; evidence is reused verbatim
    so the deterministic verification + `not_stated` rules see exactly what the
    model saw. Chemistry gold labels come from the *current* fixture.
    """
    raw_rows = [json.loads(line) for line in raw_path.read_text().splitlines() if line.strip()]
    by_item = {r["item_id"]: r for r in raw_rows}
    rows: list[dict] = []
    for item in items:
        rec = by_item.get(item.item_id)
        if rec is None:
            raise SystemExit(f"raw outputs missing item {item.item_id} for {mode} r{repeat}")
        evidence = rec.get("evidence") or ""
        raw = rec.get("raw") or ""
        transport_error = raw.startswith("__ERROR__") if raw else True
        candidates: list[dict] = []
        n_coerced = 0
        if not transport_error:
            parsed = candidates_from_raw(raw)
            coerced, n_coerced = coerce_candidates(parsed)
            candidates = [
                c
                for c in coerced
                if isinstance(c.get("value"), (int, float))
                and not isinstance(c.get("value"), bool)
            ]
        rows.append(
            score_with_discipline(item, evidence, candidates, transport_error, n_coerced)
        )
    return rows


_METRICS = (
    "condition_field_accuracy",
    "parameter_value_accuracy",
    "parameter_unit_accuracy",
    "value_found_rate",
    "invented_condition_rate",
    "abstention_rate",
    "mean_dropped_conditions",
    "quote_in_evidence_rate",
    "raw_condition_field_accuracy",
    "raw_invented_condition_rate",
)


def _arm_means(arm_summaries: list[dict]) -> dict:
    """Mean/std over repeats for each metric and each condition field."""
    out: dict[str, dict[str, float | None]] = {}
    for metric in _METRICS:
        vals = [a["all"].get(metric, float("nan")) for a in arm_summaries]
        vals = [v for v in vals if v == v]
        out[metric] = {
            "mean": statistics.fmean(vals) if vals else None,
            "std": statistics.pstdev(vals) if len(vals) > 1 else (0.0 if vals else None),
            "n": len(vals),
        }
    fields: dict[str, dict[str, float | None]] = {}
    for fname in ("chemistry", "cell", "format", "temperature_k", "soc", "method", "protocol"):
        vals = [
            a["all"].get("per_field_accuracy", {}).get(fname, float("nan"))
            for a in arm_summaries
        ]
        vals = [v for v in vals if v == v]
        fields[fname] = {
            "mean": statistics.fmean(vals) if vals else None,
            "std": statistics.pstdev(vals) if len(vals) > 1 else (0.0 if vals else None),
            "n": len(vals),
        }
    out["per_field"] = fields  # type: ignore[assignment]
    out["n_transport_errors"] = sum(
        a.get("n_transport_errors", 0) for a in arm_summaries
    )
    return out


def _write_outputs(items, args, extractor, summaries, arm_means) -> None:
    """Write the public aggregate summary (no per-item detail)."""
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
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
        "arm_labels": {mode: _arm_label(mode) for mode in args.modes},
        "evidence_sources": {
            mode: ("retrieval" if _is_retrieval_mode(mode) else "oracle")
            for mode in args.modes
        },
        "retrieval_k": getattr(args, "retrieval_k", DEFAULT_RETRIEVAL_K),
        "summary": summaries,
        "arm_means": arm_means,
        "note": (
            f"{ORACLE_LABEL}: the evidence is located from the fixture probe and is "
            "an upper bound, not a retrieval result. "
            f"{REAL_RETRIEVAL_LABEL}: the query uses only parameter name/unit and "
            "BM25 searches the full store. "
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
        f"date `{extractor.get('date', 'n/a')}` "
        "(identical across arms; not comparable with the v0.1/v3 numbers, which "
        "used a different model)",
        "",
        f"{len(items)} items (PRIVATE fixture, not published), categories: "
        + ", ".join(f"{k}={v}" for k, v in payload["categories"].items()),
        "",
        f"- {ORACLE_LABEL}: compact/expanded/v25 locate evidence from the probe; "
        "upper bound, not retrieval.",
        f"- {REAL_RETRIEVAL_LABEL}: query from parameter name/unit only; full-store "
        "BM25; no probe, target document or gold condition used.",
        "",
    ]
    if arm_means:
        lines += [
            "## Arms (mean +/- std over repeats)",
            "",
            "| metric | " + " | ".join(_arm_label(m) for m in arm_means) + " |",
            "|---|" + "---|" * len(arm_means),
        ]
        for metric in _METRICS:
            row = [metric]
            for mode in arm_means:
                cell = arm_means[mode].get(metric, {})
                m, sd = cell.get("mean"), cell.get("std")
                row.append("n/a" if m is None else f"{m:.3f} +/- {sd:.3f}")
            lines.append("| " + " | ".join(row) + " |")
        lines += [
            "",
            "## Per condition field (mean +/- std over repeats)",
            "",
            "| field | " + " | ".join(_arm_label(m) for m in arm_means) + " |",
            "|---|" + "---|" * len(arm_means),
        ]
        for fname in ("chemistry", "cell", "format", "temperature_k", "soc", "method", "protocol"):
            row = [fname]
            for mode in arm_means:
                cell = arm_means[mode]["per_field"].get(fname, {})
                m, sd = cell.get("mean"), cell.get("std")
                row.append("n/a" if m is None else f"{m:.3f} +/- {sd:.3f}")
            lines.append("| " + " | ".join(row) + " |")
        lines += ["", "transport errors excluded from scoring: "
                  + ", ".join(f"{m}={arm_means[m].get('n_transport_errors')}" for m in arm_means), ""]
    lines += ["", "Per-repeat summaries:"]
    lines += [
        "",
        "| metric | " + " | ".join(_tag_label(t) for t in summaries) + " |",
        "|---|" + "---|" * len(summaries),
    ]
    for metric in _METRICS:
        row = [metric]
        for tag in summaries:
            v = summaries[tag]["all"].get(metric, float("nan"))
            row.append("n/a" if v != v else f"{v:.3f}")
        lines.append("| " + " | ".join(row) + " |")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--modes",
        nargs="+",
        default=["compact", "expanded", "v25", RETRIEVAL_MODE],
        help="evidence arms; compact/expanded/v25 are oracle-located upper bounds, "
        "retrieval is real full-store BM25",
    )
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--items", default=str(FIXTURE))
    ap.add_argument("--out", default=str(PUBLIC_RESULTS))
    ap.add_argument("--force", action="store_true", help="re-run arms whose raw file exists")
    ap.add_argument(
        "--aggregate-only",
        action="store_true",
        help="rebuild the public summary from the stored (private) per-repeat rows, "
        "without any model calls",
    )
    ap.add_argument(
        "--rescore",
        action="store_true",
        help="re-score stored raw outputs with the verification + not_stated "
        "discipline (no model calls); rewrites rows_*.json and the public summary",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=4.0,
        help="seconds between model calls (free-tier rate limits)",
    )
    ap.add_argument(
        "--retrieval-k",
        type=int,
        default=DEFAULT_RETRIEVAL_K,
        help="number of BM25 segments shown to the extractor in the retrieval arm",
    )
    args = ap.parse_args()

    items = load_items(args.items)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    PRIVATE_RESULTS.mkdir(parents=True, exist_ok=True)

    # extractor disclosure for the public summary; no model calls on
    # --rescore / --aggregate-only, so the client is only built when needed.
    # Re-score preserves the extractor recorded in the previous summary so the
    # arm stays labelled with the model that actually produced the raw outputs.
    now = datetime.now(timezone.utc).isoformat()
    extractor = {
        "model": os.environ.get("PYCL_LLM_MODEL", "unknown"),
        "base_url": os.environ.get("PYCL_LLM_BASE_URL", "unknown"),
        "date": now[:10],
        "note": (
            "The extractor is held identical across evidence modes, so the arms are "
            "comparable with each other. Absolute numbers are NOT comparable with the "
            "v0.1/v3 results, which used a different (cloud) model."
        ),
    }
    prev_summary = out_dir / "summary.json"
    if prev_summary.exists():
        try:
            prev_ext = json.loads(prev_summary.read_text()).get("extractor") or {}
        except json.JSONDecodeError:
            prev_ext = {}
        extractor["model"] = prev_ext.get("model", extractor["model"])
        extractor["base_url"] = prev_ext.get("base_url", extractor["base_url"])
        extractor["date"] = prev_ext.get("date", extractor["date"])
    print(f"private v4 fixture: {len(items)} items", flush=True)

    summaries = {}
    arm_means: dict[str, dict] = {}
    if args.rescore:
        for mode in args.modes:
            tags = []
            for repeat in range(args.repeats):
                tag = f"{mode}_r{repeat}"
                raw_path = PRIVATE_RESULTS / f"raw_{tag}.jsonl"
                if not raw_path.exists():
                    print(f"  [{tag}] raw file missing - skipped", flush=True)
                    continue
                rows = rescore_from_raw(items, mode, repeat, raw_path)
                (PRIVATE_RESULTS / f"rows_{tag}.json").write_text(
                    json.dumps(rows, indent=2, sort_keys=True)
                )
                summaries[tag] = aggregate(rows)
                tags.append(tag)
                print(
                    f"--- {tag}: {json.dumps(summaries[tag]['all'], sort_keys=True)}",
                    flush=True,
                )
            if tags:
                arm_means[mode] = _arm_means([summaries[t] for t in tags])
        _write_outputs(items, args, extractor, summaries, arm_means)
        print(f"wrote {out_dir}/summary.md (rescored with discipline)")
        return 0

    if args.aggregate_only:
        for mode in args.modes:
            tags = []
            for repeat in range(args.repeats):
                tag = f"{mode}_r{repeat}"
                rows_path = PRIVATE_RESULTS / f"rows_{tag}.json"
                if not rows_path.exists():
                    continue
                rows = json.loads(rows_path.read_text())
                summaries[tag] = aggregate(rows)
                tags.append(tag)
            if tags:
                arm_means[mode] = _arm_means([summaries[t] for t in tags])
        _write_outputs(items, args, extractor, summaries, arm_means)
        print(f"wrote {out_dir}/summary.md (aggregate-only)")
        return 0

    store = DocumentStore(STORE_DIR)
    inner = OpenAICompatibleClient()
    client = RobustLLMClient(inner, attempts=6, backoff_s=10.0)
    retrieval_index = (
        BM25Index(store.segments())
        if any(_is_retrieval_mode(mode) for mode in args.modes)
        else None
    )
    live_now = datetime.now(timezone.utc).isoformat()
    extractor = {
        "model": inner.model,
        "base_url": inner.base_url,
        "date": live_now[:10],
        "note": extractor["note"],
    }
    print(f"extractor: {extractor['model']} @ {extractor['base_url']}", flush=True)

    for mode in args.modes:
        for repeat in range(args.repeats):
            tag = f"{mode}_r{repeat}"
            if not args.force and (PRIVATE_RESULTS / f"raw_{tag}.jsonl").exists():
                print(f"  [{tag}] raw file exists - skipping (use --force to re-run)", flush=True)
                rows = json.loads((PRIVATE_RESULTS / f"rows_{tag}.json").read_text())
                summaries[tag] = aggregate(rows)
                print(f"--- {tag}: {json.dumps(summaries[tag]['all'], sort_keys=True)}", flush=True)
                continue
            report = run_mode(
                items,
                store,
                mode,
                client,
                repeat,
                args.sleep,
                index=retrieval_index,
                retrieval_k=args.retrieval_k,
            )
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
    for metric in _METRICS:
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
