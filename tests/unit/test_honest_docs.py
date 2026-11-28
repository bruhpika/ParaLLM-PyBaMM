"""PHASE 4: documentation must be honest and version-synced."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"', text, re.MULTILINE).group(1)


def test_citation_version_matches_pyproject():
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r'^version: "([^"]+)"', citation, re.MULTILINE)
    assert match, "CITATION.cff has no version field"
    assert match.group(1) == _pyproject_version()


def test_readme_states_prototype_status_and_synthetic_only_assembly():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    lower = readme.lower()
    assert "research prototype" in lower
    assert "synthetic fixture" in lower
    assert "incomplete" in lower or "abstains" in lower


def test_readme_does_not_claim_expert_agreement():
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "expert agreement" not in readme
    assert "reviewed by the project owner" in readme


def test_readme_flags_oracle_window_and_unrun_llm_retrieval():
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "centred on the answer" in readme
    assert "not been run" in readme


def test_readme_has_ai_assistance_disclosure():
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    flat = " ".join(readme.split())
    assert "ai assistance disclosure" in flat
    assert "opencode ai agent" in flat
    assert "benchmark" in flat
