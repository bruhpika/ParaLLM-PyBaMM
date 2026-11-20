"""Tests for the examples gallery (deterministic, no network, no LLM)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "examples"


def _run(name: str, out_dir: Path) -> subprocess.CompletedProcess[str]:
    script = EXAMPLES / name
    return subprocess.run(
        [sys.executable, str(script), "--out-dir", str(out_dir)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_retrieval_recall_example_writes_summary(tmp_path):
    result = _run("01_retrieval_recall.py", tmp_path)
    assert result.returncode == 0, result.stderr
    out = tmp_path / "retrieval_recall.json"
    assert out.is_file()
    assert out.stat().st_size > 0


def test_synthetic_validation_example_writes_figure(tmp_path):
    result = _run("02_synthetic_validation_figure.py", tmp_path)
    assert result.returncode == 0, result.stderr
    out = tmp_path / "heldout_rmse.png"
    assert out.is_file()
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_assemble_example_writes_report(tmp_path):
    result = _run("03_assemble_dossiers.py", tmp_path)
    assert result.returncode == 0, result.stderr
    for name in ("report.json", "report.md", "manifest.json"):
        out = tmp_path / name
        assert out.is_file()
        assert out.stat().st_size > 0
