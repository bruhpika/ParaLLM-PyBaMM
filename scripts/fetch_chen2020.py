#!/usr/bin/env python
"""Fetch-free local ingest of the Chen2020 article PDF (verification first).

The publisher PDF is **not** downloaded here and is **not** redistributed. The
owner supplies a path to an already-acquired PDF; this script verifies its
sha256 against the value recorded in ``docs/DATA_PROVENANCE.md`` and only then
ingests it with the existing ``DocumentStore.ingest_pdf`` code into the local
(and gitignored) literature store.

Usage:
    .venv-ecosystem312/bin/python scripts/fetch_chen2020.py --pdf /path/to/chen2020.pdf
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402

DOCUMENT_ID = "chen2020_jes_167_080534"
PROVENANCE_DOC = REPO_ROOT / "docs/DATA_PROVENANCE.md"
DEFAULT_STORE = REPO_ROOT / "data/literature_store"
TITLE = (
    "Development of Experimental Techniques for Parameterization of "
    "Multi-scale Lithium-ion Battery Models"
)
HASH_LINE = "Chen2020 article PDF sha256:"
_HASH_RE = re.compile(rf"{re.escape(HASH_LINE)}\s*([0-9a-fA-F]{{64}})\b")


def expected_pdf_sha256(provenance_text: str) -> str | None:
    """Return the recorded PDF sha256, or None while it is owner-to-fill."""
    match = _HASH_RE.search(provenance_text)
    return match.group(1).lower() if match else None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True, help="path to an owner-supplied publisher PDF")
    ap.add_argument("--provenance", default=str(PROVENANCE_DOC))
    ap.add_argument("--store", default=str(DEFAULT_STORE))
    ap.add_argument("--retrieved", default=date.today().isoformat())
    args = ap.parse_args(argv)

    provenance = Path(args.provenance).read_text(encoding="utf-8")
    expected = expected_pdf_sha256(provenance)
    if expected is None:
        print(
            "REFUSED: no expected Chen2020 PDF sha256 is recorded in "
            f"{args.provenance}.\n{HASH_LINE} is still owner-to-fill; record a "
            "verified 64-hex value there before ingesting. No hash was invented.",
            file=sys.stderr,
        )
        return 1

    pdf = Path(args.pdf)
    if not pdf.is_file():
        print(f"REFUSED: PDF not found: {pdf}", file=sys.stderr)
        return 1
    actual = sha256_of(pdf)
    if actual != expected:
        print(
            f"REFUSED: sha256 mismatch for {pdf}.\n  expected: {expected}\n"
            f"  actual:   {actual}\nNo file was ingested. Check that this is the "
            "publisher PDF recorded in docs/DATA_PROVENANCE.md.",
            file=sys.stderr,
        )
        return 2

    store = DocumentStore(Path(args.store))
    record = store.ingest_pdf(
        DOCUMENT_ID,
        pdf,
        kind="paper",
        doi_or_url="10.1149/1945-7111/ab9050",
        source_url="https://iopscience.iop.org/article/10.1149/1945-7111/ab9050",
        title=TITLE,
        retrieved=args.retrieved,
    )
    print(f"verified sha256 {actual}; ingested {DOCUMENT_ID} locally")
    print(f"  raw text: {store.raw_dir / f'{DOCUMENT_ID}.txt'}")
    print(f"  segments: {store.segments_dir / f'{DOCUMENT_ID}.json'} (n={record.n_segments})")
    print("These paths are gitignored; do not commit them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
