# v0.2 Execution Plan (Parameter Assembly)

Companion to `docs/ROADMAP_V0.2.md` (scope, exit criteria, decisions). This file
is the **how**: milestone-by-milestone task breakdown, acceptance checks and the
working protocol. One milestone at a time; each ends with tests, docs, one
commit, and an explicit go/no-go from the scientific decision-maker.

Status legend: `[ ]` open · `[~]` in progress · `[x]` done

---

## Protocol (applies to every milestone)

1. **Announce scope first** — state the plan, dependencies, failure modes before
   writing code (AGENTS.md "Before implementing a major module").
2. **One milestone at a time.** No opportunistic refactors of P0–P5 code.
3. **No invented science.** Every value in every artifact traces to the
   registry, the ingested store, or the benchmark fixtures. New labels
   (expert decisions) are *drafted* and marked pending owner review.
4. **Determinism.** Every decision is reproducible from (rubric version,
   candidate records, target spec). No randomness, no learned weights in v0.2.
5. **Rule-firing transcript.** Every decision records which rules fired, with
   the inputs they used. A user must be able to re-derive or contest it.
6. **Tests + docs + commit + gate.** Then stop for the go/no-go.

---

## V2.5 — Evidence engineering (P8′)  *[slices landed; exit criterion not yet met]*

**Landed:** condition-aware evidence window (±900 chars around the probe, plus
nearby condition-bearing sentences) and **document-level experimental-setup
retrieval** (greedy class coverage over setup sentences, verbatim), wired into
the P5 harness as `--evidence-mode {compact,expanded}` (default `compact`, so
the committed v3 results stay reproducible).

**Deterministic evidence-side measurement** (`benchmarks/v2/measure_condition_coverage.py`,
`results/v2/condition_coverage/`), share of the 37 v3 items whose evidence block
contains each condition class:

| condition class | compact (v0.1) | expanded window | + document conditions |
|---|---:|---:|---:|
| temperature | 0.108 | 0.162 | **0.838** |
| SOC | 0.108 | 0.216 | **0.757** |
| C-rate | 0.054 | 0.081 | 0.432 |
| cell | 0.081 | 0.270 | 0.514 |
| chemistry | 0.243 | 0.595 | **0.838** |
| method | 0.649 | 0.946 | **1.000** |

**Also landed (second slice):** table-aware chunking (caption/header/footnotes
kept with the rows), top-k de-duplicated multi-window retrieval, and the
**private v4 benchmark**: 30 items over 3 CC BY papers (Schmitt 2023, Tuchel
2026, Wheeler 2024), categories A–E, with a frozen scorer that treats a gold
`not_stated` field as matched only when the extraction reports nothing there.

**Also landed (third slice):** the deterministic **verification pass**
(`verify_quote_in_evidence`, every candidate's quote checked against the
evidence actually shown) and the **`not_stated` discipline**
(`evidence_support` / `enforce_not_stated` in `eval/benchmark_v4.py`): a stated
condition with no trace in the evidence is replaced by `not_stated`, counted in
`mean_dropped_conditions`, and scored both ways (raw vs disciplined) so the
effect is visible. Cell identification evidence (`cell_tokens`,
`cell_identification_sentences`) and the SOC/protocol numeric false-positive fix
land with it. All nine raw runs were re-scored offline (`--rescore`, no model
calls) against the current fixture.

**Also landed (fourth slice, 2026-11-19):** the **protocol context-scorer
fix** — a free-text context now reports a protocol only when it states one
(protocol cue + not an abstention), because treating any non-empty context as
a claim scored the model's explicit abstentions as invented conditions (94 of
110 invented claims under the old rule). Offline re-score of the canonical
run; the old invented/protocol numbers are superseded (details:
`docs/V2_PRIVATE_V4_BENCHMARK.md` §4/§7.1). An unauthorised live re-run that
clobbered 8 of 9 raw files is preserved under
`data/private_v4/results_rogue_20261117/`; the canonical run was restored
from backup before re-scoring.

**LLM-side result on v4, re-scored (canonical run)** (extractor
`gemini-flash-lite-latest`, free tier — *not* comparable with the v0.1/v3
numbers; arms comparable with each other; mean ± std over 3 repeats/arm;
disciplined value with the raw value in brackets):

| metric | oracle compact (upper bound) | oracle expanded (upper bound) | oracle v25 (upper bound) |
|---|---:|---:|---:|
| condition-field accuracy | 0.144 ± 0.016 [0.165] | 0.294 ± 0.018 [0.300] | **0.310 ± 0.022** [0.320] |
| value found | 0.389 ± 0.016 | 0.389 ± 0.042 | **0.583 ± 0.014** |
| invented-condition rate | 0.067 ± 0.000 | 0.200 ± 0.000 | **0.058 ± 0.012** |
| temperature / format / SOC | 0.059 / 0.196 / 0.374 | 0.479 / 0.980 / 0.461 | **0.591 / 0.976 / 0.515** |
| chemistry / protocol | 0.000 / 0.607 | 0.178 / 0.619 | 0.143 / **0.743** |

Transport errors excluded: oracle compact 0, oracle expanded 0, oracle v25 6 (free-tier 503s).

**Honest read of the discipline pass (measured, not assumed):**
- It fires — on average 3.5–14.9 conditions per item are dropped for having no
  trace in the evidence — and quote verification passes for 0.991–1.000 of
  candidates.
- It still **did not reduce the invented-condition rate** (identical raw vs
  disciplined in every arm): the surviving invented claims are cue-anchored
  in the evidence, so an evidence-trace check cannot distinguish "condition of
  this value" from "number that appears elsewhere in the passage". Countering
  invention needs condition↔value association, not a trace check.
- It slightly **lowered** condition-field accuracy (raw → disciplined:
  0.165→0.144, 0.300→0.294, 0.320→0.310): the conservative trace check also
  rejects some correct claims. Disclosed as `raw_*` metrics rather than hidden.

**Still to do in V2.5:** the roadmap exit criterion (condition completeness
≥ 0.5 on the private v4, false extraction 0.000) is **not met** — current
best arm 0.310 / 0.058. The remaining gap is chemistry (0.143), the `v25`
cell-identity regression (0.360 → 0.186, mechanism locked by test — LLM-side
effect measurable only on a live re-run), and an association-level mechanism
against the residual invented claims (0.058–0.200). Full design:
`docs/V2_PRIVATE_V4_BENCHMARK.md`.

## V2.1 — Applicability & conflict engine  *[first milestone — implemented; awaiting label review]*

**Goal.** For a target cell + protocol, rank and decide among candidate values
for one parameter, with a recorded rationale, preserving conflicts.

**Deliverables**
- `src/pybamm_closed_loop/assembly/` package:
  - `lexicon.py` — auditable chemistry/format/cell-product keyword table used
    to parse free-text `conditions` (registry stores conditions as text).
  - `schema.py` — `TargetSpecification`, `ConditionFacts`, `CandidateValue`,
    `Decision`, `MethodClass`.
  - `rubric.py` — hand-set weighted dimensions + blocking rules;
    `evaluate(candidate, target) -> RubricOutcome` (per-dimension scores, fired
    rules, blockers).
  - `resolve.py` — conflict classification (same-source vs cross-source),
    resolution, decision, alternatives, rationale.
  - `dossier.py` — per-parameter dossier (dict + Markdown).
  - `gate.py` — approval record (who/when/what/rubric version) + gate check.
  - `report.py` — `assemble(records, target, rubric)` over the real registry.
- `configs/v2/target_lgm50.yaml` — target specification (LG M50 / Chen2020),
  including the cell product and electrolyte families.
- `configs/v2/rubric_v2.yaml` — rubric definition + weights + version
  (documentation-only; the authoritative weights live in
  `assembly/rubric.py` and are validated to sum to 1.00).
- `data/private_v4/build_applicability_cases.py` →
  `data/private_v4/applicability_cases_v1.jsonl` (**private**, git-ignored)
  — 24 labelled conflict/applicability cases **derived from** the registry and
  the v3 fixture (no hand-typed values); expert labels drafted, `reviewed_by`
  pending owner sign-off.
- `benchmarks/v2/run_applicability.py` — agreement of the rubric with the
  labelled set + rule-firing statistics; aggregates public under
  `results/v2/applicability/`, per-case rows private.
- `tests/unit/test_assembly_*.py`, `tests/integration/test_assembly_report.py`.

**Rubric dimensions (v2, hand-set weights, sum 1.00)**
chemistry 0.22 · method 0.16 · temperature 0.12 · evidence 0.12 ·
cell_product 0.12 · SOC 0.08 · model 0.05 · electrolyte 0.05 · format 0.04 ·
cross-source agreement 0.04. An `ELECTROLYTE_WEIGHTS` variant (sum 1.00,
electrolyte 0.19 / chemistry 0.06) is applied to electrolyte-family
parameters. Blocking rules: chemistry-family mismatch, failed quote
verification, not declarable in the model, cell-specific cell-product
mismatch.

**Conflict classes**
- **Same-source** (all candidates share a source): adopt the source's
  *operative* value (we parameterise the paper's model), preserve the
  alternatives with their method. Rationale recorded.
- **Cross-source**: rank by rubric score; margin below `review_margin`
  (0.10) → `REVIEW` for a human, with ranked alternatives.

**Decisions emitted in V2.1**: `USE`, `FIX`, `REJECT`, `REVIEW`.
`CALIBRATE` / `MEASURE` require observability inputs and are introduced with
V2.3 (the taxonomy in the roadmap is unchanged; V2.1 emits a subset).

**Acceptance checks**
- [x] Unit tests: each dimension, each blocker, same-source policy,
      cross-source ranking, margin→REVIEW, dossier/gate round-trip.
- [x] Integration test: assembly over the real 96-record registry produces a
      report with no exceptions and every field traceable.
- [x] Benchmark: agreement with the drafted labelled set **0.958** (24 cases,
      ≥ 80 % exit criterion met); mismatches listed per case in
      `results/v2/applicability/summary.md` — note the `ambiguous` class alone
      is 1/2 (the set is 2 ambiguous cases, too few to read that subclass).
- [ ] Expert labels reviewed (`reviewed_by` / owner sign-off) — **pending;
      agreement against unreviewed labels is provisional**.
- [x] Report states decisions for all parameters; no silent defaults.
- [x] Docs updated (`ROADMAP_V0.2.md` status, `CHANGELOG.md`); planned
      modules in `ARCHITECTURE.md` still to be moved to implemented.

**Failure modes to watch**
- Free-text condition parsing mislabels a chemistry → mitigate with explicit
  "unknown" scores (never silently 0) and a `parse_warnings` field.
- The rubric "agrees" with drafted labels by construction → the labelled set
  must include **ambiguous** cases expecting `REVIEW`; report agreement
  separately for `USE/FIX` and `REVIEW` cases.
- Same-source policy could hide a genuine paper error → the preserved
  alternative stays visible in the dossier and the set-level summary counts
  preserved conflicts.

---

## V2.2 — Dossier & assembly report  *[implemented; traceability acceptance partially met]*

The **per-parameter dossier is the central artifact** (9 mandatory fields,
roadmap §2.1): selected parameter and units · original literature value ·
verified quotation and page · experimental conditions · alternative values and
conflicts · applicability rationale · identifiability assessment · final
recommendation · human approval status.

`parallm assemble --target configs/v2/target_lgm50.yaml --registry
data/registry/registry.json --out reports/ [--documents data/raw_documents]
[--gate gate.json]` renders the dossiers as JSON + Markdown + a PyBaMM-style
export + a reproducibility manifest (`cli.py`; entry point `parallm`).

**Deterministic pieces:**
- quote verification against the archived full texts
  (`verify_record_quotes` / `verify_quote_in_evidence`) — every run records
  the counts in `manifest.json`;
- `check_traceability` per dossier: a selected value must trace to a
  *verified* quote or carry an explicit status flag (CALCULATED/ASSUMED/…);
  a value carried despite a *failed* verification is a **fail**; a quote that
  could not be re-verified is a **warn** (visible, never silent);
- mandatory human gate (D6): without a gate file the PyBaMM export is empty
  by design.

**Acceptance status (measured on the real 96-record registry):**
- reproducible report (manifest records versions, rubric version, registry +
  config SHA-256, quote-verification counts) — met;
- all 9 fields in every dossier — met (tested);
- traceability: **79/96 ok, 17 fail** — *not yet met*: 17 parameters carry
  `LITERATURE_DERIVED` values with no recorded quote (they cite tables/PyBaMM
  defaults as locators). All 36 quotes that *are* recorded verify against the
  archive (0 failures). The 17 flagged parameters need either backfilled
  quotes or an explicit status correction — an owner decision, listed in
  `report.json` `traceability`.

## V2.3 — Identifiability assessment (observability join)  *[implemented; acceptance met]*

Attach FIM/Sobol/profile-likelihood results per parameter → fit/fix/measure
action matrix; upgrades decisions to include `CALIBRATE`/`MEASURE`.
**Acceptance:** reproduces the P2 finding (negative diffusivity unobservable
≤2C) inside the report — **met** (integration test
`test_p2_finding_reproduced_in_report`).

**Implementation** (`assembly/observability.py`, wired into `assemble()` and
`parallm assemble --p2-results results/p2 [--accuracy-critical …]`):
- deterministic join from the **recorded P2 artifacts** (nothing estimated at
  runtime): `diffusivity_feasibility/report.json` (mean |normalized
  sensitivity| per protocol) and `identifiability_volume_fractions/report.json`
  (parametric-bootstrap std, FIM condition numbers, profiles, Sobol);
- explicit, recorded thresholds: sensitivity < 0.05 (mean |normalized
  sensitivity|, i.e. <5 % output change for an order-unity parameter change)
  → UNOBSERVABLE; bootstrap relative std > 5 % → UNOBSERVABLE;
- decision upgrades (rule-firing recorded in the recommendation rationale):
  observable → `CALIBRATE`; unobservable → `FIX` (hold) or `MEASURE` when the
  parameter is explicitly listed `--accuracy-critical`; REJECT/REVIEW never
  upgraded; unassessed parameters stay `not_assessed` (explicit, never
  silently fitted);
- per-parameter dossier field 7 carries the assessment (status, action,
  protocols, metrics, rules, source artifact); the set summary carries the
  action matrix.

**Measured on the real registry:** 7/96 parameters assessed — 6 CALIBRATE
(both volume fractions, both solid diffusivities except neg, electrolyte
diffusivity, both exchange-current densities), 1 MEASURE (`neg_particle_diffusivity`
when marked accuracy-critical; FIX otherwise — **the P2 finding, reproduced**:
mean |normalized sensitivity| 0.011/0.021/0.048 at 0.5C/1C/2C), 89
`not_assessed`. Limitations: only the protocols studied in the artifacts
(0.5C–2C discharge, 1C / 0.5C+1C+2C synthetic fits) are classified; a
successful fit never proves identifiability (rule 7); thresholds are
assumptions, recorded in every assessment and in the run manifest.

## V2.4 — Synthetic end-to-end validation  *[implemented; acceptance met]*

Protocol-faithful synthetic experiment with deliberate mismatch: assemble →
calibrate on one rate → validate on held-out rates; negative control (fit an
unobservable parameter → validation degrades). Labelled **synthetic**, never

**Implementation** (`benchmarks/v2/run_synthetic_validation.py`, run under
`.venv-ecosystem312`; committed run: `results/v2/synthetic_validation/`):
1. assembles decisions from the real registry + the V2.3 observability join
   (and aborts if the join disagrees with the experiment's expected role
   assignment — never silently);
2. builds a deliberately mismatched synthetic ground truth (Chen2020 with
   offsets: volume fractions 0.72/0.63, neg diffusivity 5.0e-14 vs the
   assembled 0.75/0.665/3.3e-14) and seeded synthetic data at 0.5C/1C/2C;
3. validates the assembled set on held-out rates (baseline);
4. positive control: fits the CALIBRATE-action observable pair (electrode
   volume fractions) on 1C only, re-validates;
5. negative control: fits the unobservable `neg_particle_diffusivity`
   (FIX/MEASURE decision) on the same 1C data — violating the decision —
   and re-validates;
6. reports held-out RMSE vs baseline for both controls and whether the
   predicted pattern reproduced (positive improves; negative does not).

**Measured (5 seeds 20261117–20261121, noise σ=1e-3 V, DFN, maxiter 40, all
fits converged):** held-out mean voltage RMSE **4.4 ± 0.1 mV baseline →
1.1 ± 0.1 mV positive control (4× better) → 4.4 ± 0.1 mV negative control
(unchanged)** — fitting the unobservable parameter gains nothing while the
observable pair generalizes. **Prediction reproduced on 5/5 seeds** (the
V2.6 "stable across repeats" gate item). Limitations: synthetic only
(scientific rules 7/8 — not experimental validation, not proof of
identifiability); the positive fit covers only the scalar-declarable
observable pair (function-valued kinetics remain CALIBRATE in the matrix but
are out of this run's fitting scope).

## V2.6 — Closed-loop refinement (P7) — **gated on V2.1–V2.4**  *[gate not yet open]*

Parameter-targeted loop: flagged field → targeted evidence request → retrieval
→ extraction → validation → approval → recalibrate → iteration log.
**Gate:** may not start until V2.1–V2.4 exit criteria are met, the synthetic
validation is stable across repeats, and the dossier has been reviewed by the
scientific decision-maker on a real parameter set.

**Gate status (2026-11-17):** V2.3 ✅ · V2.4 ✅ (prediction reproduced on
**5/5 seeds**, repeat stability confirmed) · V2.1 ⏳ owner label review ·
V2.2 ⏳ 17 traceability flags (backfill quotes or correct statuses). The two
pending items are owner decisions; no engineering work can close them.

## V2.7 — Product & community  *[CI + packaging scaffolding landed; publish pending owner]*

PyPI (`parallm-pybamm`), CI (3.10–3.12), docs site, examples gallery,
positioning doc, conflict-resolution mini-benchmark (v4a, private answers).

**Landed (2026-11-19):** `.github/workflows/ci.yml` — lint + test matrix on
Python 3.10/3.11/3.12, an ecosystem job (pybop/pints/SALib stack on 3.12,
runs the pybop-gated tests), and a package job that builds the sdist/wheel,
installs the wheel into a clean venv and smoke-tests `parallm --help`.
`pyproject.toml` now carries readme/license (MIT)/classifiers/keywords and
`ruff` in the `dev` extra; `python -m build` verified locally (sdist + wheel)
and the wheel verified installed from a clean venv. **Publishing to PyPI
stays an owner action** (credentials + version decision); docs site, examples
gallery and the v4a mini-benchmark remain open.

---

## Sequencing

```
V2.5 ──► V2.1 ──► V2.2 ──► V2.3 ──► V2.4 ──► V2.6 ──► V2.7 (continuous)
```

**V2.5 comes first** (corrected 2026-11-08): the applicability rubric scores
conditions, so the evidence layer must supply those conditions before the
decision logic is built on top of them.

**V2.6 is hard-gated** on V2.1–V2.4 (§4.2 of the roadmap): an automated
retrieval/recalibration loop over an unreliable decision layer is an automated
way of producing incorrect results.

**Milestone status (2026-11-17):** V2.1 ✅ implemented (agreement 0.958 vs
drafted labels, review pending) · V2.2 ✅ implemented (traceability 79/96,
17 flags pending owner) · V2.3 ✅ acceptance met · V2.4 ✅ acceptance met ·
V2.5 ⏳ exit criterion not met (0.256 / 0.439 vs ≥0.5 / 0.000; blocked on an
extractor decision) · V2.6 gated · V2.7 not started.

**TODO carried (not v0.2 scope):** multi-chemistry (LFP/graphite, NMC811,
Li-metal); experimental dataset acquisition + licensing; observables beyond
voltage (EIS/OCV/dQ/dV/GITT-D); first-party parameter set; PyPI/CI/docs site.
