"""P3 literature-extraction benchmark runner (Part H).

Usage:
    .venv-ecosystem312/bin/python benchmarks/p3/run_extraction_benchmark.py \
        [--provider offline|llm] [--out results/p3] [--live] [--overwrite] \
        [--replay]

- provider=offline (default): deterministic non-LLM baseline (CI-safe).
- provider=llm: general-purpose LLM + retrieval baseline via the
  OpenAI-compatible endpoint. Requires ``--live`` as well as
  PYCL_LLM_API_KEY / PYCL_LLM_MODEL.
- --replay: re-score frozen raw model outputs from a previous live run; no
  network call and no API key are used.

Scores the 7 metrics of docs/EXTRACTION_METHODOLOGY.md on the expert-
reviewed fixture data/eval/extraction_benchmark_v1.jsonl. No fine-tuning.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.eval.benchmark import (  # noqa: E402
    load_items,
    rescore_benchmark,
    run_benchmark,
)
from pybamm_closed_loop.eval.run_guard import (  # noqa: E402
    LiveRunPolicy,
    add_live_guard_args,
    client_for_live_run,
    find_raw,
from pybamm_closed_loop.eval.benchmark import load_items, run_benchmark  # noqa: E402
from pybamm_closed_loop.literature.availability import (  # noqa: E402
    ARTICLE_MISSING_REASON,
    article_source_text_available,
)
from pybamm_closed_loop.literature.extraction import (  # noqa: E402
    OfflineDeterministicExtractor,
    OpenAICompatibleClient,
)
from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402

DOC_ID = "chen2020_jes_167_080534"
RAW_TEXT = (
    REPO_ROOT
    / "data/raw_documents/chen2020_jes_167_080534/chen2020_jes_167_080534_fulltext.txt"
)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["offline", "llm"], default="offline")
    ap.add_argument("--out", default="results/p3")
    ap.add_argument("--items", default="data/eval/extraction_benchmark_v1.jsonl")
    args = ap.parse_args()
    if not article_source_text_available():
        raise SystemExit(f"SKIP P3 benchmark: {ARTICLE_MISSING_REASON}")


def _write_report(out_dir: Path, report: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    lines = [
        f"# Extraction benchmark v1 ({report['provider']})",
        "",
        "| metric | value |",
        "|---|---|",
    ]
    for k, v in report["metrics"].items():
        lines.append(f"| {k} | {v:.3f} |")
    lines += ["", "## Per item", ""]
    for it in report["per_item"]:
        lines.append(
            f"- {it['item_id']}: extracted={it['n_extracted']} "
            f"identified={it['identified']}/{it['gold']} "
            f"value_ok={it['value_ok']} abstained={it['abstained']}"
        )
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(report["metrics"], indent=2))
    print(f"wrote {out_dir}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["offline", "llm"], default="offline")
    ap.add_argument("--out", default="results/p3")
    ap.add_argument("--items", default="data/eval/extraction_benchmark_v1.jsonl")
    add_live_guard_args(ap)
    args = ap.parse_args()

    policy = LiveRunPolicy(live=args.live, overwrite=args.overwrite)
    raw_dir = REPO_ROOT / args.out
    raw_name = "raw_outputs_llm.jsonl"
    provider = "replay" if args.replay else args.provider
    out_dir = raw_dir / f"extraction_benchmark_v1_{provider}"

    if args.replay:
        raw_path = find_raw(raw_dir, raw_name)
        if raw_path is None:
            raise SystemExit(f"--replay needs {raw_name}; run a live arm first")
        raw_rows = [json.loads(line) for line in raw_path.read_text().splitlines() if line.strip()]
        store = DocumentStore(REPO_ROOT / "data/literature_store")
        items = load_items(REPO_ROOT / args.items)
        report = rescore_benchmark(items, store, raw_rows)
        report["run_metadata"] = {
            "replay": True,
            "rescored_from": _rel(raw_path),
            "provider": report["provider"],
        }
        _write_report(out_dir, report)
        return 0

    if args.provider == "llm":
        client = client_for_live_run(
            policy, OpenAICompatibleClient, replay=False
        )
    else:
        client = OfflineDeterministicExtractor()

    store = DocumentStore(REPO_ROOT / "data/literature_store")
    if DOC_ID not in {d.document_id for d in store.documents()}:
        store.ingest_text(
            DOC_ID,
            RAW_TEXT.read_text(),
            kind="paper",
            source_url="https://iopscience.iop.org/article/10.1149/1945-7111/ab9050",
            doi_or_url="10.1149/1945-7111/ab9050",
            title=(
                "Development of Experimental Techniques for Parameterization "
                "of Multi-scale Lithium-ion Battery Models"
            ),
            retrieved="2026-11-04",
        )
    items = load_items(REPO_ROOT / args.items)
    raw_path = policy.raw_path(raw_dir, raw_name)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w") as raw_sink:
        report = run_benchmark(items, store, client=client, raw_sink=raw_sink)
    if client is not None:
        report["run_metadata"] = policy.metadata(
            model=client.model, base_url=client.base_url
        )
        report["run_metadata"]["raw_outputs"] = _rel(raw_path)
    else:
        report["run_metadata"] = {
            "live": False,
            "provider": report["provider"],
            "raw_outputs": _rel(raw_path),
        }
    _write_report(out_dir, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
