#!/usr/bin/env python
"""Deterministically backfill verbatim Chen2020 article quotes (V2.2).

Fills the recorded evidence quotes for the 17 registry records that carry
``LITERATURE_DERIVED`` values without one (owner decision 2026-11-20:
backfill verbatim quotes from the article PDF; PDF sha256 confirmed
2026-11-22, see ``docs/DATA_PROVENANCE.md``). Quotes are carved from the
archived article text with the record's seed probe via the same
deterministic ``extract_quote`` used at seed time — never retyped.

Values, units, conditions and statuses are **not** touched: only
``evidence.source.{quote,char_start,char_end}`` change, every change is
logged through ``RegistryStore.upsert`` (``revisions.jsonl`` keeps the
previous record), and each quote is re-verified verbatim before it is
written. Idempotent: records that already carry a quote are skipped, never
overwritten.

Usage:
    .venv/bin/python scripts/backfill_chen2020_quotes.py
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pybamm_closed_loop.literature.evidence import verify_quote_in_evidence  # noqa: E402
from pybamm_closed_loop.registry.seed import RAW_DOC, SPEC, extract_quote  # noqa: E402
from pybamm_closed_loop.registry.store import RegistryStore  # noqa: E402

REGISTRY = REPO_ROOT / "data/registry"
ARTICLE_DOCUMENT_ID = "chen2020_jes_167_080534"
EXPECTED_TEXT_SHA256 = (
    "dffc1f9f532b9b899ce83caabcec711db154204db355f77e5a714d4ae28e07da"
)
ACTOR = "backfill:chen2020-article-quotes"
NOTE = (
    "V2.2 quote backfill: verbatim quote extracted from the archived article "
    "text with the record's seed probe (owner-approved 2026-11-20)"
)

# owner-approved scope: exactly the 17 traceability-flagged records
EXPECTED_IDS: tuple[str, ...] = (
    "cell_electrode_height",
    "cell_electrode_width",
    "electrolyte_conductivity",
    "electrolyte_diffusivity",
    "initial_electrolyte_concentration",
    "neg_current_collector_thickness",
    "neg_electrode_active_material_volume_fraction",
    "neg_electrode_thickness",
    "neg_particle_radius",
    "ocv_at_100pct_soc",
    "pos_current_collector_thickness",
    "pos_electrode_active_material_volume_fraction",
    "pos_electrode_ocp",
    "pos_electrode_thickness",
    "pos_particle_radius",
    "separator_porosity",
    "separator_thickness",
)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--registry", default=str(REGISTRY))
    ap.add_argument("--text", default=str(RAW_DOC))
    args = ap.parse_args(argv)

    text_path = Path(args.text)
    if not text_path.is_file():
        print(
            f"REFUSED: archived article text not found: {text_path}\n"
            "Restore data/raw_documents/chen2020_jes_167_080534/"
            "chen2020_jes_167_080534_fulltext.txt (git history blob "
            "10f00ec297f12fc36dd9e837efa888707222d513; sha256 "
            f"{EXPECTED_TEXT_SHA256}) and retry. No quote was invented.",
            file=sys.stderr,
        )
        return 1
    text = text_path.read_text()
    text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if text_sha != EXPECTED_TEXT_SHA256:
        print(
            f"REFUSED: archived article text sha256 mismatch\n"
            f"  expected: {EXPECTED_TEXT_SHA256}\n  actual:   {text_sha}\n"
            "The quotes must be carved from the exact archive the existing "
            "quotes were verified against. No quote was invented.",
            file=sys.stderr,
        )
        return 2

    # scope guard: the spec must carry the owner-approved probes and nothing
    # outside EXPECTED_IDS may be missing one while being LITERATURE_DERIVED
    for cid in EXPECTED_IDS:
        if not (SPEC.get(cid, {}).get("paper") or {}).get("probe"):
            print(f"REFUSED: SPEC[{cid}] has no probe", file=sys.stderr)
            return 3

    store = RegistryStore(Path(args.registry))
    filled: list[str] = []
    skipped: list[str] = []
    for cid in EXPECTED_IDS:
        record = store.get(cid)
        source = record.evidence.source
        if source.document_id != ARTICLE_DOCUMENT_ID:
            print(f"REFUSED: {cid} cites {source.document_id!r}", file=sys.stderr)
            return 4
        if source.quote:
            skipped.append(cid)
            continue
        probe = SPEC[cid]["paper"]["probe"]
        loc = extract_quote(text, probe)
        if not verify_quote_in_evidence(loc["quote"], text):
            print(f"REFUSED: extracted quote for {cid} fails verbatim check",
                  file=sys.stderr)
            return 5
        updated = copy.deepcopy(record)
        updated.evidence.source.quote = loc["quote"]
        updated.evidence.source.char_start = loc["char_start"]
        updated.evidence.source.char_end = loc["char_end"]
        store.upsert(updated, actor=ACTOR, note=f"{NOTE} (probe {probe!r})")
        filled.append(cid)
        print(
            f"{cid}: [{loc['char_start']}:{loc['char_end']}] "
            f"{loc['quote'][:90].replace(chr(10), ' ')}..."
        )

    print(
        f"\nbackfilled {len(filled)} quotes, skipped {len(skipped)} "
        f"(already quoted), registry {args.registry}"
    )
    print(
        "revisions appended to revisions.jsonl; values/units/conditions/"
        "statuses unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
