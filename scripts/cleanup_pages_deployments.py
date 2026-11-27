"""One-time cleanup of stale GitHub Pages deployment records.

The docs workflow used to deploy on every push to ``main``, leaving a long
history of near-identical ``github-pages`` deployment records. This script
deletes those records while preserving the deployment created by the
``v0.2.0-beta.1`` release (and any newer release/manual deployment).

Safety:

* ``--dry-run`` (the default) only lists what would be deleted.
* ``--apply`` is required for any mutation, and requires an explicit
  ``--confirm`` token so it cannot be triggered accidentally.
* Every candidate is matched on ``environment == "github-pages"`` and
  ``created_at < KEEP_AFTER`` (the release publication time), never on a
  guessed ID. On ``--apply``, the recorded SHA/ref/date of each deletion is
  written to a manifest under ``results/`` for traceability; dry runs leave
  that manifest untouched.
* Deleting a deployment also requires deleting its status records; both
  calls are made per candidate, oldest first.

This script does not touch source code, parameters, experimental data or
any git history. It requires ``gh`` to be installed and authenticated.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = "bruhpika/ParaLLM-PyBaMM"
MANIFEST = ROOT / "results" / "deployment_cleanup_manifest.json"

# Keep everything created at or after this UTC timestamp: that is the
# v0.2.0-beta.1 release publication, which produced the canonical deployment.
KEEP_AFTER = "2026-11-27T13:00:00Z"


def gh_api(path: str, *, method: str = "GET", payload: Any = None) -> Any:
    """Call the GitHub REST API via ``gh`` and parse JSON output."""
    cmd = ["gh", "api", path]
    if method == "GET":
        cmd += ["--paginate"]
    else:
        cmd += ["--method", method]
    if payload is not None:
        cmd += ["--input", "-"]
    result = subprocess.run(
        cmd,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api {path} failed: {result.stderr.strip()}")
    if not result.stdout.strip():
        return None
    # --paginate yields concatenated JSON arrays; merge them.
    decoder = json.JSONDecoder()
    text = result.stdout.strip()
    items: list[Any] = []
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        obj, end = decoder.raw_decode(text, idx)
        if isinstance(obj, list):
            items.extend(obj)
        else:
            items.append(obj)
        idx = end
    return items if len(items) != 1 or not isinstance(items[0], list) else items[0]


def list_deployments() -> list[dict[str, Any]]:
    """Return all deployment records for the repository, oldest first."""
    path = f"/repos/{REPO}/deployments?per_page=100"
    data = gh_api(path)
    if not isinstance(data, list):
        raise RuntimeError("unexpected response from deployments endpoint")
    return sorted(data, key=lambda d: d["created_at"])


def select_candidates(deployments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select old github-pages deployments; never select release-era ones."""
    cutoff = datetime.fromisoformat(KEEP_AFTER.replace("Z", "+00:00"))
    selected = []
    for dep in deployments:
        if dep.get("environment") != "github-pages":
            continue
        created = datetime.fromisoformat(dep["created_at"].replace("Z", "+00:00"))
        if created >= cutoff:
            continue
        selected.append(
            {
                "id": dep["id"],
                "environment": dep["environment"],
                "ref": dep["ref"],
                "sha": dep["sha"],
                "created_at": dep["created_at"],
                "statuses_url": dep["statuses_url"],
            }
        )
    return selected


def delete_deployment(dep: dict[str, Any]) -> None:
    """Delete a deployment and its statuses (idempotent on 404)."""
    statuses_path = dep["statuses_url"].split("//api.github.com", 1)[-1]
    try:
        gh_api(statuses_path, method="DELETE")
    except RuntimeError as exc:
        if "Not Found" not in str(exc):
            raise
    gh_api(f"/repos/{REPO}/deployments/{dep['id']}", method="DELETE")


def write_manifest(candidates: list[dict[str, Any]]) -> None:
    record = {
        "repo": REPO,
        "keep_after": KEEP_AFTER,
        "applied": True,
        "deleted_count": len(candidates),
        "candidates": candidates,
    }
    MANIFEST.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually delete the selected deployments (default: dry run)",
    )
    parser.add_argument(
        "--confirm",
        help="required literal 'DELETE' when --apply is used",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="delete at most this many candidates (oldest first)",
    )
    args = parser.parse_args(argv)

    if args.apply and args.confirm != "DELETE":
        parser.error("--apply requires --confirm DELETE")

    deployments = list_deployments()
    candidates = select_candidates(deployments)
    if args.limit is not None:
        candidates = candidates[: args.limit]

    print(f"Repository: {REPO}")
    print(f"Deployment records found: {len(deployments)}")
    print(f"Old github-pages records selected: {len(candidates)}")
    for dep in candidates:
        print(f"  {dep['id']}  {dep['created_at']}  {dep['sha'][:7]}  {dep['ref']}")

    if args.apply:
        print("APPLY: deleting selected deployments ...")
        for dep in candidates:
            delete_deployment(dep)
            print(f"  deleted {dep['id']}")
        write_manifest(candidates)
        print(f"Manifest written to {MANIFEST.relative_to(ROOT)}")
    else:
        print("DRY RUN: no deployments deleted. Re-run with --apply --confirm DELETE.")
        # A dry run must not overwrite the historical record of a prior apply.
    return 0


if __name__ == "__main__":
    sys.exit(main())
