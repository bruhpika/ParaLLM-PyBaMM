"""Dev-only lexical retrieval ablation; test is reported once for the winner.

No model calls. New outputs only under results/v2/retrieval_improvement/ and
configs/retrieval/lexical_config.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "benchmarks/v2"))

import evaluate_retrieval as protocol  # noqa: E402
from pybamm_closed_loop.eval.benchmark_p5 import load_items_v3  # noqa: E402
from pybamm_closed_loop.eval.benchmark_v4 import load_items  # noqa: E402
from pybamm_closed_loop.eval.retrieval_arms import query_for_item  # noqa: E402
from pybamm_closed_loop.literature.index import BM25Index  # noqa: E402
from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402
from pybamm_closed_loop.literature.lexical import (  # noqa: E402
    lexical_search,
    lexical_terms,
    unit_query_terms,
)

OUT_DIR = protocol.OUT_DIR
ABLATION_JSON = OUT_DIR / "lexical_ablation.json"
ABLATION_MD = OUT_DIR / "lexical_ablation.md"
CONFIG_PATH = REPO_ROOT / "configs/retrieval/lexical_config.json"
REGISTRY = REPO_ROOT / "data/registry/registry.json"
PRIMARY = "recall@1"
SECONDARY = ("mrr", "document_recall@10")

VARIANTS: dict[str, dict[str, Any]] = {
    "registry_aliases": {"use_registry": True},
    "unit_terms": {"use_unit": True},
    "symbols": {"use_symbols": True},
    "query_all": {"use_registry": True, "use_unit": True, "use_symbols": True},
    "boost_tables": {"boost_tables": True},
    "boost_units": {"boost_units": True},
    "query_all_and_boosts": {
        "use_registry": True,
        "use_unit": True,
        "use_symbols": True,
        "boost_tables": True,
        "boost_units": True,
    },
    "bm25_k1_1p2": {"k1": 1.2, "b": 0.75},
    "bm25_b_0p5": {"k1": 1.5, "b": 0.5},
    "bm25_k1_2p0": {"k1": 2.0, "b": 0.75},
    "bm25_b_0p9": {"k1": 1.5, "b": 0.9},
}


def declared_unit(item: Any) -> str | None:
    parameter = getattr(item, "parameter", None)
    if isinstance(parameter, dict):
        return parameter.get("unit")
    facets = getattr(item, "facets", None)
    if isinstance(facets, dict):
        return facets.get("unit")
    return None


def log_variant(name: str, params: dict[str, Any], status: str, detail: str = "") -> None:
    entry = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "configuration": name,
        "params": params,
        "status": status,
        "split_used": "dev" if status != "chosen_test" else "test",
    }
    if detail:
        entry["detail"] = detail
    existing = []
    if protocol.CONFIG_LOG.exists():
        existing = [json.loads(line) for line in protocol.CONFIG_LOG.read_text().splitlines()]
    if any(
        e.get("configuration") == name
        and e.get("params") == params
        and e.get("status") == status
        for e in existing
    ):
        return
    protocol.log_config(entry)


def build_search(config: dict[str, Any], records: Sequence[dict[str, Any]]) -> Callable:
    cache: dict[tuple[float, float], BM25Index] = {}

    def search(index: BM25Index, query: str, k: int, item: Any):
        k1, b = float(config.get("k1", 1.5)), float(config.get("b", 0.75))
        key = (k1, b)
        if key not in cache:
            cache[key] = BM25Index(index.segments, k1=k1, b=b)
        active = cache[key]
        unit = declared_unit(item)
        terms = lexical_terms(
            query,
            unit=unit if config.get("use_unit") else None,
            registry_records=records if config.get("use_registry") else None,
            use_registry=bool(config.get("use_registry")),
            use_unit=bool(config.get("use_unit")),
            use_symbols=bool(config.get("use_symbols")),
        )
        return lexical_search(
            active,
            terms,
            k=k,
            boost_tables=bool(config.get("boost_tables")),
            unit_terms=unit_query_terms(unit) if config.get("boost_units") else (),
            boost_units=bool(config.get("boost_units")),
        )

    return search


def _mean(metrics: dict[str, Any], key: str) -> float:
    return float(metrics[key]["mean"])


def _render(payload: dict[str, Any]) -> str:
    lines = [
        "# Lexical retrieval ablation (dev-only tuning)",
        "",
        f"Seed {payload['seed']}; configurations tried: {payload['n_configurations_tried']} "
        "(`config_log.jsonl` includes failures).",
        "Gold labels are post-retrieval audit labels only. No model call is made.",
        "",
        "| configuration | dev recall@1 | dev MRR | dev doc-recall@10 |",
        "|---|---:|---:|---:|",
    ]
    dev_rows = dict(payload["dev"])
    if "baseline_dev" in payload:
        dev_rows = {"bm25 baseline (k1=1.5,b=0.75)": payload["baseline_dev"], **dev_rows}
    for name, row in dev_rows.items():
        m = row["metrics"]
        lines.append(
            f"| {name} | {_mean(m, 'recall@1'):.3f} | {_mean(m, 'mrr'):.3f} | "
            f"{_mean(m, 'document_recall@10'):.3f} |"
        )
    chosen = payload["chosen"]
    lines += [
        "",
        f"Chosen on dev: **{chosen['name']}** (primary recall@1, then MRR and doc-recall@10).",
        "Test was evaluated once for this configuration:",
        "",
        "| benchmark / corpus | test recall@1/3/5/10 | test MRR | test doc-recall@10 |",
        "|---|---:|---:|---:|",
    ]
    for key, row in payload["test"].items():
        m = row["metrics"]
        recalls = "/".join(f"{_mean(m, f'recall@{k}'):.3f}" for k in (1, 3, 5, 10))
        lines.append(
            f"| {key} | {recalls} | {_mean(m, 'mrr'):.3f} | "
            f"{_mean(m, 'document_recall@10'):.3f} |"
        )
    baseline = payload.get("baseline_test", {})
    if baseline:
        lines += [
            "",
            "Test comparison with the unchanged BM25 baseline (same frozen split):",
            "",
            "| benchmark / corpus | baseline recall@1/3/5/10 | chosen recall@1/3/5/10 |",
            "|---|---:|---:|",
        ]
        for key, row in payload["test"].items():
            if key not in baseline:
                continue
            m, b = row["metrics"], baseline[key]
            chosen_recalls = "/".join(f"{_mean(m, f'recall@{k}'):.3f}" for k in (1, 3, 5, 10))
            base_recalls = "/".join(f"{_mean(b, f'recall@{k}'):.3f}" for k in (1, 3, 5, 10))
            lines.append(f"| {key} | {base_recalls} | {chosen_recalls} |")
    lines += [
        "",
        "The v4 corpus is small and private; v3 and v4 results are not comparable.",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evaluate-test", action="store_true")
    ap.add_argument("--render-only", action="store_true")
    args = ap.parse_args(argv)

    baseline_path = OUT_DIR / "baseline.json"
    baseline_payload = json.loads(baseline_path.read_text())

    def baseline_split(split_name: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for bench, corpora in baseline_payload["benchmarks"].items():
            for corpus, splits in corpora.items():
                if split_name == "test":
                    out[f"{bench}/{corpus}"] = splits["test"]["metrics"]
                elif bench == "v4" and corpus == "small":
                    out["v4/small"] = splits["dev"]["metrics"]
        return out

    if args.render_only:
        payload = json.loads(ABLATION_JSON.read_text())
        payload["baseline_test"] = baseline_split("test")
        payload["baseline_dev"] = {"metrics": baseline_split("dev")["v4/small"]}
        ABLATION_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        ABLATION_MD.write_text(_render(payload))
        print(f"re-rendered {ABLATION_MD}")
        return 0

    split = protocol.load_split()
    records = json.loads(REGISTRY.read_text())
    v3_by_id = {str(it.item_id): it for it in load_items_v3(protocol.V3_ITEMS)}
    v4_by_id = {str(it.item_id): it for it in load_items(protocol.V4_ITEMS)}
    main_store = DocumentStore(protocol.V3_STORE)
    v4_store = DocumentStore(protocol.V4_STORE)
    corpora = {
        "v3/full": (
            v3_by_id,
            protocol.load_gold(protocol.V3_AUDIT),
            BM25Index(main_store.segments()),
        ),
        "v4/small": (
            v4_by_id,
            protocol.load_gold(protocol.V4_SMALL_AUDIT),
            BM25Index(v4_store.segments()),
        ),
        "v4/full": (
            v4_by_id,
            protocol.load_gold(protocol.V4_FULL_AUDIT),
            BM25Index(v4_store.segments() + main_store.segments()),
        ),
    }

    payload: dict[str, Any] = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "seed": protocol.SEED,
        "corpus_sets": ["v4/small (dev tuning)", "v3/full and v4/full (test)"],
        "dev": {},
        "test": {},
        "failures": [],
    }
    # Dev tuning uses only the small v4 corpus: it has all gold labels indexed
    # and is the stress-test setting that motivated this work.
    by_id, gold, index = corpora["v4/small"]
    dev_items = [by_id[i] for i in split["benchmarks"]["v4"]["dev"]]
    for name, config in VARIANTS.items():
        try:
            stats, _rows = protocol.evaluate(
                dev_items,
                index,
                gold,
                query_fn=query_for_item,
                search_fn=build_search(config, records),
            )
            payload["dev"][name] = {"config": config, "metrics": stats["metrics"]}
            log_variant(name, config, "ok")
        except Exception as exc:  # logged, never silently skipped
            payload["failures"].append({"configuration": name, "error": str(exc)})
            log_variant(name, config, "failed", str(exc))

    def rank(name: str):
        m = payload["dev"][name]["metrics"]
        return (
            -_mean(m, PRIMARY),
            -_mean(m, SECONDARY[0]),
            -_mean(m, SECONDARY[1]),
        )

    chosen_name = min(payload["dev"], key=rank)
    chosen_config = payload["dev"][chosen_name]["config"]
    payload["chosen"] = {"name": chosen_name, "config": chosen_config}
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).isoformat(),
                "seed": protocol.SEED,
                "selected_on": "v4/small dev only",
                "name": chosen_name,
                "config": chosen_config,
                "selection_rule": "max dev recall@1, then MRR, then doc-recall@10",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    if args.evaluate_test:
        for key in ("v3/full", "v4/small", "v4/full"):
            by_id, gold, index = corpora[key]
            test_items = [
                by_id[i]
                for i in split["benchmarks"]["v3" if key.startswith("v3") else "v4"]["test"]
            ]
            stats, _rows = protocol.evaluate(
                test_items,
                index,
                gold,
                query_fn=query_for_item,
                search_fn=build_search(chosen_config, records),
            )
            payload["test"][key] = {"metrics": stats["metrics"], "n_items": stats["n_items"]}
            log_variant(chosen_name, chosen_config, "chosen_test", key)

    payload["baseline_test"] = baseline_split("test")
    payload["baseline_dev"] = {"metrics": baseline_split("dev")["v4/small"]}
    payload["n_configurations_tried"] = len(VARIANTS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ABLATION_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    ABLATION_MD.write_text(_render(payload))
    print(f"chosen on dev: {chosen_name}; wrote {ABLATION_JSON}, {ABLATION_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
