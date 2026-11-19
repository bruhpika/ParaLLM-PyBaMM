"""Leakage guard: queries and expansion may never read gold information."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ARMS = REPO_ROOT / "src/pybamm_closed_loop/eval/retrieval_arms.py"
INDEX = REPO_ROOT / "src/pybamm_closed_loop/literature/index.py"
FORBIDDEN = {
    "probe",
    "passage_probe",
    "gold",
    "gold_segment_ids",
    "gold_conditions",
    "gold_value",
    "target_document_id",
    "notes",
    "document_id",
}


def _function_source(path: Path, name: str) -> str:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(path.read_text(), node) or ""
    raise AssertionError(f"{name} not found in {path}")


def _accessed_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
    return names


@pytest.mark.parametrize(
    "path,name",
    [
        (ARMS, "query_from_facets"),
        (ARMS, "query_from_parameter"),
        (ARMS, "query_for_item"),
        (ARMS, "facets_for_item"),
        (INDEX, "expand_query"),
    ],
)
def test_query_and_expansion_never_read_gold_fields(path, name):
    source = _function_source(path, name)
    assert not (_accessed_names(source) & FORBIDDEN), f"{name} touches gold fields"


def test_query_builder_works_without_gold_attributes():
    from pybamm_closed_loop.eval.retrieval_arms import query_for_item

    class NoGoldItem:
        item_id = "safe-item"

        facets = {
            "parameter_names": ["porosity"],
            "materials": ["separator"],
            "cell_chemistry": [],
            "cell_format": [],
            "conditions": {},
            "techniques": [],
        }
        parameter = {"name": "porosity", "unit": "%"}

        def __getattr__(self, name):
            if name in FORBIDDEN:
                raise AssertionError(f"query builder read forbidden field {name}")
            raise AttributeError(name)

    item = NoGoldItem()
    assert "porosity" in query_for_item(item)
