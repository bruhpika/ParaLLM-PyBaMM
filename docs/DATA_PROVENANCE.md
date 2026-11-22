# Data, Document & License Provenance

This separates **software licensing** from **dataset/document licensing**.
The repository's MIT `LICENSE` covers PARALLM source code only; it
does **not** grant rights to third-party datasets, papers, PDFs, or parameter
sets. Materials are redistributed only where permitted, with attribution and
recorded license evidence.

## Policy

- Preserve raw data and source documents; never overwrite them. Keep
  acquisition metadata (URL/DOI, retrieval date, sha256, license/evidence).
- Distinguish user-supplied / literature-derived / calculated / assumed /
  calibrated / unresolved values. Do not invent sources or values.
- Do not redistribute datasets or papers without permission. When permission
  is unclear, **do not commit the file**; keep an acquisition note and
  derived, provenance-linked artifacts where appropriate.

## Redistributed in-repo (permitted / evidenced)

| material | location | license / evidence | notes |
|---|---|---|---|
| Laue et al. 2021 (J Appl Electrochem 51:1253–1265) | `data/raw_documents/laue2021_jappl_electrochem_51_1253/` | **CC BY 4.0** (PDF text verified) | archived + sha256 in `data/raw_documents/p5_sources/acquisition_manifest.json`; ingested to `data/literature_store/` |
| Dessantis et al. 2023 (Batteries 9:146) | `data/raw_documents/dessantis2023_batteries9_0146/` | **CC BY 4.0** (verified) | same |
| Goussian et al. 2024 (Batteries 10:205) | `data/raw_documents/goussian2024_batteries10_00205/` | **CC BY 4.0** (verified) | same; no numeric cell parameters (data confidential) |
| PyBaMM parameter-sets documentation snapshot | `data/raw_documents/pybamm_parameter_sets_docs/` | PyBaMM project docs (PyBaMM code is **BSD 3-Clause**, verified below; the docs snapshot itself has no explicit licence evidence recorded) | ingested text snapshot |
| Chen2020 **text** extract (article) | not tracked; fetch + verify locally via `scripts/fetch_chen2020.py` | **CC BY-NC-ND 4.0** (verified in the PDF text, 2026-11-22; see the single statement below) | raw text and segments were removed from git tracking; regenerate locally from an owner-supplied PDF |
| Benchmark fixtures & derived results | `data/eval/`, `results/p4/`, `results/p5/`, `data/registry/` | produced by this project (MIT, subject to underlying source terms noted per item) | include recorded provenance/qualifiers; raw model outputs preserved |

License evidence and sha256: `data/raw_documents/p5_sources/acquisition_manifest.json`.

### Chen2020 article licence — single statement (VERIFIED 2026-11-22)

- **Status: verified** from the article PDF's own first page (p. 2 of the
  owner-supplied file, sha256 pinned below). Verbatim statement:

  > © 2020 The Author(s). Published on behalf of The Electrochemical Society
  > by IOP Publishing Limited. This is an open access article distributed
  > under the terms of the Creative Commons Attribution Non-Commercial No
  > Derivatives 4.0 License (CC BY-NC-ND,
  > http://creativecommons.org/licenses/by-nc-nd/4.0/), which permits
  > non-commercial reuse, distribution, and reproduction in any medium,
  > provided the original work is not changed in any way and is properly
  > cited. For permission for commercial reuse, please email:
  > oa@electrochem.org. [DOI: 10.1149/1945-7111/ab9050]

- This resolves the earlier conflicting secondary statements: the University
  of Warwick repository's **CC BY-NC-ND 4.0** listing is confirmed by the
  document itself; the "ECS ©" phrasing (an all-rights-reserved assumption in
  earlier files) is superseded. The publisher-page check of **2026-11-19**
  (HTTP 500; DOI resolver returned citation metadata only) is retained as
  historical record.
- **Redistribution policy: unchanged.** The text stays **not redistributed**
  in this repository (fetched and verified locally). CC BY-NC-ND 4.0 would
  permit unmodified non-commercial redistribution with citation, but changing
  the distribution policy is an owner decision (`docs/REMAINING_TASKS.md`
  item 2).
- The article text was originally retrieved **2026-11-04** (recorded in
  `documents.json` before untracking).

### Local fetch of the Chen2020 article (no automatic download)

The full article text is **not redistributed**. Supply the publisher PDF
yourself and run `scripts/fetch_chen2020.py --pdf <path>`; the script verifies
the checksum before ingesting into `data/literature_store/` with the existing
ingest code. The generated raw text/segments and any local PDF are gitignored.

**Text-extract discrepancy (recorded 2026-11-22, disclosed not smoothed).**
The pypdf extraction of the owner-supplied PDF hashes to
`4c1bc8cd66ea471623dd54a88b4daec8a4ee4647c3735601803bfe23e834316c`
and does **not** reproduce the recorded text extract
`dffc1f9f532b9b899ce83caabcec711db154204db355f77e5a714d4ae28e07da`
(the difference is inline-formula glyph handling: the historical extract drops
equation glyphs; `pdftotext` variants do not reproduce it either). The
historical extract is the corpus of record — every committed v3 result and
every registry quote was produced against it — and is retained in git history
(raw blob `10f00ec297f12fc36dd9e837efa888707222d513`, segments blob
`98b528dc600caf1c25ee0fe3f7702dffe70c4f5b`). It is restored locally as
`data/literature_store/raw/chen2020_jes_167_080534.txt` (content sha256
`dffc1f9f…`, recorded in `documents.json`) and as the standalone
`data/raw_documents/chen2020_jes_167_080534/chen2020_jes_167_080534_fulltext.txt`
used for quote verification. Re-running `scripts/fetch_chen2020.py` after the
restoration is refused by the store's immutability guard (same document id,
different content) — that refusal is the intended protection.

Chen2020 article PDF sha256: 99d8f38a383e367aba5a8c3de74fdaf6ca9051842b0ddd75ca3ef1a238afb551
(owner-supplied publisher PDF; hash computed 2026-11-22 and confirmed by the
project owner). `scripts/fetch_chen2020.py` verifies the supplied file against
this value before ingesting. The sha256 of the previously tracked **text
extract** was
`dffc1f9f532b9b899ce83caabcec711db154204db355f77e5a714d4ae28e07da`
(recorded in `data/literature_store/documents.json` before untracking) and can
be used to check the regenerated text.

## NOT redistributed (acquire separately)

| material | status | how to obtain / note |
|---|---|---|
| Chen et al. 2020 supplementary PDF (JES 167 080534, DOI 10.1149/1945-7111/ab9050) | **removed from git tracking**; gitignored | ECS ©, redistribution permission not verified. Obtain from the publisher DOI and place at `data/raw_documents/chen2020_supplement/JES_167_8_080534_suppdata.pdf`; see `data/raw_documents/chen2020_supplement/ACQUISITION.md`. Derived benchmark items/results remain with provenance. |
| LG M50 experimental sample data (PyProBE) | **gitignored** (`data/external/`) — not in repo | Upstream license **UNRESOLVED** in this audit; the audited file is C/10 pOCV charge @ ~32.3 °C (ineligible for the T6 validation target). See `data/registry/dataset_audit_lgm50.json`, `docs/P5_DATA_ACQUISITION.md`. |
| Chen2020 original experimental traces | **UNRESOLVED / not present** | No in-repo copy; acquire via authors/publisher data availability + license verification before use. |

## Upstream software (attributed, not vendored as source here except via deps)

PyBaMM (**BSD 3-Clause**, verified), PyBOP (MIT), PyProBE-Data and their
transitive dependencies are installed from PyPI per the lockfiles; consult
their upstream LICENSE/NOTICE files in installed distributions. Verification
(2026-11-19, `.venv`, pinned PyBaMM 26.8.0.0):
`.venv/lib/python3.14/site-packages/pybamm-26.8.0.0.dist-info/licenses/LICENSE.txt`
begins "Copyright (c) 2018, the PyBaMM team. All rights reserved." and states
"Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:"
plus the three BSD conditions; package metadata classifier is
"License :: OSI Approved :: BSD License". An earlier line of this file called
PyBaMM MIT — that was wrong and is corrected here. PyBaMM's Chen2020
`ParameterValues` are loaded from the installed PyBaMM library (not hand-typed).

## Third-party code in this repo

Repository source is original to the project except where explicitly attributed;
no vendored third-party source files carrying separate copyright notices were
identified in `src/`/`tests/`/`scripts/`/`benchmarks/` during the release audit.
Characterization baselines reference upstream-derived numeric behavior for
regression gating (documented in `tests/characterization/`). If you add
third-party code, preserve its copyright/license notice and record it here.