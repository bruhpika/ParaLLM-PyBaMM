# Remaining tasks

Checklist of what is left after the retrieval-improvement programme. Status is
as of commit `c625e65` on `main`. Owner items are decisions, not engineering
work. See `docs/HANDOFF.md` for the full project state.

## Owner decisions (blocking)

- [ ] Fill the Chen2020 publisher-PDF sha256 TODO in
      `docs/DATA_PROVENANCE.md` (`Chen2020 article PDF sha256:`) and the
      supplement PDF hash TODO in
      `data/raw_documents/chen2020_supplement/ACQUISITION.md`. No hash was
      invented.
- [ ] Ingest the Chen2020 article locally with
      `scripts/fetch_chen2020.py --pdf <path>` after filling the hash. Required
      before any v3 live run; without it v3 fixtures drop 15 items.
- [ ] Resolve the Chen2020 article licence: currently **UNVERIFIED** (publisher
      page HTTP 500; Warwick lists CC BY-NC-ND 4.0, not independently checked).
- [ ] Review the 24 drafted applicability labels; the 0.958 agreement in
      `results/v2/applicability/summary.md` is provisional until signed off
      (closes V2.1).
- [ ] Resolve the 17 traceability flags (backfill quotes or correct statuses)
      listed in the assembly `report.json` (closes V2.2).
- [ ] Make the V2.5 extractor decision: evidence-layer work vs a controlled
      stronger-extractor re-run.
- [ ] Approve or reject the prepared TASK 6 live LLM + tuned-BM25 runs. If
      approved, run with `--live`, report the side-by-side, and do not tune on
      test.
- [ ] Decide whether to purge git history of the removed Chen2020 article and
      supplement full texts. No history rewrite was performed.
- [ ] Decide Zenodo record 4032561 eligibility for independent validation; no
      real-data claim is made until then.

## Engineering (gated or follow-up)

- [ ] After the live runs: report oracle vs BM25 baseline vs tuned BM25
      extraction side-by-side from committed results files.
- [ ] V2.5: implement the association-level condition<->value mechanism once
      the extractor decision is made. Current exit criterion is not met
      (0.310 / 0.058 vs target >= 0.5 / 0.000).
- [ ] V2.6: open the closed loop only after V2.1/V2.2 owner items and the V2.5
      exit criterion are met.
- [ ] V2.7: PyPI publish (credentials + version decision), docs site, examples
      gallery, v4a mini-benchmark.
- [ ] Update `docs/HANDOFF.md` and `CHANGELOG.md` after each completed
      milestone.

## Prepared commands (do not run without approval)

```bash
PYTHONPATH=src:benchmarks/v2 .venv/bin/python \
  benchmarks/v2/prepare_live_retrieval.py --benchmark both --repeats 3
export PYCL_LLM_API_KEY=... PYCL_LLM_MODEL=... PYCL_LLM_BASE_URL=...
.venv-ecosystem312/bin/python benchmarks/p5/run_ablation.py \
  --condition retrieval_bm25_tuned_strict --repeats 3 --live
.venv-ecosystem312/bin/python benchmarks/v2/run_v4_evaluation.py \
  --modes retrieval_tuned --repeats 3 --live
```

Dry-run estimates: v3 22 local items / 66 calls; v4 30 items / 90 calls. After
the article ingest, v3 covers 37 items / 111 calls. No model call or download
has been made for these runs.
