"""Dry-run planner tests: no model client, no API call, no download."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_PATH = REPO_ROOT / "benchmarks/v2/prepare_live_retrieval.py"
_SPEC = importlib.util.spec_from_file_location("prepare_live_retrieval", _PATH)
assert _SPEC and _SPEC.loader
MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MOD)


def test_planner_has_no_model_client():
    source = _PATH.read_text()
    assert "OpenAICompatibleClient" not in source
    assert "client.complete" not in source
    assert "requests" not in source


def test_dry_run_counts_match_items_and_repeats():
    plan = MOD._plan("v4", 3, show_prompts=False)
    assert plan["items"] == 30
    assert plan["calls"] == 90
    assert "--live" in plan["command"]
    assert plan["estimated_total_prompt_tokens"] > 0
    assert set(plan["env_vars"]) == {"PYCL_LLM_API_KEY", "PYCL_LLM_MODEL", "PYCL_LLM_BASE_URL"}


def test_v3_plan_mentions_local_ingest_when_text_absent(capsys):
    plan = MOD._plan("v3", 2, show_prompts=False)
    stderr = capsys.readouterr().err
    if not MOD.article_source_text_available():
        assert "ingest first" in stderr
    assert plan["calls"] == plan["items"] * 2
