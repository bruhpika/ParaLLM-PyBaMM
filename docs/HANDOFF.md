# PARALLM handoff for the next agent

This file is the single starting point for an agent continuing the project.
It states the aim, scientific constraints, stack, current stage, completed
work, sourced numbers, open decisions and next steps. Read the cited files
before acting; every number here comes from a committed results file.
The actionable checklist is in `docs/REMAINING_TASKS.md`.

## 1. Aim and scientific stance

PARALLM is a research framework for parameterizing physics-based lithium-ion
battery models built on PyBaMM. Its unit of work is the **per-parameter
dossier**: literature evidence -> applicability/conflict assembly -> dossier
with a mandatory human approval gate -> observability-based
CALIBRATE/FIX/MEASURE decisions.

Non-negotiable scientific rules (`AGENTS.md`) include: never invent
electrochemical parameter values or PyBaMM APIs; distinguish user-supplied /
literature-derived / calculated / assumed / calibrated / unresolved values;
optimization success is not identifiability; synthetic recovery is not
experimental validation; calibration and validation data must stay disjoint;
an LLM may never overwrite scientific parameters without deterministic
validation and explicit approval.

**No experimental validation is claimed.** Real-data work is blocked until an
eligible, licensed dataset passes the audit.

## 2. Stack and environments

- Core: Python 3.10-3.15, `pybamm==26.8.0.0`, numpy 2.x, scipy, pandas,
  pydantic, PyYAML, matplotlib; lockfiles in `requirements/`.
- Ecosystem: CPython 3.12.16, PyBOP 26.10, PyProBE-Data 2.6.1, pypdf, polars;
  `.venv-ecosystem312`.
- Optional dense retrieval: `.venv-dense` (fresh venv, Python 3.12.16) with
  `torch==2.15.0+cpu` from the CPU-only index and `sentence-transformers==5.7.0`.
  Model `sentence-transformers/all-MiniLM-L6-v2`, 90,868,376-byte
  `model.safetensors`, Apache-2.0, pinned commit
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; cache under gitignored `.cache/`.
- Optional extras: `ecosystem`, `retrieval-dense` in `pyproject.toml`. Core
  install and CI must pass without optional extras.
- Software licence: MIT for code only; third-party documents have separate
  provenance (`docs/DATA_PROVENANCE.md`). PyBaMM code is BSD 3-Clause
  (verified from installed `LICENSE.txt`).

## 3. Current stage

v0.1.0-beta.1 is released (P0-P5). v0.2 is in progress. Milestone status from
`docs/ROADMAP_V0.2.md` and `docs/V2_EXECUTION_PLAN.md`:

- V2.1 applicability engine: implemented; 24 expert labels are **owner-approved**
  (2026-11-20); agreement 0.958 (`results/v2/applicability/summary.md`).
- V2.2 dossier/assembly CLI: implemented; 36/36 recorded quotes verify;
  traceability 79/96, 17 flagged records need the Chen2020 article PDF (see
  `docs/REMAINING_TASKS.md` item 1).
- V2.3 identifiability join: done; V2.4 synthetic end-to-end validation: done.
- V2.5 evidence engineering: **exit criterion not met** (best condition
  accuracy 0.310, invented 0.058 vs target >=0.5 / 0.000;
  `results/v2/v4/summary.md`); owner delegated the extractor decision and
  evidence-layer work was chosen (deterministic association-level mechanism).
- V2.6 closed loop: hard-gated on the V2.5 exit criterion; not started.
- V2.7 productisation: CI + packaging landed; docs site and examples gallery
  in progress; PyPI publish and v4a remain open.

## 4. Completed work in this session

All branches were merged into `main` at commit `e2cc7ab` and pushed.

### Post-handoff fixes (2026-11-20)

- CI clean-checkout fix: v4 tests skip when the git-ignored private fixture is
  absent (`85dc281`); all five jobs green (run 44710982968).
- README oracle label corrected to "location oracle, not a performance upper
  bound" (`3ea7724`).
- Added the missing V2.4 held-out RMSE figure and its generator (`ad18a9c`).
- Current docs and the `ORACLE_LABEL` constant now use the clarified label;
  committed v4 summaries retain the pre-clarification wording.

### General engineering / licensing

- `task/a-readme-v02`: README rewritten with sourced results and honest limitations.
- `task/b-live-guard`: live model calls require `--live`; raw outputs protected
  by `--overwrite`/timestamped dirs; replay mode; git commit in metadata.
- `task/c-no-global-rng`: explicit `default_rng`, isolated legacy state.
- `task/d-harder-synthetic`: perturbed generating model, multiple truths and
  noise levels; result 15/18 positive beats baseline, 18/18 negative does not
  (`results/v2/synthetic_validation_mismatch/summary.md`); SYNTHETIC only.
- `task/e-retrieval-distractors`: full-corpus recall stress test
  (`results/v2/v4/retrieval_recall_distractors.md`).
- `task/1-untrack-supplement`, `task/2-fetch-chen2020`, `task/3-licence-docs`:
  untracked Chen2020 full texts; added fetch+verify script and clean skips;
  article licence marked UNVERIFIED (publisher page HTTP 500; Warwick lists
  CC BY-NC-ND 4.0); PyBaMM licence corrected to BSD 3-Clause.
- Zenodo record 4032561 was audited **report only**: CC BY 4.0 metadata,
  three LG M50 CSVs, near-match but not a verified held-out set.
- Read-only Task F licensing report remains in the conversation; no files were
  deleted outside the approved list and no git history was rewritten.

### Retrieval improvement programme

- TASK 1 (`task/retrieval-1-protocol`): frozen stratified dev/test split
  (`configs/retrieval/dev_test_split.json`, seed 20261119), leakage tests,
  recall@k/MRR/document-recall with bootstrap CIs, config log, baseline
  (`results/v2/retrieval_improvement/baseline.{json,md}`).
- TASK 2 (`task/retrieval-2-lexical`): 11 dev-only lexical variants; plain
  expansion did not help; tuned BM25 `b=0.5, k1=1.5` won
  (`configs/retrieval/lexical_config.json`,
  `lexical_ablation.{json,md}`).
- TASK 3 (`task/retrieval-3-dense`): approved local model pinned; preflight
  (`segment_length_preflight.{json,md}`), dense/hybrid dev then test once;
  **hybrid did not beat tuned BM25 on test** (`hybrid.{json,md}`).
- TASK 4 (`task/retrieval-4-scaling`): recall vs corpus size with synthetic
  distractors (`corpus_scaling.{json,md,png}`).
- TASK 5 (`task/retrieval-5-wire`): tuned BM25 offline arms in P5/v4;
  side-by-side (`offline_side_by_side.{json,md}`).
- TASK 6 (`task/retrieval-6-prepare`): oracle label clarified
  (`offline_side_by_side_v2.{json,md}`, `docs/V2_PRIVATE_V4_BENCHMARK.md` §7.5),
  v4 split tables, dry-run planner (`benchmarks/v2/prepare_live_retrieval.py`).
  No live run was executed.

## 5. Sourced numbers to reuse (do not re-derive by hand)

- Core test scope: 397 passed, 15 skipped, 3 deselected (measured on `main`).
- v3 BM25 gold-passage recall@1/3/5/10 = 0.189 / 0.351 / 0.459 / 0.486
  (`results/p5/benchmark_v3/retrieval_recall.md`).
- v4 small recall = 0.300 / 0.867 / 0.900 / 1.000; full corpus =
  0.000 / 0.167 / 0.367 / 0.767
  (`results/v2/v4/retrieval_recall_distractors.md`).
- v4 offline test split (n=15): value found oracle 0.333, BM25 0.733, tuned
  0.733; condition accuracy 0.190 / 0.248 / 0.257
  (`results/v2/retrieval_improvement/offline_side_by_side_v2.md`).
- Oracle is a **location oracle, not a performance upper bound**: oracle
  compact gets ~561 chars; BM25 arms get ~43-46k chars (~81x), same source.
- Hybrid vs tuned BM25 on test: hybrid does not win; see `hybrid.md`.
- Synthetic end-to-end mismatch: 15/18 positive beats baseline; 18/18 negative
  does not (`results/v2/synthetic_validation_mismatch/summary.md`). Figure for
  both the 5-seed stability and 18-run mismatch panels:
  `results/v2/synthetic_validation/heldout_rmse.png`.

## 6. Hard operating rules for the next agent

- No paid/live LLM API call without explicit owner approval. If needed, print
  command, env vars and call count, then wait.
- Any model download needs approval first (model name, size, licence).
- Never hand-edit `results/`; generate files with scripts and cite paths.
- Do not change committed fixtures, gold labels or existing results files.
  New outputs go to new files.
- One task per branch, small commits; after each task run
  `ruff check src/ benchmarks/ tests/` and
  `pytest -q -m "not benchmark and not characterization"`; add tests and a
  CHANGELOG entry; then stop and report.
- Do not rewrite git history, force-push or use filter-repo/BFG.
- No emojis.
- Recall/evaluation queries must never use `probe`, `passage_probe`, gold
  conditions, target document id or gold value; the probe is only a
  post-retrieval label. Leakage tests enforce this.

## 7. Open owner decisions (blocking)

Owner decisions recorded 2026-11-20 are applied in
`docs/REMAINING_TASKS.md`. Remaining open:

1. Fill the Chen2020 publisher-PDF sha256 TODO in `docs/DATA_PROVENANCE.md`
   (line with `Chen2020 article PDF sha256:`); `scripts/fetch_chen2020.py`
   refuses until a real 64-hex value is present. Supplement PDF hash TODO in
   `data/raw_documents/chen2020_supplement/ACQUISITION.md`.
2. Article licence remains UNVERIFIED; decide whether to seek a citable
   publisher statement or keep the fetched-only policy.

Recorded decisions: the 24 drafted applicability labels are owner-approved;
V2.5 continues with evidence-layer work; the prepared live runs are approved
but blocked on `PYCL_LLM_*` env vars; git history is retained (no rewrite);
Zenodo 4032561 is not eligible as independent validation.

## 8. Next step: prepared live runs (DO NOT RUN without approval)

Dry-run command (no model client, no API call):

```bash
PYTHONPATH=src:benchmarks/v2 .venv/bin/python \
  benchmarks/v2/prepare_live_retrieval.py --benchmark both --repeats 3
```

Env vars required for live runs: `PYCL_LLM_API_KEY`, `PYCL_LLM_MODEL`,
`PYCL_LLM_BASE_URL`. Dry-run token estimate uses chars/4 and no tokenizer
download. Current dry-run estimates: v3 22 locally available items, 66 calls,
~158.5k prompt tokens/run (~475.5k total); v4 30 items, 90 calls, ~366.2k
tokens/run (~1.099M total).

**The v3 live run requires the local Chen2020 article ingest first**:
fill the PDF hash TODO, supply the publisher PDF, then run
`scripts/fetch_chen2020.py --pdf <path>`; after ingest v3 covers 37 items /
111 calls and the dry-run should be repeated for an exact token estimate.

Prepared live commands (each needs owner approval and `--live`):

```bash
export PYCL_LLM_API_KEY=... PYCL_LLM_MODEL=... PYCL_LLM_BASE_URL=...
.venv-ecosystem312/bin/python benchmarks/p5/run_ablation.py \
  --condition retrieval_bm25_tuned_strict --repeats 3 --live
.venv-ecosystem312/bin/python benchmarks/v2/run_v4_evaluation.py \
  --modes retrieval_tuned --repeats 3 --live
```

Outputs: `results/p5/benchmark_v3/raw_outputs_retrieval_bm25_tuned_strict_r{0,1,2}.jsonl`,
`aggregate_retrieval_bm25_tuned_strict.json`; private
`data/private_v4/results/raw_retrieval_tuned_r{0,1,2}.jsonl`, public
`results/v2/v4/summary.json`. Raw outputs are protected by the live guard.

## 9. After the live runs

- Report oracle vs BM25 vs tuned LLM extraction side-by-side; do not tune on
  test. A null result is acceptable.
- Then continue with V2.5's association-level mechanism for
  condition<->value binding; keep V2.6 gated until V2.1/V2.2 owner items close.
- Update this handoff and `CHANGELOG.md` after every milestone.
