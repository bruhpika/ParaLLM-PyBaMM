"""P5 Task 3 retrieval/knowledge ablation runner over benchmark v3.

Runs the evidence/knowledge conditions (same model, task, schema, scoring)
with repeated runs to expose run-to-run variance:

  retrieval_strict      ORACLE-LOCATED (UPPER BOUND): +/-260-char window
                        around the fixture probe; not a retrieval result
  retrieval_bm25_strict REAL RETRIEVAL: BM25 over the full document store,
                        query built from item facets (no probe/document filter)
  no_retrieval_strict   no evidence + strict prompt (must abstain)
  no_retrieval_memory   no evidence + knowledge-permitted prompt
                        (document_id="model_knowledge", quote null)

Also runs deterministic offline references (``offline`` = oracle window,
``offline_bm25`` = real retrieval) for no-API regression context.

Usage:
  PYCL_LLM_API_KEY=... PYCL_LLM_BASE_URL=... PYCL_LLM_MODEL=... \
  .venv-ecosystem312/bin/python benchmarks/p5/run_ablation.py --condition all --repeats 3 --live

Live model calls require ``--live``; raw outputs are never overwritten unless
``--overwrite`` is also given (otherwise a fresh timestamped directory is used).
``--rescore``/``--replay`` re-score frozen raw outputs with no network or key.

Outputs (results/p5/benchmark_v3/):
  raw_outputs_<condition>_r<k>.jsonl   verbatim model outputs per repeat
  report_<condition>_r<k>.json       metrics + per-item scores + metadata
  aggregate_<condition>.json         mean/std across repeats
  summary.md                         cross-condition comparison (mean +/- std)

No API key is ever written to an artifact. Existing raw files are skipped
(delete them to re-run); --rescore re-scores frozen raw output deterministically.
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

from pybamm_closed_loop.eval.run_guard import (  # noqa: E402
    LiveRunPolicy,
    add_live_guard_args,
    client_for_live_run,
    find_raw,
)
from pybamm_closed_loop.eval.benchmark_p5 import RobustLLMClient  # noqa: E402
from pybamm_closed_loop.eval.benchmark_p5 import (  # noqa: E402
    CONDITIONS,
    OFFLINE_CONDITIONS,
    aggregate_repeats,
    load_items_v3,
    rescore_from_raw,
    run_condition,
)
from pybamm_closed_loop.eval.retrieval_arms import (  # noqa: E402
    DEFAULT_RETRIEVAL_K,
    ORACLE_LABEL,
    REAL_RETRIEVAL_LABEL,
)
from pybamm_closed_loop.literature.extraction import (  # noqa: E402
    OfflineDeterministicExtractor,
    OpenAICompatibleClient,
)
from pybamm_closed_loop.literature.availability import without_supplement_items  # noqa: E402
from pybamm_closed_loop.literature.index import BM25Index  # noqa: E402
from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402

OUT_DIR = REPO_ROOT / "results/p5/benchmark_v3"
STORE_DIR = REPO_ROOT / "data/literature_store"

ALL_CONDITIONS = OFFLINE_CONDITIONS + CONDITIONS

_CONDITION_LABELS = {
    "retrieval_strict": f"{ORACLE_LABEL}: retrieval_strict",
    "retrieval_bm25_strict": f"{REAL_RETRIEVAL_LABEL}: retrieval_bm25_strict",
    "no_retrieval_strict": "no retrieval, strict prompt",
    "no_retrieval_memory": "no retrieval, memory permitted",
    "offline": f"deterministic offline ({ORACLE_LABEL})",
    "offline_bm25": f"deterministic offline ({REAL_RETRIEVAL_LABEL})",
}


def _condition_label(condition: str) -> str:
    return _CONDITION_LABELS.get(condition, condition)


def _model_from_provider(provider: str | None) -> str | None:
    """Return the real model id encoded in a provider tag, if any."""
    if not provider or provider.startswith("deterministic"):
        return None
    parts = provider.split(":", 2)
    if parts[0] == "llm":
        return parts[2] if len(parts) == 3 and parts[2] else provider
    return provider


def _model_for_report(report: dict) -> str | None:
    """Resolve the model from metadata, falling back to preserved raw outputs.

    Rescored reports predate the ``run_metadata.model`` field, so the provider
    tag recorded on each raw output is the authoritative fallback.
    """
    meta = report.get("run_metadata") or {}
    if isinstance(meta, list):
        meta = meta[0] if meta else {}
    if isinstance(meta, dict):
        if meta.get("model"):
            return str(meta["model"])
        model = _model_from_provider(meta.get("provider"))
        if model:
            return model
    for row in report.get("raw_outputs") or []:
        if isinstance(row, dict):
            model = _model_from_provider(row.get("provider"))
            if model:
                return model
    return None


def _repair_metadata(out_dir: Path) -> int:
    """Backfill provider/model into old report and aggregate metadata.

    Only metadata fields are written; metrics, per-item rows and raw outputs
    are left byte-for-byte unchanged.
    """
    repaired = 0
    for report_path in sorted(out_dir.glob("report_*_r*.json")):
        report = json.loads(report_path.read_text())
        model = _model_for_report(report)
        provider = next(
            (
                row.get("provider")
                for row in report.get("raw_outputs") or []
                if isinstance(row, dict) and row.get("provider")
            ),
            None,
        )
        meta = report.get("run_metadata")
        if not isinstance(meta, dict):
            meta = {}
        changed = False
        if model and not meta.get("model"):
            meta["model"] = model
            changed = True
        if provider and not meta.get("provider"):
            meta["provider"] = provider
            changed = True
        if changed:
            report["run_metadata"] = meta
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
            repaired += 1
    for aggregate_path in sorted(out_dir.glob("aggregate_*.json")):
        payload = json.loads(aggregate_path.read_text())
        condition = payload["condition"]
        metas = [
            json.loads(path.read_text()).get("run_metadata", {})
            for path in sorted(out_dir.glob(f"report_{condition}_r*.json"))
        ]
        if metas and payload.get("run_metadata") != metas:
            payload["run_metadata"] = metas
            aggregate_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
            repaired += 1
    return repaired


def _load_disk(out_dir: Path) -> dict[str, dict]:
    """Load aggregates and backfill the model from per-repeat reports.

    Older rescored aggregates carry an empty ``run_metadata.model``; the raw
    outputs inside the reports still record the real provider/model.
    """
    disk: dict[str, dict] = {}
    for path in sorted(out_dir.glob("aggregate_*.json")):
        payload = json.loads(path.read_text())
        condition = payload["condition"]
        if _model_for_report(payload) is None:
            for report_path in sorted(out_dir.glob(f"report_{condition}_r*.json")):
                model = _model_for_report(json.loads(report_path.read_text()))
                if model:
                    meta = payload.get("run_metadata")
                    if isinstance(meta, list) and meta:
                        for entry in meta:
                            if isinstance(entry, dict):
                                entry.setdefault("model", model)
                    else:
                        payload["run_metadata"] = {"model": model}
                    break
        disk[condition] = payload
    return disk


def _write_summary(disk: dict[str, dict], items_path: str, repeats: int) -> None:
    lines = [
        "# P5 benchmark v3 - retrieval/knowledge ablation",
        "",
        f"items: `{items_path}`; repeats per condition (LLM): {repeats}; "
        f"generated {datetime.now(timezone.utc).isoformat()}",
        "",
        "Means +/- population std over repeats. v3 only (P4 not mixed).",
        "",
        f"- {ORACLE_LABEL}: evidence located from the fixture probe.",
        f"- {REAL_RETRIEVAL_LABEL}: query built from item facets only; BM25 over "
        "the complete document store; no probe, target-document filter or gold "
        "condition is used.",
        "",
    ]
    labels = {cond: _condition_label(cond) for cond in disk}
    for cond, r in disk.items():
        meta = r.get("run_metadata") or {}
        if isinstance(meta, list):
            meta = meta[0] if meta else {}
        model = meta.get("model") or _model_for_report(r)
        base_url = meta.get("base_url") or meta.get("endpoint_host")
        date = meta.get("date") or meta.get("timestamp")
        repeats_for_cond = r.get("repeats", "?")
        lines.append(
            f"- {labels[cond]}: model={model or 'deterministic (no LLM)'} "
            f"repeats={repeats_for_cond} base_url={base_url or 'n/a'} "
            f"date={date or 'n/a'}"
        )
    lines += ["", "## all items (mean +/- std over repeats)", ""]
    header = "| metric | " + " | ".join(labels[c] for c in disk) + " |"
    lines += [header, "|---|" + "---|" * len(disk)]
    for metric in disk[next(iter(disk))]["aggregate"]["all"]:
        row = [metric]
        for cond in disk:
            cell = disk[cond]["aggregate"]["all"][metric]
            if cell["mean"] is None:
                row.append("n/a")
            else:
                row.append(f"{cell['mean']:.3f} +/- {cell['std']:.3f}")
        lines.append("| " + " | ".join(row) + " |")

    for scope in ("eval", "dev"):
        present = [c for c in disk if scope in disk[c]["aggregate"]]
        if not present:
            continue
        lines += [
            "",
            f"## {scope} split (mean +/- std)",
            "",
            "| metric | " + " | ".join(labels[c] for c in present) + " |",
            "|---|" + "---|" * len(present),
        ]
        for metric in disk[present[0]]["aggregate"][scope]:
            row = [metric]
            for cond in present:
                cell = disk[cond]["aggregate"][scope][metric]
                row.append(
                    "n/a"
                    if cell["mean"] is None
                    else f"{cell['mean']:.3f} +/- {cell['std']:.3f}"
                )
            lines.append("| " + " | ".join(row) + " |")

    lines += ["", "## T4 provenance diagnostics (mean)", ""]
    keys = list(disk[next(iter(disk))]["aggregate"]["provenance"])
    lines += [
        "| check | " + " | ".join(labels[c] for c in disk) + " |",
        "|---|" + "---|" * len(disk),
    ]
    for key in keys:
        row = [key]
        for cond in disk:
            v = disk[cond]["aggregate"]["provenance"][key]
            row.append("n/a" if v is None or v != v else f"{v:.3f}")
        lines.append("| " + " | ".join(row) + " |")
    (OUT_DIR / "summary.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT_DIR / 'summary.md'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--condition",
        choices=list(ALL_CONDITIONS) + ["all"],
        default="all",
    )
    ap.add_argument("--items", default="data/eval/extraction_benchmark_v3.jsonl")
    ap.add_argument("--split", choices=["dev", "eval", "all"], default="all")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument(
        "--evidence-mode",
        choices=["compact", "expanded"],
        default="compact",
        help=(
            "compact = v0.1 +/-260-char window (the frozen v3 results); "
            "expanded = V2.5 condition-aware window + document-level conditions"
        ),
    )
    ap.add_argument(
        "--rescore",
        action="store_true",
        help="re-score frozen raw outputs instead of calling the model again; "
        "no network/API key is used",
    )
    ap.add_argument(
        "--retrieval-k",
        type=int,
        default=DEFAULT_RETRIEVAL_K,
        help="number of BM25 segments shown to the extractor (real-retrieval arms)",
    )
    ap.add_argument(
        "--summary-only",
        action="store_true",
        help="rebuild summary.md from existing aggregate_*.json (no model calls, "
        "no re-scoring)",
    )
    ap.add_argument(
        "--repair-metadata",
        action="store_true",
        help="backfill model/provider into old report/aggregate metadata from the "
        "preserved raw outputs (no model calls, no re-scoring)",
    )
    add_live_guard_args(ap)
    args = ap.parse_args()

    policy = LiveRunPolicy(live=args.live, overwrite=args.overwrite)
    replay = args.rescore or args.replay

    if args.repair_metadata:
        n = _repair_metadata(OUT_DIR)
        print(f"repaired metadata in {n} file(s)")
        return 0

    if args.summary_only:
        disk = _load_disk(OUT_DIR)
        if disk:
            _write_summary(disk, args.items, args.repeats)
        return 0

    store = DocumentStore(STORE_DIR)
    items = without_supplement_items(
        load_items_v3(REPO_ROOT / args.items), STORE_DIR
    )
    if args.split != "all":
        items = [it for it in items if it.split == args.split]

    conditions = list(ALL_CONDITIONS) if args.condition == "all" else [args.condition]
    needs_llm = any(c not in OFFLINE_CONDITIONS for c in conditions) and not replay
    if needs_llm:
        policy.ensure_allowed()
    llm_client = (
        client_for_live_run(policy, OpenAICompatibleClient, replay=False)
        if needs_llm
        else None
    )
    retrieval_index = (
        BM25Index(store.segments())
        if any(c in ("retrieval_bm25_strict", "offline_bm25") for c in conditions)
        else None
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for condition in conditions:
        repeats = 1 if condition in OFFLINE_CONDITIONS else args.repeats
        reports: list[dict] = []
        for repeat in range(repeats):
            raw_name = (
                f"raw_outputs_{condition}.jsonl"
                if condition in OFFLINE_CONDITIONS
                else f"raw_outputs_{condition}_r{repeat}.jsonl"
            )
            raw_path = OUT_DIR / raw_name

            if replay and condition not in OFFLINE_CONDITIONS:
                frozen = find_raw(OUT_DIR, raw_name)
                if frozen is None:
                    raise SystemExit(f"--replay needs {raw_name}")
                raw_rows = [
                    json.loads(line)
                    for line in frozen.read_text().splitlines()
                    if line.strip()
                ]
                report = rescore_from_raw(items, store, raw_rows, condition, repeat)
                report_path = OUT_DIR / f"report_{condition}_r{repeat}.json"
                prev_meta: dict = {}
                if report_path.exists():
                    prev_meta = json.loads(report_path.read_text()).get(
                        "run_metadata"
                    ) or {}
                now = datetime.now(timezone.utc).isoformat()
                providers = {
                    row.get("provider") for row in raw_rows if row.get("provider")
                }
                provider = (
                    providers.pop()
                    if len(providers) == 1
                    else next(iter(providers), prev_meta.get("provider"))
                )
                report["run_metadata"] = dict(
                    condition=condition,
                    repeat=repeat,
                    timestamp=prev_meta.get("timestamp", now),
                    date=prev_meta.get("date", now[:10]),
                    provider=provider,
                    model=prev_meta.get("model") or _model_from_provider(provider),
                    base_url=prev_meta.get("base_url")
                    or prev_meta.get("endpoint_host"),
                    items_file=args.items,
                    split=args.split,
                    n_items=len(items),
                    evidence_source=report.get("evidence_source")
                    or next(
                        (
                            row.get("evidence_source")
                            for row in raw_rows
                            if row.get("evidence_source")
                        ),
                        "retrieval"
                        if condition == "retrieval_bm25_strict"
                        else "oracle",
                    ),
                    retrieval_k=(
                        args.retrieval_k
                        if condition == "retrieval_bm25_strict"
                        else None
                    ),
                    rescored=True,
                    rescored_from=str(frozen.relative_to(REPO_ROOT)),
                )
            else:
                if condition in OFFLINE_CONDITIONS and raw_path.exists():
                    raw_path.unlink()
                elif condition not in OFFLINE_CONDITIONS and raw_path.exists():
                    # live runs never clobber frozen raw outputs without --overwrite
                    raw_path = policy.raw_path(OUT_DIR, raw_name)
                    raw_path.parent.mkdir(parents=True, exist_ok=True)
                if condition in OFFLINE_CONDITIONS:
                    client = OfflineDeterministicExtractor()
                else:
                    client = RobustLLMClient(llm_client)

                print(
                    f"=== condition {condition} repeat {repeat + 1}/{repeats} "
                    f"({len(items)} items) ===",
                    flush=True,
                )
                t0 = time.monotonic()
                with raw_path.open("w") as raw_sink:

                    def progress(idx, item_id, n_cands, abstained, raw_content=None):
                        tag = "abstain" if abstained else f"{n_cands} cand"
                        print(
                            f"  [{condition} r{repeat}] {idx + 1}/{len(items)} "
                            f"{item_id}: {tag} ({time.monotonic() - t0:.0f}s)",
                            flush=True,
                        )

                    report = run_condition(
                        items,
                        store,
                        condition=condition,
                        client=client,
                        raw_sink=raw_sink,
                        repeat_index=repeat,
                        on_progress=progress,
                        evidence_mode=args.evidence_mode,
                        index=retrieval_index,
                        retrieval_k=args.retrieval_k,
                    )
                now = datetime.now(timezone.utc).isoformat()
                report["run_metadata"] = dict(
                    condition=condition,
                    repeat=repeat,
                    timestamp=now,
                    date=now[:10],
                    provider=getattr(client, "name", condition),
                    base_url=(llm_client.base_url if llm_client else None),
                    endpoint_host=(llm_client.base_url if llm_client else None),
                    model=(llm_client.model if llm_client else None),
                    items_file=args.items,
                    split=args.split,
                    n_items=len(items),
                    raw_outputs=str(raw_path.relative_to(REPO_ROOT)),
                    temperature=0,
                    evidence_mode=args.evidence_mode,
                    evidence_source=report.get("evidence_source"),
                    retrieval_k=(
                        args.retrieval_k
                        if report.get("evidence_source") == "retrieval"
                        else None
                    ),
                    **(
                        policy.metadata(
                            model=llm_client.model, base_url=llm_client.base_url
                        )
                        if llm_client
                        else {}
                    ),
                )
            (OUT_DIR / f"report_{condition}_r{repeat}.json").write_text(
                json.dumps(report, indent=2, sort_keys=True)
            )
            print(json.dumps(report["metrics"]["all"], indent=2), flush=True)
            reports.append(report)

        aggregate = aggregate_repeats(reports)
        (OUT_DIR / f"aggregate_{condition}.json").write_text(
            json.dumps(
                dict(
                    condition=condition,
                    repeats=len(reports),
                    aggregate=aggregate,
                    run_metadata=[r.get("run_metadata", {}) for r in reports],
                ),
                indent=2,
                sort_keys=True,
            )
        )

    disk = _load_disk(OUT_DIR)
    if disk:
        _write_summary(disk, args.items, args.repeats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
