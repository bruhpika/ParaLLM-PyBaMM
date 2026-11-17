# Changelog

All notable changes to PARALLM are documented here. The project follows the
milestone plan (P0–P8); scientific behavior is versioned conservatively and
documented with provenance.

## [Unreleased] — v0.2 "Parameter Assembly" (in execution)

Scope, exit criteria, risks and decisions: `docs/ROADMAP_V0.2.md`.
Positioning/competitive scan: `docs/POSITIONING.md`. Milestone plan:
`docs/V2_EXECUTION_PLAN.md`.

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
  labels, discipline pass): condition-field accuracy **0.095 ± 0.010 (compact)
  → 0.251 ± 0.014 (expanded) → 0.256 ± 0.023 (v25)** [raw 0.116 / 0.257 /
  0.266]; value found 0.389 → 0.389 → 0.583; invented conditions still rise
  with richer evidence (0.411 → 0.500 → 0.439). The earlier "chemistry never
  recovered" finding reflects the pre-correction fixture; corrected chemistry is
  0.000 / 0.178 / 0.143. Roadmap exit criterion (≥0.5 completeness, false
  extraction 0.000) **not met**. Aggregates: `results/v2/v4/`.
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
- **Private v4 result**, 3 repeats/arm (extractor `gemini-flash-lite-latest`,
  free tier; arms comparable with each other, **not** with the v0.1/v3 numbers):
  condition-field accuracy **0.111 ± 0.009 (compact) → 0.240 ± 0.004 (expanded)
  → 0.249 ± 0.022 (v25)**; value found 0.389 → 0.389 → 0.583; temperature
  0.059 → 0.479 → 0.591; format 0.219 → 0.980 → 0.976. Negative findings
  disclosed: **chemistry never recovered (0.000 in every arm — later corrected
  with the fixture's chemistry gold labels, see 2026-11-17)**, protocol ≤ 0.091,
  `v25` regresses on cell identity (0.360 → 0.186), and invented conditions
  **rise** with richer evidence (0.411 → 0.500 → 0.439). Design + results:
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

### Planned
- **V2.1** Applicability & conflict engine — auditable, hand-set rubric; decision
  taxonomy `USE / FIX / CALIBRATE / MEASURE / REJECT`; rule-firing transcript;
  conflicts preserved with alternatives.
- **V2.2** Parameter assembly report + CLI/API (`parallm assemble`) → per-parameter
  dossier, set summary, JSON/Markdown/PyBaMM export.
- **V2.3** Observability join — per-parameter identifiability (FIM/Sobol from P2)
  → fit/fix/measure action matrix.
- **V2.4** Synthetic end-to-end validation (assemble → calibrate → validate on
  held-out rates) with a negative control; labelled *synthetic*, never
  experimental.
- **V2.5** Evidence engineering (P8′, replaces fine-tuning) — multi-window
  retrieval, table-aware chunking, condition-window expansion, verification pass;
  target: condition completeness ≥0.5 on a **private v4** with false extraction
  still 0.000.
- **V2.6** Closed loop (P7) — parameter-targeted: flagged field → targeted
  evidence request → retrieval → extraction → validation → approval → recalibrate.
- **V2.7** Product/community — PyPI (`parallm-pybamm`), CI (3.10–3.12), docs
  site, examples gallery, conflict-resolution mini-benchmark (v4a).

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
