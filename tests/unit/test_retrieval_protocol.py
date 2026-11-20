"""Frozen split and metric protocol tests (deterministic, no model calls)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_V4_ITEMS = REPO_ROOT / "data/private_v4/fixture/benchmark_v4.jsonl"
_SPEC = importlib.util.spec_from_file_location(
    "evaluate_retrieval", REPO_ROOT / "benchmarks/v2/evaluate_retrieval.py"
)
assert _SPEC and _SPEC.loader
MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MOD)


class _Item:
    def __init__(self, item_id: str, document_id: str, name: str):
        self.item_id = item_id
        self.document_id = document_id
        self.facets = {
            "parameter_names": [name],
            "materials": [],
            "cell_chemistry": [],
            "cell_format": [],
            "conditions": {},
            "techniques": [],
        }


def test_split_is_deterministic_balanced_and_disjoint():
    items = [
        _Item(f"it-{i}", f"doc{i % 3}", name)
        for i, name in enumerate(["porosity", "diffusivity", "thickness", "capacity"] * 3)
    ]
    first = MOD.make_split(items, seed=42)
    second = MOD.make_split(items, seed=42)
    assert first == second
    dev, test = set(first["dev"]), set(first["test"])
    assert not dev & test
    assert dev | test == {it.item_id for it in items}
    assert abs(len(dev) - len(test)) <= 1


def test_bootstrap_ci_is_deterministic_and_brackets_values():
    values = [0.0, 1.0, 0.0, 1.0, 0.5]
    a = MOD.bootstrap_ci(values, 7)
    b = MOD.bootstrap_ci(values, 7)
    assert a == b
    assert 0.0 <= a["low"] <= a["high"] <= 1.0


def _assert_split_matches(split, bench, loader, path, n):
    ids = {str(it.item_id) for it in loader(path)}
    s = split["benchmarks"][bench]
    assert len(s["dev"]) + len(s["test"]) == n
    assert set(s["dev"]) | set(s["test"]) == ids
    assert not set(s["dev"]) & set(s["test"])


def test_committed_split_covers_v3_items():
    split = json.loads(
        (REPO_ROOT / "configs/retrieval/dev_test_split.json").read_text()
    )
    from pybamm_closed_loop.eval.benchmark_p5 import load_items_v3

    _assert_split_matches(
        split, "v3", load_items_v3, REPO_ROOT / "data/eval/extraction_benchmark_v3.jsonl", 37
    )
    assert split["seed"] == MOD.SEED


@pytest.mark.skipif(
    not PRIVATE_V4_ITEMS.exists(), reason="private v4 fixture not present in this checkout"
)
def test_committed_split_covers_private_v4_items():
    split = json.loads(
        (REPO_ROOT / "configs/retrieval/dev_test_split.json").read_text()
    )
    from pybamm_closed_loop.eval.benchmark_v4 import load_items

    _assert_split_matches(split, "v4", load_items, PRIVATE_V4_ITEMS, 30)
