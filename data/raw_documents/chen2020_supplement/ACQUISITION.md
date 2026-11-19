# Chen2020 supplementary data (not redistributed)

The supplementary PDF for Chen et al., "Development of Experimental Techniques
for Parameterization of Multi-scale Lithium-ion Battery Models", J.
Electrochem. Soc. 167 080534 (2020), DOI 10.1149/1945-7111/ab9050, is **not
redistributed** in this repository because redistribution permission was not
verified (ECS copyright). It was removed from git tracking in release commit
`25526f1`. Its derived full text and segment index were removed from tracking
in the licensing clean-up; neither should be committed.

## How to obtain and ingest it locally

1. Obtain the supplementary PDF from the publisher's supplementary materials
   for DOI 10.1149/1945-7111/ab9050 (normally named
   `JES_167_8_080534_suppdata.pdf`).
2. Place it at
   `data/raw_documents/chen2020_supplement/JES_167_8_080534_suppdata.pdf`
   (this path is gitignored).
3. Ingest it into the **local** store with the existing PDF ingest path:

   ```bash
   .venv-ecosystem312/bin/python -c '
   from pathlib import Path
   from pybamm_closed_loop.literature.ingest import DocumentStore
   DocumentStore(Path("data/literature_store")).ingest_pdf(
       "chen2020_supplement_s1",
       Path("data/raw_documents/chen2020_supplement/JES_167_8_080534_suppdata.pdf"),
       kind="supplement",
       title="Supplementary data for: Development of Experimental Techniques for Parameterization of Multi-scale Lithium-ion Battery Models",
       doi_or_url="10.1149/1945-7111/ab9050 (supplementary)",
       retrieved="2026-11-08",
       meta={"page_numbering": "1-based PDF page indices (pypdf)"},
   )'
   ```

   This writes `data/literature_store/raw/chen2020_supplement_s1.txt`,
   `data/literature_store/segments/chen2020_supplement_s1.json` and an entry in
   `data/literature_store/documents.json`. Do not commit those files.

## Expected hashes

The extracted text previously tracked in `documents.json` had
sha256 `80f2c08bc079ebe63070d181a46a23e68f837cfdbacb6f657f7381bd062e81dd`.
Compare the locally generated
`data/literature_store/raw/chen2020_supplement_s1.txt` against this value before
reproducing supplement-derived benchmark items.

No sha256 for the supplementary **PDF** was recorded in the repository or in
the Task F licensing report. **TODO (owner to fill):** record the expected PDF
sha256 here after the owner verifies an acquired copy.

The benchmark fixture items and recorded extraction results derived from the
supplement remain in-repo as research artifacts with provenance; the source
file itself is excluded from distribution. Benchmarks and tests that need the
supplement skip with an explicit reason when the local ingest has not been
done.
