# Changelog

All notable changes to PARALLM are documented here. The project retains the
PRD phase names (P0–P8) for historical mapping; the *shipped* v0.1 feature set
is milestones P0–P5, and v0.2 work is tracked as V2.x (see
`docs/ROADMAP_V0.2.md` §9). Scientific behavior is versioned conservatively and
documented with provenance.

## [Unreleased] — v0.2 "Parameter Assembly" (in execution)

Scope, exit criteria, risks and decisions: `docs/ROADMAP_V0.2.md`.
Positioning/competitive scan: `docs/POSITIONING.md`. Milestone plan:
`docs/V2_EXECUTION_PLAN.md`.

### README rewritten for v0.2 (documentation only)

- Replaced the marketing tagline with a scoped, non-overclaiming one; reframed
  the document around the v0.2 pipeline (literature evidence → applicability/
  conflict assembly → per-parameter dossier + human gate → observability-based
  CALIBRATE/FIX/MEASURE). Kept it short and sourced every figure in the Results
  section from a committed `results/` file, cited inline.
- Replaced the stale "184 passed / 201 passed" (release commit `bec653d`)
  counts with a measurement at the current HEAD: **334 passed, 7 skipped**
  (3 characterization tests deselected), core `.venv`, CPython 3.14.8, command
  `.venv/bin/python -m pytest -q -m "not benchmark and not characterization"`.
  The brief's stated "332 passed / 9 skipped" could not be reproduced in any
  local env; it differs by exactly 2 passes → skips and is **not written into
  docs** because it is not from a committed results file or a command run here.
- Added the required oracle-located vs real-BM25 side-by-side (v3 deterministic
  extractor), the v3/v4 recall table, an explicit "oracle = upper bound"
  statement, the v4 easy-corpus caveat, and the synthetic-only V2.4 result.
  Limitations now state: no experimental validation, synthetic mismatch only,
  private v4 not reproducible, scorer revised post-hoc (not pre-registered),
  observability limited to protocols in `results/p2/`.
- Contradictions fixed (all in README.md): (1) old tagline "Parameters — not a
  problem anymore" removed (marketing overclaim already dropped from the package
  description); (2) "184/201 passed" + release-commit scope → measured counts;
  (3) "retrieval + strict" described as a ±260-char probe window but presented
  as retrieval → relabelled **oracle-located (upper bound)** throughout;
  (4) milestone naming reconciled — v0.2 work is V2.x (ROADMAP §9), not P6+;
  (5) future-tense "What's next" framing of dossiers, rubric, human gate,
  observability and synthetic validation → implemented status (V2.1–V2.4
  landed), with V2.5/V2.6/V2.7 status; (6) "public beta v0.1.0-beta.1" only
  status → v0.1 beta released + v0.2 in progress; (7) `retrieval_strict` arm
  label in the v3 table → "oracle-located (upper bound): retrieval_strict";
  (8) duplicated "Where PARALLM fits" / "What's next" sections condensed.
  No other files changed; no scientific number changed.
### Live-run guard and raw-output safety (2026-11-19)

- **Live model calls are now opt-in.** All four runners that can construct a
  model client (`benchmarks/p3/run_extraction_benchmark.py`, `p4/run_llm_evaluation.py`,
  `p5/run_ablation.py`, `v2/run_v4_evaluation.py`) refuse to run a live arm
  without `--live`; they exit with a clear message before any client is built.
  `--rescore`/`--replay` (and p5's `--summary-only`/`--repair-metadata`, v4's
  `--aggregate-only`) stay network-free and need no API key. Offline arms are
  unaffected. No live API call was made while implementing this.
- **Raw outputs are never silently clobbered.** Shared `eval/run_guard.py`:
  `LiveRunPolicy.raw_path()` redirects a live run to a fresh `live_<UTC-stamp>/`
  directory when the target raw file already exists and `--overwrite` was not
  given; `find_raw()` lets replay locate either the original or a redirected
  file. `--force` on v4 remains an alias for `--overwrite`.
- **Live run metadata records the exact model id, base URL, date and git
  commit** (`LiveRunPolicy.metadata()` uses `git rev-parse HEAD`; `None` outside
  a checkout). Added to P3/P4/P5 run metadata and the v4 `extractor` block; the
  raw path actually used is recorded for traceability.
- **Replay is available for every model-calling runner.** P3 gained a verbatim
  raw-output cache and `rescore_benchmark()` (`eval/benchmark.py`) so its
  `--replay` re-scores frozen extractions with no client, network or key; P4/P5/v4
  accept `--replay` as an alias of `--rescore`.
- **Tests** (`tests/unit/test_live_run_guard.py`, 13 new): fake clients prove no
  client is constructed or called without `--live` in any runner; redirected vs
  overwritten raw paths; metadata fields; replay without an API key; and a live
  P3 run with a fake client proving a second run creates a timestamped directory
  instead of clobbering. Verification: ruff clean; core scope 347 passed,
  7 skipped (3 characterization deselected), core `.venv` CPython 3.14.8.
### No global numpy RNG state (2026-11-19)

- **Removed all `np.random.seed()` calls** from library code and the synthetic
  benchmark. New `calibration/rng.py` provides `isolated_numpy_seed(seed)` (a
  context manager that saves/restores `np.random.get_state()`) and
  `legacy_seed(rng)` for third-party APIs that expose no generator argument.
- `calibration/synthetic.py`: `generate_dataset` / `generate_datasets` accept an
  explicit `rng: numpy.random.Generator`; a `default_rng` is derived from the
  per-condition seed otherwise. `pybop.add_noise` (verified against PyBOP
  26.10 to use global `np.random.normal`) runs under the isolated seed; the
  historical bit stream is preserved and `rng_seed_used` is recorded.
- `calibration/identifiability.py`: `sobol_indices` accepts an explicit `rng`;
  SALib 1.6.0's `saltelli.sample` exposes no seed argument, so it runs under the
  isolated seed. `benchmarks/identifiability/run_identifiability.py` wraps the
  PINTS MCMC draw the same way.
- **Tests**: `tests/unit/test_rng_isolation.py` (5 core tests: state restored on
  success and on exception, explicit-generator reproducibility, SALib isolation
  via a fake module) and 2 pybop-gated tests in `test_calibration_synthetic.py`
  (global state unchanged, explicit generator reproducible). The existing
  same-seed / different-condition-noise tests continue to pass.
- **Characterization checked, not regenerated**: `test_char_p2_recovery.py`
  produces byte-identical numeric values before (main `e43910f`) and after this
  change in `.venv-ecosystem312` (estimate 0.7377946795097997, final_cost
  3.986404e-04, etc.); only runtimes differ. The two characterization failures
  are pre-existing on main. Verification: ruff clean; core scope 339 passed,
  7 skipped (3 deselected); ecosystem scope 359 passed, 6 deselected.

### Retrieval arms (2026-11-19)

- **Oracle vs real retrieval separated.** The probe-based evidence path is now
  labelled **oracle-located (upper bound)** in the harness, public summaries and
  docs; it is not described as retrieval. Added a real BM25 arm that queries the
  complete document store from v3 `RetrievalFacets` or v4 parameter name/unit
  only — no probe, target document, printed/gold value or gold condition enters
  the query or evidence selection.
- **BM25 indexing:** deduplicated expanded terms and added an inverted index
  without changing ranking on the existing tests; tightened multi-word alias
  triggering so a generic shared token cannot expand an unrelated synonym group.
- **Recall reporting:** new no-API script
  `benchmarks/v2/report_retrieval_recall.py` (gold probe used only as a
  post-retrieval label). v3 recall@1/3/5/10 = **0.189 / 0.351 / 0.459 / 0.486**;
  private v4 = **0.300 / 0.867 / 0.900 / 1.000**. Per-item v4 audit remains
  private; public aggregates are in `results/{p5/benchmark_v3,v2/v4}/retrieval_recall.*`.
- **End-to-end side-by-side:** added `offline_bm25` (deterministic extractor,
  no API) and the LLM `retrieval_bm25_strict` / v4 `retrieval` arms. Replay is
  offline via `--rescore` and records model, base URL and date in run metadata.
  The deterministic v3 oracle→real comparison shows value extraction
  **0.500 → 0.386**, provenance **1.000 → 0.773**, false extraction
  **0.000 → 0.195**. The LLM real-retrieval arms are implemented but **not run**
  (no live API call made); no LLM oracle-vs-real extraction numbers are claimed.

### Landed so far (2026-11-17)

- **V2.5 (third slice) — verification pass + `not_stated` discipline**
  (`eval/benchmark_v4.py`): every candidate's quote is checked against the
  evidence actually shown; a stated condition with no trace in the evidence is
  replaced by `not_stated` (temperature within 1 K of an extracted temperature;
  chemistry/cell/format/method tokens present; SOC/protocol numbers as
  standalone tokens). Shared verbatim by the live runner and the new offline
  `run_v4_evaluation.py --rescore` path (no model calls). Scored twice: the
  disciplined verdict plus `raw_*` verdicts, so the effect is measured.
  **Measured effect (disclosed):** it fires (3.5–14.7 conditions/item dropped,
  quote verification 0.991–1.000) but removed **none** of the 119 invented
  claims (their tokens do occur in the evidence) and slightly *lowered*
  condition accuracy (19 verdicts changed, all losing). Also landed: cell
  identification evidence (`cell_tokens`, `cell_identification_sentences`) and
  the SOC numeric false-positive fix (`50` inside `INR21700-50E`).
- **Private v4 re-scored** (same raw outputs, corrected fixture chemistry gold
  labels, discipline pass; canonical source of truth
  `results/v2/v4/summary.md`): condition-field accuracy **0.144 ± 0.016
  (compact) → 0.294 ± 0.018 (expanded) → 0.310 ± 0.022 (v25)** [raw,
  pre-discipline: 0.165 / 0.300 / 0.320]; value found 0.389 → 0.389 → 0.583;
  invented conditions **0.067 → 0.200 → 0.058** (richer windows raise
  invention from compact to expanded; the v25 table context lowers it below
  compact). The earlier "chemistry never recovered" finding reflects the
  pre-correction fixture; corrected chemistry is 0.000 / 0.178 / 0.143.
  Roadmap exit criterion (≥0.5 completeness, false extraction 0.000) **not
  met**. The pre-scorer-fix numbers are superseded (see 2026-11-19 below).
  Aggregates: `results/v2/v4/`.
- **V2.1 — applicability rubric v2** (`assembly/rubric.py`,
  `configs/v2/rubric_v2.yaml`): new `cell_product` and `electrolyte`
  dimensions (sum still 1.00; `ELECTROLYTE_WEIGHTS` variant for
  electrolyte-family parameters; blocking rule for cell-specific cell-product
  mismatches). `configs/v2/rubric_v1.yaml` removed; the target spec records
  the cell product and electrolyte families.
- **V2.1 — expert-agreement case set + benchmark**: 24 labelled
  conflict/applicability cases (**private**, git-ignored; labels drafted,
  pending owner review) scored by `benchmarks/v2/run_applicability.py`:
  decision agreement **0.958** (≥80% exit threshold), 1 mismatch
  (`APP-AMB-exchange-current-density`, ambiguous class 1/2). Public aggregates:
  `results/v2/applicability/`.
- **Assembly resolve/report fixes**: evidence-dimension checks now require
  *all* blockers evidence-related (was *any*); a single surviving candidate
  with rejections is no longer reported conflict-free; non-numeric single
  survivors no longer crash the ranking; per-case agreement now reports
  distinct sources instead of a constant conflict count.
- **Docs: external corroboration cited.** The v4 negative findings (trace
  check cannot remove invented conditions; counteracting needs condition↔value
  association) are now referenced against the published literature —
  cross-context numeric contamination as a known LLM failure mode
  (Yaghi-group LLM comparison), source-tracked multi-stage extraction as the
  documented remedy (MetMINE, *RSC Digital Discovery* 2026; arXiv:2510.05142),
  and condition binding as the bottleneck for value+condition tuples (Phi et
  al., WASP 2025). Citations, quoted findings and an explicit
  non-comparability caveat: `docs/V2_PRIVATE_V4_BENCHMARK.md` §9 and
  `docs/ROADMAP_V0.2.md` §3.2.
- **V2.2 — dossier & assembly report CLI**: `parallm assemble` (`cli.py`,
  new `[project.scripts]` entry) renders the 9-field per-parameter dossiers
  as JSON + Markdown + a PyBaMM-style export + a reproducibility manifest
  (tool versions, rubric version, registry/config SHA-256, quote-verification
  counts). Deterministic quote verification against the archived full texts
  (`verify_record_quotes`) and a `check_traceability` acceptance gate (a
  selected value must trace to a *verified* quote or carry an explicit status
  flag). The mandatory human gate (D6) is enforced: without a gate file the
  export is empty by design. Measured on the real 96-record registry:
  decisions 29 USE / 67 FIX (7 same-source conflicts preserved), **all 36
  recorded quotes verify**, traceability **79 ok / 17 fail** — the 17 flags
  are `LITERATURE_DERIVED` values with no recorded quote (owner decision:
  backfill quotes or correct statuses; listed in `report.json`).
- **V2.3 — identifiability (observability) join**: `assembly/observability.py`
  deterministically joins the recorded P2 artifacts (`results/p2/`:
  per-protocol normalized sensitivities; parametric-bootstrap std, FIM
  condition numbers, profiles, Sobol) into dossier field 7 and a
  fit/fix/measure action matrix, and upgrades decisions (rule-firing recorded
  in the rationale): observable → `CALIBRATE`; unobservable → `FIX` or
  `MEASURE` when explicitly `--accuracy-critical`; REJECT/REVIEW never
  upgraded; uncovered parameters stay `not_assessed`. Explicit recorded
  thresholds (assumptions, in every assessment + manifest): mean |normalized
  sensitivity| < 0.05 → unobservable; bootstrap relative std > 5 % →
  unobservable. **Acceptance met**: the report reproduces the P2 finding —
  `neg_particle_diffusivity` UNOBSERVABLE under 0.5C/1C/2C (mean |S| =
  0.011/0.021/0.048) → FIX, or MEASURE when accuracy-critical. Measured on
  the real registry: 7/96 assessed (6 CALIBRATE, 1 MEASURE/FIX), 89 explicit
  `not_assessed`.
- **V2.4 — synthetic end-to-end validation**: `benchmarks/v2/run_synthetic_validation.py`
  (run under `.venv-ecosystem312`; committed run in
  `results/v2/synthetic_validation/`, labelled SYNTHETIC): assemble (real
  registry + observability join) → deliberately mismatched synthetic ground
  truth → seeded synthetic data at 0.5C/1C/2C → baseline held-out validation
  → positive control (fit the CALIBRATE-action observable pair on 1C) →
  negative control (fit the unobservable `neg_particle_diffusivity` on 1C,
  violating the decision). Measured (5 seeds): held-out mean voltage RMSE
  **4.4 ± 0.1 mV baseline → 1.1 ± 0.1 mV positive (4×) → 4.4 ± 0.1 mV
  negative (no gain)**; all fits converged; **prediction reproduced on 5/5
  seeds** (V2.6 gate "stable across repeats" item). Not experimental
  validation and not proof of identifiability (rules 7/8).

### Landed so far (2026-11-16)

- **V2.5 (second slice) — private v4 condition benchmark**: 30 items over three
  CC BY papers (Schmitt 2023 JES, Tuchel 2026 JES, Wheeler 2024 Batteries),
  categories A–E (separated conditions, table-dependent interpretation, multiple
  conditions, same-parameter/different-value, condition genuinely absent).
  Corpus, fixture and per-item results stay **private** (git-ignored); only the
  harness, the scorer and the aggregates are public. Frozen scorer: a gold
  `not_stated` field is matched only when the extraction reports nothing there;
  transport failures are excluded (not counted as abstentions); printed values
  are coerced to numbers by a deterministic rule applied to every arm.
- **V2.5 evidence layer, second slice**: table-aware chunking (caption/header/
  footnotes with the rows), top-k de-duplicated multi-window retrieval.
- **Private v4 first-pass result** (superseded by the 2026-11-17 re-score and
  the 2026-11-19 scorer fix; current numbers in the 2026-11-17 entry),
  3 repeats/arm (extractor `gemini-flash-lite-latest`, free tier; arms
  comparable with each other, **not** with the v0.1/v3 numbers):
  condition-field accuracy **0.111 ± 0.009 (compact) → 0.240 ± 0.004 (expanded)
  → 0.249 ± 0.022 (v25)**; value found 0.389 → 0.389 → 0.583; temperature
  0.059 → 0.479 → 0.591; format 0.219 → 0.980 → 0.976. Negative findings
  disclosed: **chemistry never recovered (0.000 in every arm — later corrected
  with the fixture's chemistry gold labels, see 2026-11-17)**, protocol ≤ 0.091,
  `v25` regresses on cell identity (0.360 → 0.186), and invented conditions
  **rise** with richer evidence under the pre-fix scorer (0.411 → 0.500 →
  0.439; superseded — current 0.067 → 0.200 → 0.058). Design + results:
  `docs/V2_PRIVATE_V4_BENCHMARK.md`.

### Landed so far (2026-11-08)
- **V2.5 (first slice) — evidence engineering**: condition-aware evidence window
  (±900 chars + condition-bearing sentences) and document-level experimental-setup
  retrieval, verbatim and deterministic (`literature/evidence.py`); wired into the
  P5 harness as `--evidence-mode {compact,expanded}` (default `compact` — the
  committed v3 results stay reproducible). Deterministic evidence-side metric
  (`benchmarks/v2/measure_condition_coverage.py`): temperature availability
  0.108 → 0.838, SOC 0.108 → 0.757, chemistry 0.243 → 0.838, method 0.649 → 1.000
  (share of the 37 v3 items whose evidence block contains each condition class).
  The LLM-side effect is still to be measured on a private v4.
- **V2.1/V2.2 (prototypes) — assembly layer**: auditable hand-set rubric with
  blocking rules (chemistry-family mismatch, failed quote verification,
  non-declarable parameter), same-source vs cross-source conflict resolution,
  and the **per-parameter dossier as the central artifact** (nine mandatory
  fields: selected value · original literature value · verified quotation and
  page · experimental conditions · alternatives/conflicts · applicability
  rationale · identifiability assessment · final recommendation · human approval
  status) plus the mandatory human approval gate. Over the real 96-record
  registry: 96 dossiers, 7 same-source conflicts all resolved to the source's
  operative value with the alternative preserved, no spurious escalations.

### Fixed (2026-11-17)

- **`registry/units.py`**: removed the silent `"C" -> ("K", 1.0)` mapping, which
  misread Celsius as kelvin and collided with coulomb / C-rate; `to_canonical("C")`
  now raises an explicit KeyError (units table is multiplicative-only, so Celsius
  cannot be expressed without an offset).
- **`validation/checks.py`**: parameter-name matching is token-based (tokens of
  length > 2, stopword-filtered, subset either direction) instead of bidirectional
  substring matching, so short names (e.g. `"D"`) no longer match arbitrary
  records; ambiguous mappings (one extraction → multiple registry records) are
  reported as warnings instead of being silently resolved to the first record.
- **`literature/ingest.py`**: heading detection fixed — table/figure captions are
  tracked, short title-like lines are headings, but full sentences ending in
  sentence punctuation are no longer mistaken for headings.
- **`calibration/synthetic.py`**: noise is drawn under a per-condition seed
  derived deterministically from `spec.seed` and the condition name (recorded as
  `noise_seed` alongside `seed`), so conditions get independent noise instead of
  reusing the same global draw.
- **`calibration/identifiability.py`**: `fim_diagnostics` accepts parameter
  values `x` and scales the Jacobian to dimensionless sensitivities before the
  FIM, so eigenvalues and condition number are comparable across units
  (`run_identifiability` passes `x_hat`; `correlation` was already scale-invariant).
- **`calibration/fitting.py`**: `run_fit_with_result` records the optimiser
  success flag and status from the wrapped scipy result (`success`/`status` in
  the report) instead of comparing `final_cost` blindly; the recovery benchmark
  prefers converged multi-start runs.

### Fixed (2026-11-19)

- **V2.4 multi-seed stability**: `run_stability()` + `--n-seeds` (default 5);
  the synthetic validation's predicted pattern reproduces on **5/5 seeds**
  (held-out RMSE baseline 4.4 ± 0.1 mV → positive control 1.1 ± 0.1 mV →
  negative control 4.4 ± 0.1 mV, all fits converged) — closes the V2.6
  "stable across repeats" gate item.
- **V2.5 scorer false-positive — protocol claims from abstaining contexts**
  (`eval/benchmark_v4.py`): any non-empty free-text context counted as a
  protocol claim, so the model's explicit abstentions ("measurement protocol
  are not stated") were scored as invented conditions — **94 of 110**
  invented claims under the old rule. `_context_slice` now requires a
  protocol cue (C-rate/GITT/EIS/pulse/rest/cutoffs/…) and rejects negated
  claims; affects scoring and the `not_stated` discipline identically.
  Offline re-score of the canonical run: invented rate **0.411 → 0.500 →
  0.439 becomes 0.067 → 0.200 → 0.058**, protocol field **0.000/0.080/0.091
  becomes 0.607/0.619/0.743**, condition accuracy **0.095/0.251/0.256
  becomes 0.144/0.294/0.310** (abstentions now correctly matched). The old
  numbers are superseded in `results/v2/v4/` and all docs.
- **Private v4 raw-data discipline**: an unauthorised live re-run
  (2026-11-17 14:03–14:49) had overwritten 8 of 9 raw files (one left with 12
  rate-limit/DNS transport errors). The clobbered run is preserved untouched
  under `data/private_v4/results_rogue_20261117/`; the canonical run was
  restored md5-identical from the pre-chemfix backup and every subsequent
  re-score runs against it (transport errors back to compact 0 / expanded 0 /
  v25 6).
- **Evidence-section lock-in test**: expanded/v25 evidence blocks always
  carry the `CELL IDENTIFICATION` and `EXPERIMENT CONDITIONS` sections
  (mechanism behind the v4 cell condition; the v25 cell regression's LLM-side
  effect is measurable only on a live re-run, pending the extractor decision).
- **V2.7 scaffolding — CI + packaging**: `.github/workflows/ci.yml` (lint +
  test matrix on Python 3.10/3.11/3.12; ecosystem job for the pybop stack on
  3.12; package job builds sdist/wheel, installs the wheel in a clean venv and
  smoke-tests `parallm --help`). `pyproject.toml` gains readme/license
  (MIT)/classifiers/keywords and `ruff` in `dev`; `python -m build` verified
  locally; `__version__` synced to `0.1.0b1`. PyPI **publish** stays an owner
  action (credentials + version decision); docs site, gallery and v4a remain
  open.
- **CI hardening after the first Actions run**: environment-pinned
  characterization gates (`test_char_baseline.py` P0 at rtol=atol=1e-12 and
  `test_char_p2_recovery.py` at 1e-4) are now tagged `characterization` and
  excluded from CI — their baselines are documented same-machine/same-venv
  gates (runtime `aot_compile` and BLAS kernels make the last bits
  environment-dependent), so they stay in the local default run only. The
  PyProBE Neware audit test skips when the git-ignored
  `data/external/pyprobe_sample/neware/` fixture is absent (previously a hard
  `FileNotFoundError` on any clean checkout). Pytest failures are now emitted
  as check annotations (JUnit XML) so red runs are diagnosable without log
  access.

### Documentation (2026-11-19)

- **Stale v4 numbers and status contradictions fixed**: the 2026-11-17 entry
  now quotes the canonical re-scored aggregate (`results/v2/v4/summary.md`:
  condition accuracy 0.144 / 0.294 / 0.310, invented 0.067 / 0.200 / 0.058);
  the v0.2 execution plan and the private-v4 write-up no longer cite the
  superseded 0.256 / 0.439 values. Milestone naming is reconciled (PRD phases
  P0–P8 vs shipped milestones P0–P5), the v0.2 "proposal / not implemented"
  labels are corrected, and the package description drops the marketing
  tagline. README now discloses that the v4 scorer and the fixture's chemistry
  gold labels were revised *after* the first results were seen (not
  pre-registered). The P5 v3 summary records the real extractor
  (`mimo-v2.6-flash`) for the no-retrieval arms instead of
  "deterministic (no LLM)", falling back to the provider tags in the preserved
  raw outputs when older run metadata is empty. No result value changed.

### Planned (v0.2 original scope; status as of 2026-11-19)
- **V2.1** Applicability & conflict engine — **landed** (expert-label review
  pending owner): auditable, hand-set rubric; decision taxonomy
  `USE / FIX / CALIBRATE / MEASURE / REJECT`; rule-firing transcript;
  conflicts preserved with alternatives.
- **V2.2** Parameter assembly report + CLI/API (`parallm assemble`) — **landed**
  (17 traceability flags pending owner decision): per-parameter dossier, set
  summary, JSON/Markdown/PyBaMM export.
- **V2.3** Observability join — **landed; acceptance met**: per-parameter
  identifiability (FIM/Sobol from P2) → fit/fix/measure action matrix.
- **V2.4** Synthetic end-to-end validation — **landed; acceptance met**
  (assemble → calibrate → validate on held-out rates) with a negative control;
  labelled *synthetic*, never experimental.
- **V2.5** Evidence engineering (P8′, replaces fine-tuning) — **slices landed;
  exit criterion not met**: multi-window retrieval, table-aware chunking,
  condition-window expansion, verification pass; target: condition completeness
  ≥0.5 on a **private v4** with false extraction still 0.000 (current best arm
  0.310 / 0.058).
- **V2.6** Closed loop (P7) — **gated, not started**: parameter-targeted flagged
  field → targeted evidence request → retrieval → extraction → validation →
  approval → recalibrate.
- **V2.7** Product/community — **CI + packaging landed; open**: PyPI publish
  (`parallm-pybamm`; owner action), docs site, examples gallery,
  conflict-resolution mini-benchmark (v4a).

### Decisions (2026-11-08)
D1 auditable hand-set rubric · D2 LG M50 only (multi-chemistry → TODO) ·
D3 no fine-tuning · D4 no real-data-dependent claims · D5 private benchmarks ·
D6 human gate mandatory · D7 LLM out of the numeric decision path.

## [0.1.0-beta.1] - 2026-11-08 (public beta)

First public beta. **No independent experimental validation is claimed.**

### Added
- **P0 — PyBaMM DFN baseline:** pinned PyBaMM (26.8.0.0) Chen2020 DFN, 1C
  discharge to 2.5 V (IDAKLU), deterministic manifests, figures, and tests.
- **P1 — Ecosystem audit:** verified compatibility for PyBOP 26.10 /
  PyProBE-Data 2.6.1 on CPython 3.12.16; revised architecture and integration
  plan.
- **P2 — Estimation & identifiability (PyBOP):** synthetic data generation,
  bounded fitting, sensitivity/identifiability, and a synthetic parameter
  recovery benchmark (synthetic recovery ≠ experimental validation).
- **P3 — Literature & provenance:** document ingestion/store, deterministic
  + optional LLM extraction, parameter registry with provenance/qualifiers,
  validation checks, dataset linkage.
- **P4 — LLM extraction evaluation:** benchmark v2 (20 items, 3 real docs,
  3 arms); Chen2020 discrepancy analysis; LG M50 dataset audit/feasibility
  (no fitting performed).
- **P5 — Reliability, v3 benchmark, retrieval ablation:** benchmark v3 (37
  items, 6 docs incl. 3 CC BY PDFs, 8 dev/29 eval, 6 abstention, 3 repeats
  per LLM arm, mean±std); retrieval_strict id 0.718±0.009, value
  0.946±0.022, provenance 0.928±0.026, condition 0.116±0.011 (weak),
  qualifier 0.741±0.033, false 0.000, abst 1.000; memory-without-evidence
  yields unsupported claims (prov 0.000, false 0.275); strict no-evidence
  abstains. Deterministic provenance diagnostics. Real-data experiment
  designed (not run; eligible dataset unresolved).
- Release-quality docs, MIT software license with third-party scope
  note, data-provenance separation, and reproducibility/limitation
  disclosure.

### Security / compliance
- LLM API keys read from environment only; no secrets committed.
- Copyrighted Chen2020 supplement PDF removed from git tracking (acquire
  separately); CC BY sources redistributed with attribution and recorded
  license evidence.

### Known limitations
- No independent experimental validation; experimental-condition extraction
  is weak (condition completeness 0.116 all / 0.035 eval under retrieval);
  eligible Chen2020-aligned multi-rate validation dataset unresolved.
