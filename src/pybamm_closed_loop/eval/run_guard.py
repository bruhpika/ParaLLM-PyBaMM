"""Shared guards for runners that can call a model.

Live model calls are opt-in (``--live``). Raw model outputs are never silently
overwritten (``--overwrite``); without it a live run writes to a fresh
timestamped directory. Replay/re-score paths make no network calls and need no
API key. Every live run records the exact model, base URL, date and git commit.
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")


class LiveRunDisabled(SystemExit):
    """Refuse a live model run without ``--live`` (clean CLI error, exit 1)."""


@dataclass(frozen=True)
class LiveRunPolicy:
    """Policy resolved from the shared CLI flags of a model-calling runner."""

    live: bool
    overwrite: bool

    def ensure_allowed(self) -> None:
        if not self.live:
            raise LiveRunDisabled(
                "Live model calls require --live. Use --rescore/--replay (no "
                "network, no API key) or an offline arm for a default run."
            )

    def raw_path(self, base_dir: Path, filename: str) -> Path:
        """Return a raw-output path that cannot clobber an existing file.

        Without ``--live`` or with ``--overwrite`` the usual path is returned.
        A live run without ``--overwrite`` is redirected to a new timestamped
        subdirectory when the target already exists.
        """
        target = base_dir / filename
        if not self.live or self.overwrite or not target.exists():
            return target
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return base_dir / f"live_{stamp}" / filename

    def metadata(
        self,
        *,
        model: str | None,
        base_url: str | None,
        date: str | None = None,
        repo_root: Path | None = None,
    ) -> dict:
        """Run metadata for a live model call; includes the exact git commit."""
        self.ensure_allowed()
        now = datetime.now(timezone.utc).isoformat()
        return {
            "live": True,
            "model": model,
            "base_url": base_url,
            "date": date or now[:10],
            "git_commit": git_commit(repo_root),
            "timestamp": now,
        }


def add_live_guard_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared live/replay/overwrite flags to a runner's parser."""
    parser.add_argument(
        "--live",
        action="store_true",
        help="allow live model/API calls (default: refuse; use replay or offline)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="permit overwriting existing raw outputs (live runs only)",
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="re-score cached raw outputs with no network call and no API key",
    )


def client_for_live_run(
    policy: LiveRunPolicy,
    factory: Callable[[], T],
    *,
    replay: bool,
) -> T | None:
    """Construct a model client only when a live call is actually permitted.

    Replay returns ``None`` without calling the factory, so no client (and no
    network-capable object) is created on the offline path.
    """
    if replay:
        return None
    policy.ensure_allowed()
    return factory()


def find_raw(base_dir: Path, filename: str) -> Path | None:
    """Locate a frozen raw file, including one in a timestamped live directory."""
    direct = base_dir / filename
    if direct.exists():
        return direct
    candidates = sorted(base_dir.glob(f"live_*/{filename}"))
    return candidates[-1] if candidates else None


def git_commit(repo_root: Path | None = None) -> str | None:
    """Return the current git commit id, or ``None`` outside a git checkout."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None
