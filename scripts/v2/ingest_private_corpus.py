"""Ingest the PRIVATE v4 corpus into a private document store.

The v4 benchmark is deliberately **not published**: its corpus, fixture and
answers live under ``data/private_v4/`` (git-ignored). This script is
committed so the corpus can be rebuilt reproducibly from the recorded URLs
and sha256 checksums — the fixture itself is never committed.

Sources (all CC BY 4.0, verified in the PDF text; see manifest):
  * Schmitt et al. 2023, JES 170 070509 — full parameterization study
    (NCA / graphite-SiOx and NCA / graphite 21700 cells; GITT+EIS at
    25 °C, repeated at 10 °C and 40 °C) — categories A and C.
  * Tuchel et al. 2026, JES (10.1149/1945-7111/aea7e1) — NMC/graphite
    parameterization via current interrupt + voltage relaxation (EIS series
    resistance) — categories A/C.
  * Ghoulam 2022, Energies 15 4005 — downloaded but **not usable**: the
    experimental-setup section is not present in the extracted PDF text, so its
    conditions cannot be verified against the archive (kept for reference).
  * Wheeler et al. 2024, Batteries 10 119 — 18650 graphite/LFP postmortem
    aging study — categories A and E (conditions not stated).

Usage:
    .venv-ecosystem312/bin/python scripts/v2/ingest_private_corpus.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.literature.ingest import DocumentStore  # noqa: E402

PRIVATE_ROOT = REPO_ROOT / "data/private_v4"
CORPUS_DIR = PRIVATE_ROOT / "corpus"
STORE_DIR = PRIVATE_ROOT / "store"

DOCS = [
    {
        "document_id": "schmitt2023_jes_170_070509",
        "pdf": "schmitt2023_jes_170_070509.pdf",
        "kind": "paper",
        "title": (
            "Full Parameterization Study of a High-Energy and High-Power Li-Ion Cell "
            "for Physicochemical Models"
        ),
        "doi_or_url": "https://doi.org/10.1149/1945-7111/ace1a7",
        "source_url": "https://iopscience.iop.org/article/10.1149/1945-7111/ace1a7/pdf",
        "license": "CC BY 4.0",
    },
    {
        "document_id": "tuchel2026_jes_aea7e1",
        "pdf": "tuchel2026_jes_aea7e1.pdf",
        "kind": "paper",
        "title": (
            "Accelerated Electrochemical Parameterization of NMC and Graphite via "
            "Current Interrupt and Voltage Relaxation Extrapolation"
        ),
        "doi_or_url": "https://doi.org/10.1149/1945-7111/aea7e1",
        "source_url": "https://iopscience.iop.org/article/10.1149/1945-7111/aea7e1/pdf",
        "license": "CC BY 4.0 (open access, to be verified in the PDF text)",
    },
    {
        "document_id": "ghoulam2022_energies_15_04005",
        "pdf": "ghoulam2022_energies_15_04005.pdf",
        "kind": "paper",
        "title": (
            "Lithium-Ion Battery Parameter Identification for Hybrid and Electric "
            "Vehicles Using Drive Cycle Data"
        ),
        "doi_or_url": "https://doi.org/10.3390/en15114005",
        "source_url": (
            "https://mdpi-res.com/d_attachment/energies/energies-15-04005/"
            "article_deploy/energies-15-04005.pdf"
        ),
        "license": "CC BY 4.0",
    },
    {
        "document_id": "wheeler2024_batteries_10_00119",
        "pdf": "wheeler2024_batteries_10_00119.pdf",
        "kind": "paper",
        "title": (
            "Postmortem Analysis of 18650 Graphite/LFP Cells in a Long-Term Aging "
            "Study for Second-Life Applications"
        ),
        "doi_or_url": "https://doi.org/10.3390/batteries10040119",
        "source_url": (
            "https://mdpi-res.com/d_attachment/batteries/batteries-10-00119/"
            "article_deploy/batteries-10-00119.pdf"
        ),
        "license": "CC BY 4.0",
    },
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    store = DocumentStore(STORE_DIR)
    have = {d.document_id for d in store.documents()}

    manifest = []
    for doc in DOCS:
        pdf = CORPUS_DIR / doc["pdf"]
        if not pdf.exists():
            print(f"MISSING {pdf} — download from {doc['source_url']}")
            manifest.append({**doc, "status": "missing"})
            continue
        digest = sha256(pdf)
        if doc["document_id"] not in have:
            store.ingest_pdf(
                doc["document_id"],
                pdf,
                kind=doc["kind"],
                title=doc["title"],
                doi_or_url=doc["doi_or_url"],
                retrieved="2026-11-12",
                meta={
                    "license": doc["license"],
                    "page_numbering": "1-based PDF page indices (pypdf)",
                    "corpus": "private v4 benchmark corpus (not published)",
                },
            )
            print(f"ingested {doc['document_id']}")
        else:
            print(f"present  {doc['document_id']}")
        manifest.append(
            {
                **doc,
                "sha256": digest,
                "bytes": pdf.stat().st_size,
                "status": "ingested",
                "license_evidence": "CC BY 4.0 statement present in the PDF text",
            }
        )

    (PRIVATE_ROOT / "corpus_manifest.json").write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).isoformat(),
                "note": (
                    "Private corpus manifest — kept out of the public repository; "
                    "commit only the builder script, never this file or the PDFs."
                ),
                "documents": manifest,
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(f"wrote {PRIVATE_ROOT / 'corpus_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
