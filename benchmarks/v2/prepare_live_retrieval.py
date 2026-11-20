"""Prepare (never execute) live LLM + tuned-retrieval runs.

This script has no model client and makes no network call. ``--dry-run``
builds the exact prompts offline and prints item/call/token estimates; it is
the only supported mode. Live commands are printed for the owner to approve.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.eval.benchmark_p5 import (  # noqa: E402
    build_extraction_prompt_p5,
    load_items_v3,
)
from pybamm_closed_loop.eval.benchmark_v4 import (  # noqa: E402
    build_v4_prompt,
    load_items,
)
from pybamm_closed_loop.eval.retrieval_arms import (  # noqa: E402
    retrieval_context_for_item,
    tuned_index,
)
from pybamm_closed_loop.literature.availability import (  # noqa: E402
    SUPPLEMENT_MISSING_REASON,
    article_source_text_available,
    without_article_items,
    without_supplement_items,
)
from pybamm_closed_loop.literature.index import BM25Index  # noqa: E402
from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402

V3_ITEMS = REPO_ROOT / "data/eval/extraction_benchmark_v3.jsonl"
V3_STORE = REPO_ROOT / "data/literature_store"
V4_ITEMS = REPO_ROOT / "data/private_v4/fixture/benchmark_v4.jsonl"
V4_STORE = REPO_ROOT / "data/private_v4/store"
ENV_VARS = ("PYCL_LLM_API_KEY", "PYCL_LLM_MODEL", "PYCL_LLM_BASE_URL")
CHARS_PER_TOKEN = 4  # disclosed estimate; no tokenizer weights are fetched


def _plan(benchmark: str, repeats: int, *, show_prompts: bool) -> dict[str, Any]:
    if benchmark == "v3":
        if not article_source_text_available():
            print(f"WARNING: {SUPPLEMENT_MISSING_REASON}", file=sys.stderr)
            print(
                "v3 live run requires the local Chen2020 article ingest first; "
                "see docs/BENCHMARK_RESULTS.md §5.",
                file=sys.stderr,
            )
        store = DocumentStore(V3_STORE)
        items = without_article_items(
            without_supplement_items(load_items_v3(V3_ITEMS), V3_STORE), V3_STORE
        )
        index = BM25Index(store.segments())
        system = build_extraction_prompt_p5(memory_permitted=False)
        condition = "retrieval_bm25_tuned_strict"
        command = (
            ".venv-ecosystem312/bin/python benchmarks/p5/run_ablation.py "
            f"--condition {condition} --repeats {repeats} --live"
        )
        outputs = [
            f"results/p5/benchmark_v3/raw_outputs_{condition}_r{k}.jsonl"
            for k in range(repeats)
        ]
        outputs.append(f"results/p5/benchmark_v3/aggregate_{condition}.json")
    else:
        store = DocumentStore(V4_STORE)
        items = load_items(V4_ITEMS)
        index = BM25Index(store.segments())
        system = build_v4_prompt()
        mode = "retrieval_tuned"
        command = (
            ".venv-ecosystem312/bin/python benchmarks/v2/run_v4_evaluation.py "
            f"--modes {mode} --repeats {repeats} --live"
        )
        outputs = [
            f"data/private_v4/results/raw_{mode}_r{k}.jsonl" for k in range(repeats)
        ]
        outputs.append("results/v2/v4/summary.json")

    tuned = tuned_index(index)
    prompts: list[str] = []
    for item in items:
        context = retrieval_context_for_item(item, store, index=tuned, k=8)
        if benchmark == "v3":
            prompt = system + "\n\n" + context.to_prompt_block()
        else:
            prompt = (
                system
                + "\n\nQUERY: extract the parameter value and its experimental "
                "conditions for this passage.\n\nEVIDENCE:\n"
                + context.to_evidence_block()
            )
        prompts.append(prompt)
        if show_prompts:
            print(f"--- {item.item_id} ---\n{prompt}\n")

    chars = sum(len(p) for p in prompts)
    return {
        "benchmark": benchmark,
        "items": len(items),
        "repeats": repeats,
        "calls": len(items) * repeats,
        "prompt_chars_per_run": chars,
        "estimated_prompt_tokens_per_run": round(chars / CHARS_PER_TOKEN),
        "estimated_total_prompt_tokens": round(chars * repeats / CHARS_PER_TOKEN),
        "command": command,
        "env_vars": list(ENV_VARS),
        "outputs": outputs,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--benchmark", choices=("v3", "v4", "both"), default="both")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--show-prompts", action="store_true")
    args = ap.parse_args()

    print("DRY RUN ONLY — no model client is constructed and no API call is made.")
    print("Env vars required: " + ", ".join(ENV_VARS))
    print(f"Token estimate: chars/{CHARS_PER_TOKEN} (no tokenizer download).")
    for benchmark in (("v3", "v4") if args.benchmark == "both" else (args.benchmark,)):
        plan = _plan(benchmark, args.repeats, show_prompts=args.show_prompts)
        print(json.dumps(plan, indent=2, sort_keys=True))
        missing = [key for key in ENV_VARS if not os.environ.get(key)]
        if missing:
            print(f"  missing env vars (fine for dry run): {missing}")
    print("Approval required before running any printed command.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
