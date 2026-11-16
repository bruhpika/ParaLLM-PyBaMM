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

## 5. Arms

| arm | evidence |
|---|---|
| `compact` | v0.1 behaviour: ±260-character window around the probe |
| `expanded` | condition-aware window (±900 chars + condition-bearing sentences) **+ document-level setup sentences** |
| `v25` | `expanded` **+ table-aware chunking** (caption/header/footnotes kept with the rows) **+ top-k de-duplicated multi-window retrieval** (a value printed both in a table and in the text) |

## 6. Extractor disclosure (important)

The v0.1/v3 results were produced with `mimo-v2.6-flash`. The v4 arms were
produced with **`gemini-flash-lite-latest` (free tier)** because the MiMo token
plan was exhausted in this environment.

Consequences, stated plainly:

- The **arms are comparable with each other** (same extractor, same prompt,
  same fixture, same scorer) — that is what the V2.5 exit criterion needs.
- The v4 numbers are **not comparable** with the v0.1/v3 numbers; they are a
  different model on a different (private) fixture.
- The free tier returns intermittent HTTP 503; those calls are excluded and
  counted, never scored as abstentions.

## 7. Results

See `results/v2/v4/summary.md` (aggregate only; per-item rows stay private).

### 7.1 Single-run result (r0, extractor `gemini-flash-lite-latest`)

| metric | compact (v0.1) | expanded | v25 (full) |
|---|---:|---:|---:|
| condition-field accuracy | 0.105 | **0.243** | 0.229 |
| value found | 0.367 | 0.400 | **0.600** |
| unit accuracy | 0.400 | 0.367 | 0.433 |
| **invented-condition rate** | 0.367 | 0.533 | 0.467 |
| abstention rate | 0.500 | 0.433 | 0.400 |

Per condition field:

| field | compact | expanded | v25 |
|---|---:|---:|---:|
| chemistry | 0.000 | 0.000 | 0.000 |
| cell | 0.267 | **0.353** | 0.167 |
| format | 0.267 | 0.941 | **1.000** |
| temperature | 0.067 | 0.529 | **0.556** |
| SOC | 0.400 | 0.412 | 0.444 |
| method | 0.467 | **0.647** | 0.500 |
| protocol | 0.000 | 0.118 | 0.000 |

### 7.2 What the result says (and what it does not)

**Supported.** The V2.5 hypothesis is confirmed for the *value-local*
conditions: supplying the document-level setup statements lifts the
condition-field accuracy from **0.105 → 0.243** (2.3×), with the largest gains
in temperature (0.067 → 0.529), format (0.267 → 0.941) and method
(0.467 → 0.647). The same evidence also raises the rate at which the correct
value is found at all (0.367 → 0.600 for the full `v25` arm).

**Not supported / negative findings.**
- **Chemistry is never recovered** (0.000 in every arm): the system does not
  report the electrode chemistry correctly, even when the material is in the
  evidence. This is a genuine gap, not a scoring artefact.
- **Protocol stays near zero** (0.000–0.118): pulse/rest details are stated in
  the methods but not recovered.
- **More evidence, more invention.** The invented-condition rate *rises* with
  the richer evidence (0.367 → 0.533 → 0.467): supplying more context gives
  the model more opportunity to attach a condition that does not belong to the
  value. A future iteration must pair evidence engineering with a
  *not_stated*-discipline mechanism.
- **The `v25` cell regression** (0.353 → 0.167) is a hypothesis to test, not
  a settled result: table-aware + multi-window evidence dilutes the cell
  identity. With one repeat per arm the arm differences beyond compact-vs-
  evidence are inside run-to-run noise, which is why repeats are running.

**Not established.** These numbers are from a **free-tier model on a 30-item
private fixture**; they are a diagnostic for the evidence layer, not a
capability claim, and they are not comparable with the v0.1/v3 results.

## 8. What this benchmark does and does not establish

**Establishes:** whether a retrieval-grounded extractor can attach the right
experimental conditions to a literature value, and how much that ability
depends on the evidence supplied (the arm comparison).

**Does not establish:** general extraction quality (v3 does that), parameter
identifiability, or anything about real-cell validation. The fixture is small
(30 items, three papers) and the extractor is a free-tier model, so the
absolute numbers are a *diagnostic*, not a benchmark result to cite as a
capability claim.
