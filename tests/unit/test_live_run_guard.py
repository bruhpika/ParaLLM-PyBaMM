"""Live-run guards, raw-output safety and network-free replay (TASK B)."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.eval.benchmark import run_benchmark  # noqa: E402
from pybamm_closed_loop.eval.run_guard import (  # noqa: E402
    LiveRunDisabled,
    LiveRunPolicy,
    add_live_guard_args,
    client_for_live_run,
    find_raw,
    git_commit,
)
from pybamm_closed_loop.literature.extraction import (  # noqa: E402
    OfflineDeterministicExtractor,
)
from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402


class FakeClient:
    """A model client that fails loudly if any network call is attempted."""

    name = "fake:no-network"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        raise AssertionError("a network/model call was attempted")


def _load_runner(relative: str):
    path = REPO_ROOT / relative
    spec = importlib.util.spec_from_file_location(f"runner_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_policy_requires_explicit_live():
    policy = LiveRunPolicy(live=False, overwrite=True)
    with pytest.raises(LiveRunDisabled, match="--live"):
        policy.ensure_allowed()
    with pytest.raises(LiveRunDisabled):
        policy.metadata(model="m", base_url="u")


def test_raw_path_is_redirected_instead_of_overwritten(tmp_path):
    policy = LiveRunPolicy(live=True, overwrite=False)
    direct = tmp_path / "raw.jsonl"
    direct.write_text("frozen")
    target = policy.raw_path(tmp_path, "raw.jsonl")
    assert target != direct
    assert target.name == "raw.jsonl"
    assert not target.exists()
    assert direct.read_text() == "frozen"
    target.parent.mkdir(parents=True)
    target.write_text("new")
    assert find_raw(tmp_path, "raw.jsonl") == direct
    direct.unlink()
    assert find_raw(tmp_path, "raw.jsonl") == target


def test_overwrite_and_offline_paths_stay_direct(tmp_path):
    direct = tmp_path / "raw.jsonl"
    direct.write_text("frozen")
    assert LiveRunPolicy(live=True, overwrite=True).raw_path(tmp_path, "raw.jsonl") == direct
    assert LiveRunPolicy(live=False, overwrite=False).raw_path(tmp_path, "raw.jsonl") == direct


def test_live_metadata_records_model_url_date_and_commit():
    policy = LiveRunPolicy(live=True, overwrite=False)
    meta = policy.metadata(model="model-x", base_url="https://example.invalid/v1", repo_root=REPO_ROOT)
    assert meta["model"] == "model-x"
    assert meta["base_url"] == "https://example.invalid/v1"
    assert meta["date"]
    assert meta["live"] is True
    assert meta["git_commit"] and len(meta["git_commit"]) == 40


def test_git_commit_outside_repository(tmp_path):
    assert git_commit(tmp_path) is None


def test_replay_never_constructs_or_calls_a_client():
    built: list[FakeClient] = []

    def factory() -> FakeClient:
        built.append(FakeClient())
        return built[-1]

    assert client_for_live_run(LiveRunPolicy(False, False), factory, replay=True) is None
    assert built == []
    with pytest.raises(LiveRunDisabled):
        client_for_live_run(LiveRunPolicy(False, False), factory, replay=False)
    assert built == []
    client = client_for_live_run(LiveRunPolicy(True, False), factory, replay=False)
    assert client is built[0]
    assert client.calls == 0


def test_live_guard_args_are_registered():
    import argparse

    parser = argparse.ArgumentParser()
    add_live_guard_args(parser)
    args = parser.parse_args([])
    assert args.live is False and args.overwrite is False and args.replay is False


@pytest.mark.parametrize(
    "relative,argv",
    [
        ("benchmarks/p3/run_extraction_benchmark.py", ["--provider", "llm"]),
        ("benchmarks/p4/run_llm_evaluation.py", ["--arm", "llm_rag"]),
        ("benchmarks/p5/run_ablation.py", ["--condition", "retrieval_strict"]),
        ("benchmarks/v2/run_v4_evaluation.py", []),
    ],
)
def test_runners_refuse_live_without_flag(monkeypatch, relative, argv):
    """No runner may construct a model client (or call it) without --live."""
    module = _load_runner(relative)
    built: list[FakeClient] = []

    def factory(*_args, **_kwargs) -> FakeClient:
        built.append(FakeClient())
        return built[-1]

    monkeypatch.setattr(module, "OpenAICompatibleClient", factory, raising=False)
    monkeypatch.setattr(sys, "argv", ["runner", *argv])
    with pytest.raises(SystemExit):
        module.main()
    assert built == [], "a model client was constructed without --live"


def test_p3_live_run_redirects_raw_instead_of_clobbering(monkeypatch, tmp_path):
    """A live run with a fake client never overwrites frozen raw outputs."""
    module = _load_runner("benchmarks/p3/run_extraction_benchmark.py")
    instances: list[FakeLiveClient] = []

    class FakeLiveClient:
        name = "fake:live"
        model = "fake-model-1"
        base_url = "https://example.invalid/v1"

        def __init__(self) -> None:
            self.calls = 0
            instances.append(self)

        def complete(self, system: str, user: str) -> str:
            self.calls += 1
            return "[]"

    monkeypatch.setattr(module, "OpenAICompatibleClient", FakeLiveClient)
    argv = [
        "runner",
        "--provider",
        "llm",
        "--live",
        "--out",
        str(tmp_path),
        "--items",
        "data/eval/extraction_benchmark_v1.jsonl",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert module.main() == 0
    direct = tmp_path / "raw_outputs_llm.jsonl"
    original = direct.read_text()
    meta = json.loads(
        (tmp_path / "extraction_benchmark_v1_llm" / "report.json").read_text()
    )["run_metadata"]
    assert meta["model"] == "fake-model-1"
    assert meta["base_url"] == "https://example.invalid/v1"
    assert len(meta["git_commit"]) == 40

    assert module.main() == 0
    assert direct.read_text() == original
    redirected = list(tmp_path.glob("live_*/raw_outputs_llm.jsonl"))
    assert len(redirected) == 1
    assert instances[-1].calls > 0  # fake client really exercised the live path

    monkeypatch.setattr(sys, "argv", [*argv, "--overwrite"])
    assert module.main() == 0
    assert len(list(tmp_path.glob("live_*"))) == 1  # no further directory created


def test_p3_replay_rescores_cached_raw_without_api_key(monkeypatch, tmp_path):
    """Replay re-scores frozen model output with no client, network or API key."""
    module = _load_runner("benchmarks/p3/run_extraction_benchmark.py")
    store = DocumentStore(REPO_ROOT / "data/literature_store")
    from pybamm_closed_loop.eval.benchmark import load_items

    items = load_items(REPO_ROOT / "data/eval/extraction_benchmark_v1.jsonl")
    sink = io.StringIO()
    frozen = run_benchmark(items, store, client=OfflineDeterministicExtractor(), raw_sink=sink)
    (tmp_path / "raw_outputs_llm.jsonl").write_text(sink.getvalue())

    def fail_factory(*_args, **_kwargs):
        raise AssertionError("replay must not construct a model client")

    monkeypatch.setattr(module, "OpenAICompatibleClient", fail_factory)
    for key in ("PYCL_LLM_API_KEY", "PYCL_LLM_BASE_URL", "PYCL_LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["runner", "--out", str(tmp_path), "--replay"],
    )
    assert module.main() == 0
    replayed = json.loads(
        (tmp_path / "extraction_benchmark_v1_replay" / "report.json").read_text()
    )
    assert replayed["metrics"] == frozen["metrics"]
    assert replayed["run_metadata"]["replay"] is True
    assert os.environ.get("PYCL_LLM_API_KEY") is None
