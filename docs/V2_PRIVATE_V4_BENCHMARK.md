# V2.5 — Private v4 condition benchmark: design, method and results

**Status:** implemented; private corpus + fixture + per-item results are **not
published** (git-ignored under `data/private_v4/`). This document publishes the
*method*, the *aggregate* numbers, and everything needed to reproduce the
harness against a private fixture of your own.

---

## 1. Why v4 exists

The v0.1 benchmark (v3, 37 items) measures *whether* a parameter value can be
extracted with a verifiable quote. Its weakest metric is **experimental-condition
completeness** (0.116 all / 0.035 eval under retrieval). The V2.5 hypothesis is
that the conditions are usually **present in the paper but absent from the
retrieved passage**:

| condition | typical location in the paper |
|---|---|
| value | results section / parameter table |
| temperature | experimental (methods) section |
| chemistry, cell | materials & methods / cell fabrication |
| measurement method | experimental procedure |
| SOC, protocol | test protocol / figure caption |

So v4 asks a different question: **given the retrieved evidence, does the
system recover the conditions under which the value was reported — and does it
avoid inventing conditions the source never states?**

## 2. Private corpus (CC BY 4.0, verified in the PDF text)

| document | why it is in the corpus | conditions it provides |
|---|---|---|
| Schmitt et al. 2023, *J. Electrochem. Soc.* 170 070509 | full parameterization study (NCA cathode; graphite-SiOx and graphite anodes; INR21700-50E / -30T cells) | 25 °C climate chamber, GITT/EIS protocol, values in a parameter table with HE/HP × Experiment/Simulation columns, Arrhenius activation energies at 10/25/40 °C |
| Tuchel et al. 2026, *J. Electrochem. Soc.* 173 180514 | parameterization via current-interrupt + voltage relaxation (NMC920503 and graphite half-cells) | 25 °C laboratory, 2032 coin cells, Li-FUN areal loadings, formation/CIM protocol |
| Wheeler et al. 2024, *Batteries* 10 119 | postmortem aging of 18650 graphite/LFP cells | cell identity and nominal capacity; **no** aging temperature (category E) |

A fourth candidate (Ghoulam 2022, *Energies* 15 4005) was downloaded but
**rejected**: its experimental-setup section is not present in the extracted PDF
text, so its conditions cannot be verified against the archive (a fixture item
whose evidence cannot be verified would be unsound).

## 3. Fixture: 30 items, categories A–E

Categories (per the v4 design):

| category | n | what it tests |
|---|---:|---|
| **A** — separated experimental conditions | 9 | value in one place, conditions in another → multi-window + document-level retrieval |
| **B** — table-dependent interpretation | 5 | the value depends on the table's columns/caption/units → table-aware chunking |
| **C** — multiple experimental conditions | 7 | the same paper reports the quantity under several conditions → condition↔value association |
| **D** — same nominal parameter, different values | 3 | values that differ only because the conditions differ (not a contradiction) → applicability |
| **E** — condition genuinely absent | 6 | the source states no temperature / SOC / method → the system must say `not_stated`, never guess |

Per item the fixture records the parameter (value as printed + unit), the seven
condition fields, an explicit `not_stated_fields` list, and the evidence
locator. Every probe is a **verbatim** substring of the archived document
(validated mechanically when the fixture is built).

## 4. Scoring rules (frozen, `eval/benchmark_v4.py`)

- A gold field is either a value or the literal `"not_stated"`.
- **A gold `not_stated` field is matched only by an extraction that reports
  nothing there.** Inventing a condition is always penalised (and counted
  separately as `invented_condition_rate`).
- Temperature is compared numerically (1 K tolerance); SOC numerically when
  both sides are numeric; other fields by keyword matching, where gold
  alternatives are separated by `|` (any) and required tokens by `+` (all).
- **Protocol claims must be stated, not merely present as words** (scorer
  fix, 2026-11-19): a free-text context reports a protocol only when it
  contains a protocol cue (C-rate, GITT/EIS, pulse, rest, CC-CV, cutoffs, …)
  and is not an abstention ("measurement protocol are not stated"). Treating
  any non-empty context as a protocol claim counted the model's correct
  abstentions as invented conditions — a measured false-positive that was
  **94 of 110** invented claims under the old rule (the earlier 0.41–0.50
  invented rates are superseded by §7.1).
- The system is **not** told which value is the target. The scorer looks for
  the candidate that carries a gold value **and** the best condition set, and
  reports that candidate's per-field verdicts. A correct value with wrong or
  invented conditions therefore scores zero on the condition fields — which is
  exactly the association question v4 is about.
- Transport failures (HTTP 503 etc.) are **excluded** from the scores and
  reported separately; a failed call is not an abstention.
- Printed values such as `9.61·10−15` are converted to JSON numbers by a
  **deterministic coercion applied identically to every arm** (reported in the
  run summary), so no arm can benefit from a formatting quirk.

### 4.1 Verification pass + `not_stated` discipline (deterministic, identical for every arm)

Applied after extraction, before scoring (`eval/benchmark_v4.py`:

`apply_discipline` → `score_with_discipline`), and shared verbatim by the live
runner and the offline re-score (`run_v4_evaluation.py --rescore`):

1. **Quote verification** — each candidate's quote must appear in the evidence
   that was actually shown (`verify_quote_in_evidence`); reported as
   `quote_in_evidence_rate`.
2. **Evidence-grounded conditions** — a stated condition with **no trace in the
   evidence** is replaced by `not_stated` (`enforce_not_stated`): temperature
   must match a temperature extracted from the evidence within 1 K;
   chemistry/cell/format/method must have their distinguishing tokens in the
   evidence; SOC/protocol numbers must occur as standalone tokens (a bare
   substring would match `50` inside `INR21700-50E`). Dropped fields are
   counted (`mean_dropped_conditions`), never silently discarded.
3. **Scored twice** — the row keeps both the disciplined verdict and the raw
   verdict (`raw_condition_field_accuracy`, `raw_invented_condition_rate`), so
   the discipline's effect is measured, not assumed.

### 4.2 Association discipline (opt-in, `--discipline association`, 2026-11-22)

The trace rule of §4.1 is *necessary but not sufficient*: a number that occurs
in another table row, another sentence, or the document-level setup still
counts as a trace. The association discipline adds a deterministic **local
scope** around each candidate's verified quote
(`eval/association.py`); a condition must be supported *there*:

- **Table scope** — when the quote lies in a detected table, the scope is the
  quote's row plus the table caption, the column-header region (including the
  cell-product line, e.g. `High energy (HE): INR21700 –50E …`) and footnotes.
  Other rows are excluded.
- **Sentence scope** — otherwise the quote's sentence plus at most one
  adjacent, same-paragraph condition-bearing sentence (a `…:` run-in before,
  or a condition-cue sentence after). Blank-line-separated sentences are not
  adjacent.
- **Document-level fallback** — only for `temperature_k`, `cell`, `chemistry`
  and `format`, and only from explicitly global statements: the
  `EXPERIMENT CONDITIONS` block, table caption/column-header regions, and
  `all experiments`-style sentences. `soc` and `protocol` are always
  value-local; the single exception lets `protocol` use the document's
  `GITT … C/10` statement when the candidate's method names GITT.
- **Method rules** — an `Experiment` column label is not a method (a table
  column heading is not a technique), and only recognised method families
  (EIS/impedance, GITT, Arrhenius, CIM, simulation/model, DVA, ICA, CV, pulse,
  fit) are accepted. `Simulation` is allowed: simulation/model is the gold
  method for the simulation-column values.
- **Scoring-neutral** — `trace` remains the default; a full re-score with
  `trace` reproduces the committed canonical numbers exactly (regression
  checked). Every decision records scope + rule (`association_rule_counts`,
  `association_fallback_rate` = share of quotes not locatable, which fall back
  to the trace rule; measured 0.000–0.050).

**Protocol (frozen before the test evaluation).** Rules were developed on the
dev half of the seeded split only (`configs/retrieval/dev_test_split.json`,
seed 20261119, 15 dev / 15 test items), then applied **once** to the test
half. Raw outputs are frozen: this is an offline re-score, no model calls.

### 4.3 Prompt arm v26 (Phase 1; results pending, 2026-11-26)

The frozen v25 prompt asks for “the value **and** the conditions” and says to
respond `[]` when the evidence supports no parameter statement. In the
canonical raw outputs, **5 of 6 category-E items return `[]`** even though the
value is verbatim in the evidence — the model is over-abstaining on the item
when the probed condition is absent, which also loses the value and any other
stated conditions. This is a prompt-boundary problem, not a condition-
association problem.

`v26` is the v25 prompt plus one paragraph:

> A parameter value is a valid extraction even when none of its experimental
> conditions are stated. Return the value and mark each unstated condition as
> missing (null for temperature, `UNRESOLVED` for free-text fields, and an
> explicit “not stated” note in context). Do not abstain because conditions are
> missing; abstain only when no parameter value is stated in the evidence.

The schema, evidence builder, scorer and discipline are unchanged. Select it
with `--prompt-version v26`; raw files are suffixed `_v26` and must be written
to a separate `--private-out` directory so the frozen v25 raws are untouched.
Protocol: dev first, test once, then score both `trace` and `association` from
the same raw outputs (`--rescore`, no model calls).

**Expected effect is partial, not a fix-all.** Category E also carries stated
cell/chemistry/format/temperature fields; returning the value alone would only
recover the `not_stated` fields. A diagnostic what-if on the frozen v25 rows
gives condition accuracy **0.372** if every E item returned its value with no
conditions, versus **0.510** if every E item were fully correct — so the prompt
arm is necessary but not sufficient, and the cell/chemistry association work
remains the next lever. **No v26 result is claimed yet**: the live dev run is
blocked on the `PYCL_LLM_*` credentials.

### 4.4 Evidence reachability ceiling (diagnostic, 2026-11-26)

A second limit is in the **evidence**, not the extractor. Running
`scripts/v2/audit_v4_reachability.py` (no model calls; scorer untouched) checks
each gold condition against the frozen v25 evidence window with the same
deterministic matchers the scorer uses. A gold field absent from the evidence
cannot be recovered without importing outside knowledge, which the prompt
forbids.

| split | reachable gold fields | ceiling |
|---|---:|---:|
| dev | 87 / 105 | 0.829 |
| test | 90 / 105 | 0.857 |
| all | 177 / 210 | **0.843** |

Per field (all 30 items): chemistry 1.000, SOC 1.000, method 1.000, protocol
0.900, format 0.900, temperature 0.767, **cell 0.333**. The low ceiling is
almost entirely the cell product identity: for 20 of 30 items the table header
naming `INR21700-50E` / `INR21700-30T` (or the `2032` coin-cell line) is outside
the probe-centred window, while the extracted `LG M50 21700` comparison cell
*is* in it. A model that obeys “only use the evidence” cannot win those fields;
a deterministic association rule cannot recover them either.

Consequences for V2.5: the ≥0.5 condition-completeness criterion is **not
mathematically impossible** (ceiling 0.843), but cell can contribute at most
0.333 / 7 ≈ 0.048 overall, versus 0.184 measured. The remaining headroom is
chemistry (0.143 measured / 1.000 reachable), SOC (0.510 / 1.000) and method
(0.551 / 1.000). This diagnostic is reported, not used to relax the threshold.
Per-item unreachable fields stay private; the public summary is aggregate only.

## 5. Arms

| arm | evidence |
|---|---|
| `compact` | v0.1 behaviour: ±260-character window around the probe |
| `expanded` | condition-aware window (±900 chars + condition-bearing sentences) **+ document-level setup sentences** |
| `v25` | `expanded` **+ table-aware chunking** (caption/header/footnotes kept with the rows) **+ top-k de-duplicated multi-window retrieval** (a value printed both in a table and in the text) |

## 6. Extractor disclosure (important)

All v4 evidence modes (`compact`, `expanded`, `v25`) are **oracle-located
(probe window; NOT performance upper bounds)**: they search the fixture's
hand-written `probe` in the raw text and receive a single small window, not the
BM25 arms' 8-segment block. They are not retrieval results and oracle accuracy
is not a ceiling (§7.5). A real full-store BM25 arm (`retrieval`)
builds the query from the item's parameter name and unit only; its gold-passage
recall is reported below and no live LLM run has been made. The v0.1/v3 results
were produced with `mimo-v2.6-flash`. The v4 arms were
produced with **`gemini-flash-lite-latest` (free tier)** because the MiMo token
plan was exhausted in this environment.

Consequences, stated plainly:

- The **arms are comparable with each other** (same extractor, same prompt,
  same fixture, same scorer) — that is what the V2.5 exit criterion needs.
- The v4 numbers are **not comparable** with the v0.1/v3 numbers; they are a
  different model on a different (private) fixture.
- The free tier returns intermittent HTTP 503; those calls are excluded and
  counted, never scored as abstentions.

**v26 prompt arm (2026-11-26):** the live dev run uses **`mimo-v2.6-flash`**
via Xiaomi's OpenAI-compatible Token Plan endpoint (regional `sgp`). The
endpoint, model and key are supplied through the gitignored `.env` via
`PYCL_LLM_BASE_URL`, `PYCL_LLM_MODEL` and `PYCL_LLM_API_KEY`; no credential is
stored in the repository. This is a **different extractor** from the canonical
v4 arms above, so its absolute numbers are **not comparable** with the frozen
0.310 / 0.058 baseline. The v26 run is a within-run prompt-boundary check
(does the new rule stop the category-E over-abstention?), not a replacement of
the baseline. Schema, evidence, scorer, fixture and threshold are unchanged;
only the prompt arm and the extractor differ.

## 7. Results

See `results/v2/v4/summary.md` (aggregate only; per-item rows stay private).

### 7.1 Result — 3 repeats per arm (extractor `gemini-flash-lite-latest`, canonical run, re-scored with the discipline pass + protocol-scorer fix)

Headline metrics (mean ± std over 3 repeats; raw = pre-discipline value in
brackets):

| metric | oracle compact (probe window) | oracle expanded (probe window) | oracle v25 (probe window) |
|---|---:|---:|---:|
| condition-field accuracy | 0.144 ± 0.016 [0.165] | 0.294 ± 0.018 [0.300] | **0.310 ± 0.022** [0.320] |
| value found | 0.389 ± 0.016 | 0.389 ± 0.042 | **0.583 ± 0.014** |
| unit accuracy | 0.433 ± 0.027 | 0.367 ± 0.027 | 0.403 ± 0.024 |
| **invented-condition rate** (raw = disciplined) | 0.067 ± 0.000 | 0.200 ± 0.000 | **0.058 ± 0.012** |
| abstention rate | 0.433 ± 0.047 | 0.444 ± 0.016 | 0.417 ± 0.014 |
| quote-in-evidence rate | 0.991 ± 0.013 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| mean dropped conditions / item | 3.656 ± 0.427 | 3.478 ± 0.833 | 14.903 ± 2.541 |

Per condition field (disciplined, mean ± std over 3 repeats):

| field | oracle compact | oracle expanded | oracle v25 |
|---|---:|---:|---:|
| chemistry | **0.000 ± 0.000** | 0.178 ± 0.126 | 0.143 ± 0.027 |
| cell | 0.196 ± 0.023 | **0.360 ± 0.010** | 0.186 ± 0.021 |
| format | 0.196 ± 0.023 | 0.980 ± 0.028 | 0.976 ± 0.034 |
| temperature | 0.059 ± 0.005 | 0.479 ± 0.038 | **0.591 ± 0.040** |
| SOC | 0.374 ± 0.029 | 0.461 ± 0.037 | **0.515 ± 0.053** |
| method | 0.352 ± 0.026 | **0.620 ± 0.024** | 0.568 ± 0.164 |
| protocol | 0.607 ± 0.046 | 0.619 ± 0.062 | **0.743 ± 0.082** |

Transport errors excluded from scoring: oracle compact 0, oracle expanded 0, oracle v25 6 (free-tier
503s; they are counted, never scored as abstentions).

Superseded numbers: the previously published invented rates (0.411 / 0.500 /
0.439), condition accuracies (0.095 / 0.251 / 0.256) and protocol field
(0.000 / 0.080 / 0.091) came from the pre-fix scorer that counted abstaining
contexts as protocol claims (§4) — corrected by offline re-score, same
canonical raw run. The chemistry numbers are against the corrected fixture
chemistry gold labels (the earlier "0.000 in every arm" statement came from
the pre-correction fixture).

**Data discipline note:** after the canonical run was committed, an
unauthorised live re-run on 2026-11-17 14:03–14:49 overwrote 8 of 9 raw
files (one with 12 rate-limit/DNS transport errors). The run is preserved
untouched under `data/private_v4/results_rogue_20261117/`, and the canonical
run was restored from the pre-chemfix backup (md5-identical to the state the
committed numbers were produced from) before every re-score.

### 7.2 What the result says (and what it does not)

**Supported — the V2.5 hypothesis holds for value-local conditions.**
Supplying the document-level setup statements lifts the condition-field
accuracy from **0.165 → 0.300 raw** (0.144 → 0.294 after the discipline pass),
with the largest gains in temperature (0.059 → 0.479), format (0.196 → 0.980)
and method (0.352 → 0.620). The full `v25` arm adds table-aware chunking and
multi-window retrieval: temperature 0.591, SOC 0.515, and — notably — **the
rate at which the correct value is found rises from 0.389 to 0.583**, i.e. the
table context also helps *value* selection, not only conditions.

**The protocol scorer false-positive (measured, fixed).** The previously
published invented-condition rates (0.411 → 0.500 → 0.439) were dominated by a
scorer bug: any non-empty free-text context counted as a protocol claim, so
the model's explicit abstentions ("measurement protocol are not stated")
were scored as invented conditions — **94 of 110** invented claims under the
old rule. After the fix (§4) the rates are **0.067 → 0.200 → 0.058** and the
protocol field rises from 0.000/0.080/0.091 to **0.607/0.619/0.743**. The
remaining invented claims are genuine cue-anchored claims that are wrong.

**The discipline pass: measured, and largely negative — disclosed as such.**
- It fires as designed: 3.5–14.9 conditions per item are dropped for having
  no trace in the evidence, and quote verification passes for 0.991–1.000 of
  candidates.
- It still **removed none of the invented conditions** (identical raw vs
  disciplined in every arm): the surviving inventions are cue-anchored in the
  evidence, so an evidence-trace check cannot separate "condition under which
  this value was measured" from "number that appears elsewhere in the
  passage". Countering the residual needs condition↔value association, not a
  trace check.
- It slightly **lowered** condition-field accuracy (raw 0.165/0.300/0.320 →
  disciplined 0.144/0.294/0.310): the conservative trace check also rejects
  some correct claims. Both verdicts are reported (`raw_*` metrics) so the
  trade-off stays visible.

**Negative findings (disclosed, not smoothed over).**
- **Electrode chemistry stays weak** (0.000 compact → 0.178 expanded → 0.143
  v25): the system attaches the chemistry far less reliably than format or
  temperature.
- **Genuine invention now tracks evidence structure, not evidence volume.**
  After the scorer fix the invented rate is compact 0.067 → expanded 0.200 →
  v25 0.058: richer windows raise genuine invention from compact to expanded,
  but the structured `v25` block (table + cell/setup sections) drops it
  **below** compact — structure helps correctness, volume alone does not.
- **`v25` regresses on cell identity** (0.360 → 0.186, consistent across all
  three repeats, so not noise). The cell-identification section is present in
  every expanded/v25 block (locked in by test), so the remaining gap is
  LLM-side association inside the block — hypothesis: the table-aware block
  lists both cells and competes with the identification sentence. Measurable
  only on a live re-run (pending the extractor decision).
- **The discipline still cannot fix association** (above): the residual
  invention problem is exactly the binding problem the cited literature
  (§9) describes. The association discipline of §4.2/§7.6 is the follow-up:
  it halves the invented rate (0.108 → 0.044) with flat condition accuracy.

**Not established.** These numbers come from a **free-tier model on a 30-item
private fixture**; they are a diagnostic for the evidence layer, not a
capability claim, and they are **not comparable** with the v0.1/v3 results
(different model, different fixture). The v0.1/v3 numbers remain the
reference for extraction quality; v4 answers a different question. The
roadmap's V2.5 exit criterion (condition completeness ≥ 0.5, false extraction
0.000) is **not met** at 0.310 / 0.044 (best arm / best arm; §7.6).

### 7.3 Real BM25 retrieval arm (recall only)

The oracle arms above locate evidence from the fixture's `probe`; they are
location oracles (probe window; NOT performance upper bounds; §7.5).
`benchmarks/v2/report_retrieval_recall.py --benchmark v4` adds a
real-retrieval arm that queries BM25 over the full four-document v4 store with
only the parameter name and unit (no probe, target document, gold conditions,
printed value or gold value). Gold-passage recall over the 30 private items is
recall@1 **0.300**, recall@3 **0.867**, recall@5 **0.900**, recall@10 **1.000**
(`results/v2/v4/retrieval_recall.md`). The per-item audit stays private under
`data/private_v4/results/retrieval_recall_audit.json`; the public aggregate
contains no fixture text.

The LLM extraction arm `retrieval` is implemented in
`benchmarks/v2/run_v4_evaluation.py` (and replayable via `--rescore`) but has
**not been run**: it requires a live model call and owner approval. No
oracle-vs-real LLM extraction numbers are claimed. Existing compact/expanded/v25
results are labelled `oracle-located (upper bound)` in the committed
`summary.md`/`summary.json`; that wording predates the clarification and should
be read as `oracle-located (probe window; NOT a performance upper bound)`. New
runs emit the clarified label.

### 7.4 Distractor stress test — small-corpus recall overstates quality

The numbers in §7.3 are measured on the **small** private store (4 documents,
121 segments). `benchmarks/v2/report_retrieval_recall.py --benchmark v4 --stress`
repeats the exact same queries with every ingested document added as a
distractor (10 documents, 472 segments: the v4 store plus the other papers and
the PyBaMM documentation in `data/literature_store`). Recall drops from
0.300 / 0.867 / 0.900 / 1.000 to **0.000 / 0.167 / 0.367 / 0.767** at
k = 1 / 3 / 5 / 10 (source:
`results/v2/v4/retrieval_recall_distractors.md`). No model call is made; the
probe is still only the post-retrieval evaluation label. **Small-corpus recall
overstates retrieval quality**: with few distractors the same query is much
easier, so the §7.3 figures are an easy-setting upper bound, not evidence that
retrieval generalises. The full-corpus per-item audit remains private at
`data/private_v4/results/retrieval_recall_full_audit.json`.

### 7.5 Oracle is a location oracle, not a performance upper bound (offline arms)

The offline end-to-end comparison in
`results/v2/retrieval_improvement/offline_side_by_side_v2.md` shows the
oracle-located `compact` arm finding the value for only 0.333 of 15 test
items, versus 0.733 for both BM25 arms. This is **not** a contradiction: the
oracle arm receives one ~561-character probe window, while each BM25 arm
receives 8 segments (~43–46k characters, ~81x more text). The oracle label
therefore means only "the gold passage was located using the probe"; it is
**not a performance ceiling** when evidence volume differs. The clarified
label is "oracle-located (probe window; NOT a performance upper bound)".
Oracle-vs-BM25 value accuracy is not a like-for-like arm comparison; the
BM25-vs-tuned-BM25 comparison is like-for-like (same 8-segment evidence
volume, different `b`).

### 7.6 Association discipline — dev/test evaluation (2026-11-22)

`--discipline association` (§4.2) re-scored offline from the frozen raw
outputs; rules frozen after the dev half, then applied once to the test half.
Mean over 3 repeats, `trace` (canonical behaviour) vs `association`:

| metric | dev trace | dev assoc | test trace | test assoc | all-30 trace | all-30 assoc |
|---|---:|---:|---:|---:|---:|---:|
| **invented-condition rate** | 0.096 | **0.022** | 0.120 | **0.067** | 0.108 | **0.044** |
| condition-field accuracy | 0.226 | 0.234 | 0.273 | 0.275 | 0.249 | 0.254 |
| method accuracy | 0.51 | **0.65** | 0.52 | 0.53 | 0.51 | **0.58** |
| protocol / SOC | 0.66 / 0.49 | 0.66 / 0.49 | 0.65 / 0.42 | 0.65 / 0.45 | 0.66 / 0.45 | 0.66 / 0.46 |
| temperature / format / cell | 0.35 / 0.74 / 0.38 | flat | 0.40 / 0.70 / 0.15 | flat | 0.38 / 0.72 / 0.25 | flat |
| chemistry | 0.12 | 0.11 | 0.09 | 0.08 | 0.11 | 0.09 |
| scope fallback rate | — | 0.000 | — | 0.000–0.050 | — | 0.000 |

Reading (mean over repeats, same raw outputs, so the only variable is the
discipline):

- **The invented-condition rate halves or better** on every split. The
  mechanism is exactly what §7.2 predicted: cue-anchored inventions (`50%`
  from another row, `C/10` from a different measurement, `Experiment` column
  labels) no longer survive because the local scope does not contain them.
  The dominant rules are `column_label_not_method` (the `Experiment` /
  `Simulation` column-heading habit) and `not_in_local_scope_{method,soc}`.
- **Condition accuracy is flat** (±0.01): the discipline is not trading
  correctness for abstention at the aggregate level. Method accuracy rises
  (0.51 → 0.58 all-30) because dropping a column label converts a wrong claim
  into a correct `not_stated` wherever the gold says `not_stated`.
- **Residual trade-offs, disclosed:** chemistry dips slightly (0.11 → 0.09;
  a claim like `graphite-SiOx` needs every token in scope, and `SiOx` is not
  in the evidence), and in the `v25` arm the strict local-method rule drops
  some correct method claims whose technique is named in a *different* window
  of the multi-window block (test method accuracy 0.625 → 0.500 for v25_r1).
- **E3-type protocol association works as designed:** the document's
  `GITT … C/10` statement attaches to GITT-method values but not to EIS
  values, so the A6-style protocol inventions disappear while the GITT C/10
  protocol of E3-type items keeps scoring.
- **Not a cure-all:** the best arm still misses the V2.5 exit criterion
  (condition completeness 0.310, invented 0.044, vs ≥0.5 / 0.000), and the
  discipline is a post-hoc filter — it prevents *scoring* wrong associations,
  it does not make the extractor abstain. Both are measured and reported.

Artifacts: `results/v2/v4_association/` (all 30),
`results/v2/v4_association_dev/`, `results/v2/v4_association_test/`, with
`trace` baselines in `results/v2/v4_trace_all/`, `results/v2/v4_trace_dev/`,
`results/v2/v4_trace_test/`; private per-item rows in
`data/private_v4/results_association*/`; the all-30 `trace` re-run reproduces
the committed `results/v2/v4/` metrics exactly.

## 8. What this benchmark does and does not establish

**Establishes:** whether a retrieval-grounded extractor can attach the right
experimental conditions to a literature value, and how much that ability
depends on the evidence supplied (the arm comparison).

**Does not establish:** general extraction quality (v3 does that), parameter
identifiability, or anything about real-cell validation. The fixture is small
(30 items, three papers) and the extractor is a free-tier model, so the
absolute numbers are a *diagnostic*, not a benchmark result to cite as a
capability claim.

## 9. External corroboration (related work, checked 2026-11-17)

The two negative findings of §7.2 — (a) the discipline pass removed **none**
of the invented conditions because each invented value's token does occur
somewhere in the evidence, and (b) counteracting this needs condition↔value
**association**, not a trace check — were checked against the published
literature. The sources below are *external* results on *different* tasks,
datasets and metrics; their numbers are **not comparable** with ours (we
score per-field exact match with a gold `not_stated` penalty on 30 private
items). They are cited only as qualitative corroboration of the diagnosis and
of the follow-up direction:

- **Cross-context numeric contamination is a known LLM failure mode.**
  *Comparison of LLMs in extracting synthesis conditions and generating Q&A
  datasets for metal–organic frameworks* (Yaghi group,
  <https://yaghi.berkeley.edu/pdfPublications/25compareLLM.pdf>): frontier
  models (GPT-4 Turbo, Claude 3 Opus, Gemini 1.5 Pro) reached 67.8–83.5 %
  completeness / 83.5–95.7 % correctness on synthesis-condition extraction,
  but *"similar numerical data is presented in multiple contexts… leading to
  confusion or overwriting of details"* — the same mechanism by which our
  invented conditions survive a trace check (the number exists in the
  passage, attached to a different context).
- **Source-tracked, multi-stage extraction is the documented remedy.**
  MetMINE (Wang et al., *RSC Digital Discovery*, 2026,
  <https://pubs.rsc.org/dd/article/5/10/4191/1296477/MetMINE-a-generative-large-language-model-based>)
  records a companion source text per value, extracts iteratively per material
  and finishes with a confirmation pass, reporting that *"confusion errors,
  comprising 62.5 % of total errors, predominantly involve attributing
  properties from one material to another"* without it; and *Reliable
  End-to-End Material Information Extraction from the Literature with
  Source-Tracked Multi-Stage Large Language Models* (arXiv:2510.05142, 2025)
  reports feature-level F1 ≈ 0.96 for the multi-stage source-tracked pipeline
  vs 0.869 for single-pass extraction over 100 articles with a five-expert
  ground truth.
- **Tuple/condition binding is the active bottleneck for value+condition
  records.** Phi et al., *A Hybrid LLM and Supervised Model Pipeline for
  Polymer Property Extraction from Tables in Scientific Literature* (WASP
  2025, doi:10.18653/v1/2025.wasp-main.11): 5-ary tuples
  (polymer, property, value, **condition**, method); a hybrid LLM+encoder
  pipeline reached 67.9 % F1 vs 56.7 % for direct LLM extraction, i.e. binding
  the condition to the value is where systems lose accuracy. See also the
  engineering hypothesis note *"Find With the LLM, Bind With the Encoder:
  Slot-Level Verification for Document-Level N-ary Extraction"*
  (<https://lacuna.tiptreesystems.com/hypothesis/find-with-the-llm-bind-with-the-encoder-slot-level-verification-for-document-119008f290834bbf>,
  **not peer-reviewed**), which states the thesis directly: most document-level
  errors are *binding* errors, not *finding* errors.
- **Extractor capability is a plausible bottleneck (to be isolated, not
  assumed).** On related-but-not-identical tasks — extraction of experimental
  "specifications" attached to table claims — frontier models scored F1
  ≈ 0.59–0.63 (Bertillo et al., *TaDA*, VLDB Workshops 2025,
  <https://www.vldb.org/2025/Workshops/VLDB-Workshops-2025/TaDA/TaDA25_16.pdf>).
  Our 0.310 (best arm) was measured with a **free-tier lite model**. Whether
  the V2.5 gap is an evidence-layer problem or an extractor-capability problem
  is therefore
  an *open question* that only a controlled stronger-extractor re-run can
  settle (decision reserved for the project owner).
