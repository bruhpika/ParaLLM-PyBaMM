"""Run the PRIVATE v4 condition benchmark (V2.5 exit criterion).

Compares the evidence arms on the same private fixture:

  compact    ORACLE-LOCATED (probe window; NOT a performance upper bound):
             +/-260-character window around probe
  expanded   ORACLE-LOCATED: condition-aware window + document-level setup
  v25        ORACLE-LOCATED: expanded + table-aware chunking + top-k multi-window
  retrieval  REAL RETRIEVAL: BM25 over the full store, query from parameter
             name/unit only (no probe, target document or gold conditions)

The first three arms search for the fixture's hand-written probe; they are
location oracles, not performance upper bounds, and are labelled as such in
every output. Only ``retrieval`` is a retrieval result.

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
        --modes compact expanded v25 --repeats 1 --live

Live model calls require ``--live``; raw outputs are never overwritten unless
``--overwrite`` is given (``--force`` remains an alias), otherwise a fresh
timestamped directory is used. ``--rescore``/``--replay`` re-score frozen raw
outputs with no network or API key.
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
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.eval.run_guard import (  # noqa: E402
    LiveRunPolicy,
    add_live_guard_args,
    client_for_live_run,
    find_raw,
    git_commit,
)
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
    TUNED_RETRIEVAL_LABEL,
    retrieval_context_for_item,
    tuned_index,
)
from pybamm_closed_loop.literature.extraction import (  # noqa: E402
    OfflineDeterministicExtractor,
    OpenAICompatibleClient,
    run_extraction,
)
from pybamm_closed_loop.literature.index import BM25Index  # noqa: E402
from pybamm_closed_loop.literature.ingest import DocumentStore, Segment  # noqa: E402

PRIVATE_ROOT = REPO_ROOT / "data/private_v4"
FIXTURE = PRIVATE_ROOT / "fixture/benchmark_v4.jsonl"
STORE_DIR = PRIVATE_ROOT / "store"
PRIVATE_RESULTS = PRIVATE_ROOT / "results"
PUBLIC_RESULTS = REPO_ROOT / "results/v2/v4"

ORACLE_MODES = ("compact", "expanded", "v25")
RETRIEVAL_MODE = "retrieval"
OFFLINE_TUNED_MODE = "offline_bm25_tuned"
RETRIEVAL_TUNED_MODE = "retrieval_tuned"


def _is_offline_mode(mode: str) -> bool:
    return mode == OFFLINE_TUNED_MODE


def _is_tuned_retrieval_mode(mode: str) -> bool:
    return mode == RETRIEVAL_TUNED_MODE


def _is_retrieval_mode(mode: str) -> bool:
    return mode in (
        RETRIEVAL_MODE,
        "real_retrieval",
        "bm25",
        OFFLINE_TUNED_MODE,
        RETRIEVAL_TUNED_MODE,
    )


def _arm_label(mode: str) -> str:
    if _is_offline_mode(mode):
        return f"deterministic offline ({TUNED_RETRIEVAL_LABEL})"
    if _is_tuned_retrieval_mode(mode):
        return f"{TUNED_RETRIEVAL_LABEL}: {mode}"
    if _is_retrieval_mode(mode):
        return f"{REAL_RETRIEVAL_LABEL}: {mode}"
    return f"{ORACLE_LABEL}: {mode}"


def _tag_label(tag: str) -> str:
    mode = tag.rsplit("_r", 1)[0]
    return f"{_arm_label(mode)} ({tag.rsplit('_r', 1)[-1]})"


def _prompt_suffix(prompt_version: str) -> str:
    """Filename suffix for non-default prompts; v25 stays byte-compatible."""
    return "" if prompt_version == "v25" else f"_{prompt_version}"


def run_mode(
    items,
    store,
    mode: str,
    client,
    repeat: int,
    sleep_s: float = 0.0,
    *,
    index: BM25Index | None = None,
    tuned: BM25Index | None = None,
    retrieval_k: int = DEFAULT_RETRIEVAL_K,
    offline_extract: bool = False,
    discipline: str = "trace",
    prompt_version: str = "v25",
) -> dict:
    prompt = build_v4_prompt(prompt_version)
    rows = []
    raw_rows = []
    retrieval_audits = []
    t0 = time.monotonic()
    for idx, item in enumerate(items, start=1):
        retrieval_audit = None
        context = None
        if _is_retrieval_mode(mode):
            context = retrieval_context_for_item(
                item,
                store,
                k=retrieval_k,
                index=tuned
                if (_is_offline_mode(mode) or _is_tuned_retrieval_mode(mode))
                else index,
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
        if offline_extract and context is None:
            context = SimpleNamespace(
                facets={"parameter_names": [str(item.parameter.get("name") or "")]},
                segments=[
                    Segment(
                        segment_id=f"{item.item_id}#oracle-passage",
                        document_id=item.document_id,
                        char_start=0,
                        char_end=len(evidence),
                        page=None,
                        heading=None,
                        text=evidence,
                    )
                ]
            )
        if offline_extract:
            batch = run_extraction(
                OfflineDeterministicExtractor(),
                context,
            )
            raw = json.dumps([c.payload for c in batch.valid()])
        else:
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
        # verification pass + deterministic discipline (shared with the
        # offline re-score path so both apply the identical rules)
        row = score_with_discipline(
            item, evidence, candidates, transport_error, n_coerced,
            discipline=discipline,
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
        "prompt_version": prompt_version,
        "evidence_source": (
            "retrieval" if _is_retrieval_mode(mode) else "oracle"
        ),
        "retrieval_audits": retrieval_audits,
        "rows": rows,
        "raw": raw_rows,
    }


def rescore_from_raw(
    items, mode: str, repeat: int, raw_path: Path, *, discipline: str = "trace"
) -> list[dict]:
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
            score_with_discipline(
                item, evidence, candidates, transport_error, n_coerced,
                discipline=discipline,
            )
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
        "discipline": getattr(args, "discipline", "trace"),
        "prompt_version": getattr(args, "prompt_version", "v25"),
        "split": getattr(args, "split", "all"),
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
            f"{ORACLE_LABEL}: the evidence is located from the fixture probe; it "
            "is a location oracle, not a retrieval result and not a performance "
            "upper bound. "
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
        f"discipline: `{payload['discipline']}` (split: {payload['split']}); "
        f"prompt: `{payload['prompt_version']}`; "
        "deterministic post-extraction rules, identical for every arm.",
        "",
        f"- {ORACLE_LABEL}: compact/expanded/v25 locate evidence from the probe; "
        "location oracle, not retrieval and not a performance upper bound.",
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
    if payload.get("discipline") == "association":
        lines += [
            "",
            "## Association discipline",
            "",
            "Fallback rate = share of candidates whose quote could not be located "
            "and which therefore fell back to the evidence-wide trace check "
            "(lower is better). Rule counts tally unsupported field decisions.",
            "",
            "| tag | fallback rate |",
            "|---|---|",
        ]
        for tag in summaries:
            v = summaries[tag]["all"].get("association_fallback_rate")
            shown = "n/a" if v is None or v != v else f"{v:.3f}"
            lines.append(f"| {tag} | {shown} |")
        rule_counts: dict[str, int] = {}
        for tag in summaries:
            for rule, count in (
                summaries[tag]["all"].get("association_rule_counts") or {}
            ).items():
                rule_counts[rule] = rule_counts.get(rule, 0) + count
        if rule_counts:
            lines += ["", "rule counts (unsupported field decisions):", ""]
            for rule, count in sorted(
                rule_counts.items(), key=lambda kv: (-kv[1], kv[0])
            ):
                lines.append(f"- `{rule}`: {count}")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--modes",
        nargs="+",
        default=["compact", "expanded", "v25", RETRIEVAL_MODE],
        help="evidence arms; compact/expanded/v25 are oracle-located (probe "
        "window; not performance upper bounds), retrieval is real full-store BM25",
    )
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--items", default=str(FIXTURE))
    ap.add_argument("--out", default=str(PUBLIC_RESULTS))
    ap.add_argument("--force", action="store_true", help="re-run arms whose raw file exists")
    ap.add_argument(
        "--offline-all",
        action="store_true",
        help="use the deterministic offline extractor for every requested arm",
    )
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
    ap.add_argument(
        "--discipline",
        choices=("trace", "association"),
        default="trace",
        help="deterministic post-extraction discipline: trace (default, "
        "evidence-wide condition trace) or association (value-local scope; "
        "new discipline, no model calls)",
    )
    ap.add_argument(
        "--prompt-version",
        choices=("v25", "v26"),
        default="v25",
        help="extraction prompt version: v25 (frozen, default) or v26 "
        "(v25 + one abstention-boundary clarification; same schema/scorer)",
    )
    ap.add_argument(
        "--split",
        choices=("all", "dev", "test"),
        default="all",
        help="restrict scoring to the v4 dev/test split (configs/retrieval/"
        "dev_test_split.json); default all 30 items",
    )
    ap.add_argument(
        "--private-out",
        default=None,
        help="directory for the private raw_*.jsonl and rows_*.json "
        "(default: data/private_v4/results, next to the frozen raw outputs)",
    )
    add_live_guard_args(ap)
    args = ap.parse_args()

    policy = LiveRunPolicy(live=args.live, overwrite=args.force or args.overwrite)
    replay = args.rescore or args.aggregate_only or args.replay
    offline_only = args.offline_all or (
        bool(args.modes) and all(_is_offline_mode(m) for m in args.modes)
    )
    if not replay and not offline_only:
        policy.ensure_allowed()
    if not args.offline_all and offline_only and any(
        not _is_offline_mode(m) for m in args.modes
    ):
        raise SystemExit("offline modes cannot be mixed with live modes")

    items = load_items(args.items)
    if args.split != "all":
        split_path = REPO_ROOT / "configs/retrieval/dev_test_split.json"
        split_doc = json.loads(split_path.read_text())["benchmarks"]["v4"]
        wanted = set(split_doc[args.split])
        n_before = len(items)
        items = [item for item in items if item.item_id in wanted]
        if not items:
            raise SystemExit(
                f"split {args.split!r} matched no items from {split_doc[args.split]}"
            )
        print(
            f"v4 split {args.split}: {len(items)}/{n_before} items "
            f"(seed {split_doc['seed']})",
            flush=True,
        )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_dir = Path(args.private_out) if args.private_out else PRIVATE_RESULTS
    rows_dir.mkdir(parents=True, exist_ok=True)
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
        "git_commit": git_commit(REPO_ROOT) if not replay else None,
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
        extractor["git_commit"] = prev_ext.get("git_commit", extractor["git_commit"])
    print(f"private v4 fixture: {len(items)} items", flush=True)

    summaries = {}
    arm_means: dict[str, dict] = {}
    if args.rescore or args.replay:
        for mode in args.modes:
            tags = []
            for repeat in range(args.repeats):
                tag = f"{mode}_r{repeat}"
                raw_path = find_raw(
                    rows_dir,
                    f"raw_{tag}{_prompt_suffix(args.prompt_version)}.jsonl",
                )
                if raw_path is None:
                    print(f"  [{tag}] raw file missing - skipped", flush=True)
                    continue
                rows = rescore_from_raw(
                    items, mode, repeat, raw_path, discipline=args.discipline
                )
                rows_name = f"rows_{tag}{_prompt_suffix(args.prompt_version)}.json"
                (rows_dir / rows_name).write_text(
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
                rows_path = find_raw(
                    rows_dir,
                    f"rows_{tag}{_prompt_suffix(args.prompt_version)}.json",
                )
                if rows_path is None:
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
    retrieval_index = (
        BM25Index(store.segments())
        if any(_is_retrieval_mode(mode) for mode in args.modes)
        else None
    )
    tuned_retrieval_index = (
        tuned_index(retrieval_index)
        if any(
            _is_offline_mode(mode) or _is_tuned_retrieval_mode(mode)
            for mode in args.modes
        )
        else None
    )
    if offline_only:
        client = OfflineDeterministicExtractor()
        extractor = {
            "model": "deterministic (no LLM)",
            "base_url": None,
            "date": datetime.now(timezone.utc).date().isoformat(),
            "git_commit": git_commit(REPO_ROOT),
            "note": extractor["note"],
        }
    else:
        inner = client_for_live_run(policy, OpenAICompatibleClient, replay=False)
        client = RobustLLMClient(inner, attempts=6, backoff_s=10.0)
        live_meta = policy.metadata(model=inner.model, base_url=inner.base_url)
        extractor = {
            "model": live_meta["model"],
            "base_url": live_meta["base_url"],
            "date": live_meta["date"],
            "git_commit": live_meta["git_commit"],
            "note": extractor["note"],
        }
    print(f"extractor: {extractor['model']} @ {extractor['base_url']}", flush=True)

    for mode in args.modes:
        for repeat in range(args.repeats):
            tag = f"{mode}_r{repeat}"
            suffix = _prompt_suffix(args.prompt_version)
            raw_name = f"raw_{'offline_' if args.offline_all else ''}{tag}{suffix}.jsonl"
            raw_path = policy.raw_path(rows_dir, raw_name)
            rows_name = f"rows_{'offline_' if args.offline_all else ''}{tag}{suffix}.json"
            rows_path = raw_path.with_name(rows_name)
            if raw_path.parent != rows_dir:
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                print(
                    f"  [{tag}] raw file exists - writing to {raw_path.parent.name}/",
                    flush=True,
                )
            report = run_mode(
                items,
                store,
                mode,
                client,
                repeat,
                args.sleep,
                index=retrieval_index,
                tuned=tuned_retrieval_index,
                retrieval_k=args.retrieval_k,
                offline_extract=offline_only,
                discipline=args.discipline,
                prompt_version=args.prompt_version,
            )
            raw_path.write_text(
                "\n".join(json.dumps(r, sort_keys=True) for r in report["raw"]) + "\n"
            )
            rows_path.write_text(json.dumps(report["rows"], indent=2, sort_keys=True))
            agg = aggregate(report["rows"])
            summaries[tag] = agg
            print(f"--- {tag}: {json.dumps(agg['all'], sort_keys=True)}", flush=True)

    # public aggregate only (no per-item detail: the fixture is private)
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "extractor": extractor,
        "fixture": "PRIVATE v4 (30 items; fixture not published)",
        "n_items": len(items),
        "discipline": args.discipline,
        "prompt_version": args.prompt_version,
        "split": args.split,
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
        f"discipline: `{payload['discipline']}` (split: {payload['split']}); "
        f"prompt: `{payload['prompt_version']}`",
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
