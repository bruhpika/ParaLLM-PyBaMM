"""Tests for the v4a applicability mini-benchmark (deterministic, no network)."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "data/registry/registry.json"


def _registry() -> list[dict]:
    return json.loads(REGISTRY.read_text())


def test_build_dataset_covers_every_registry_conflict():
    from pybamm_closed_loop.eval.v4a_cases import build_dataset

    records = _registry()
    public, answers = build_dataset(records)
    n_conflicts = sum(1 for r in records if r.get("conflicts"))
    assert len(public) == n_conflicts
    assert len(answers) == n_conflicts
    assert len(public) >= 1


def test_public_cases_have_no_gold_answers():
    from pybamm_closed_loop.eval.v4a_cases import build_dataset

    public, _ = build_dataset(_registry())
    for case in public:
        assert "expert_decision" not in case
        assert "expert_choice" not in case
        assert "expert_rationale" not in case
        assert "ambiguous" not in case


def test_answers_are_drafted_and_choose_the_operative_candidate():
    from pybamm_closed_loop.eval.v4a_cases import build_dataset

    public, answers = build_dataset(_registry())
    for case, answer in zip(public, answers):
        assert case["case_id"] == answer["case_id"]
        assert answer["expert_choice"] == 0
        assert answer["label_status"] == "drafted"
        assert answer["reviewed_by"] is None
        assert answer["expert_decision"] in {"USE", "FIX"}


def test_candidates_are_copied_from_the_registry():
    from pybamm_closed_loop.eval.v4a_cases import build_dataset

    records = {r["canonical_id"]: r for r in _registry()}
    public, _ = build_dataset(_registry())
    for case in public:
        record = records[case["parameter"]]
        operative, alternative = case["candidates"]
        assert operative["value"] == record["value"]
        assert alternative["value"] == (record["conflicts"] or [{}])[0].get("value")


def test_runner_writes_agreement_and_summary(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_v4a", REPO_ROOT / "benchmarks/v2/run_v4a.py"
    )
    assert spec and spec.loader
    run_v4a = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_v4a)

    cases_path = tmp_path / "cases.jsonl"
    answers_path = tmp_path / "answers.jsonl"
    split_path = tmp_path / "split.json"
    out_dir = tmp_path / "out"

    records = _registry()
    from pybamm_closed_loop.eval.v4a_cases import build_dataset  # noqa: PLC0415

    public, answers = build_dataset(records)
    cases_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in public) + "\n"
    )
    answers_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in answers) + "\n"
    )
    split_path.write_text(json.dumps({"dev": [], "test": []}))

    rc = run_v4a.main(
        [
            "--cases", str(cases_path),
            "--answers", str(answers_path),
            "--split", str(split_path),
            "--out", str(out_dir),
        ]
    )
    assert rc == 0
    agreement = json.loads((out_dir / "agreement.json").read_text())
    assert agreement["n_cases"] == len(public)
    assert (out_dir / "summary.md").is_file()
