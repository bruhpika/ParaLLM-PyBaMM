# ParaLLM-PyBaMM — Release Readiness Audit

**Audit date:** 2026-11-23  
**Auditor:** Release engineering / scientific software QA  
**Scope:** existing repository at `/home/bruhpika/Projects/Parameters` on branch `main`  
**Mode:** read-only audit. No scientific algorithm, CLI screen, CI file, or source file was modified. No commit, push, tag or release was performed. The only file created is this report.

---

## A. Executive summary

### Overall release readiness

**CONDITIONALLY READY — the core scientific engine and CLI are functional and honest, but six HIGH-severity issues should be resolved before a public release.** There are **no BLOCKER** findings: the package builds, installs cleanly in a fresh virtual environment, exposes a working `parallm` executable, and the deterministic science, provenance model and approval gate behave as documented in the main workflows. The reported baseline was reproduced exactly.

### Major strengths

- **Reproduced baseline:** Ruff clean; **499 passed, 8 skipped** (1 PyBaMM deprecation warning); strict MkDocs build successful; three VHS GIFs present and embedded in the README.
- **Clean install verified:** wheel build in isolation, then install into a fresh Python 3.14.10 venv with dependencies resolved from `pyproject.toml`; `parallm --help`, `--version`, `doctor`, `doctor --deep`, `init`, `status`, `simulate`, `assemble`, `validate`, `export` and `calibrate` all executed from `/tmp`, outside the repository.
- **Scientific state separation is mostly explicit** in code and UI: `ExtractionCandidate` → `ReviewReport` → dossier → approval gate → export; `NOT CHECKED`, `NOT CALIBRATED`, `NOT ASSESSED` and `PENDING` are rendered as distinct states, never as passes.
- **Genuine provenance machinery:** verbatim quote verification against archived full text, source document IDs, locators, page/offset fields, SHA-256 hashes of target/registry/gate in assembly manifests, nine mandatory dossier fields, and an empty-by-design export without a human gate.
- **The archived example was not sanitised:** `examples/candidate_archived.json` still fails `physical_plausibility` when validated; the failure is visible in text and JSON output and in the VHS demo, exactly as required.

### Main risks

1. Common CLI usage errors are turned into `E199 Unexpected CLI failure / report this as a bug` because Typer 0.29 raises exceptions from its vendored `typer._click` module while `cli.py` catches only `click.exceptions.*`. Documented examples with misplaced global options trigger this.
2. `export --format pybamm` can return exit 0 while writing `PARAMETERS = {}` if PyBaMM names cannot be resolved; the registry used by `assemble` is not carried into `export`.
3. Scientific state labels contradict each other in `explain` (Origin `CALIBRATED` vs Calibration `NOT CALIBRATED`), and dossier approval status stays `pending` even for gate-approved values.
4. Documentation contains stale test counts and quick-start commands that reference files that do not exist, so a new researcher's first copied commands fail.

### Ready for public release?

**Not yet.** The software is credible and the scientific core is defensible, but the HIGH findings below should be fixed and re-verified first. Nothing found requires a redesign of the approved CLI or a change to scientific algorithms.

### Working-tree note

`git status` before and after the audit showed the same **24 pre-existing entries** (modified `README.md`, `pyproject.toml`, `cli.py`, engine files, etc., plus untracked CLI modules, docs, demos and examples). The audit did not alter any of them.

---

## B. Verification results

| Check | Actual result | Supporting evidence |
|---|---|---|
| Git baseline | `main`; HEAD `76afc7c` (`docs: restore supplement text locally…`); 24 modified/untracked entries | `git status --porcelain=v1`, `git log --oneline -15` |
| Ruff | **Clean** — `All checks passed!` (ruff 0.17.5) | `.venv/bin/python -m ruff check .` |
| Tests (default) | **499 passed, 8 skipped, 1 warning** in 12.48 s (CPython 3.14.10) | `.venv/bin/python -m pytest -q` |
| Tests (README core scope) | **496 passed, 8 skipped, 3 deselected** — README says 462 | `.venv/bin/python -m pytest -q -m "not benchmark and not characterization"` |
| Strict docs build | **Successful** (`Documentation built in 0.71 seconds`) | `.venv/bin/python -m mkdocs build --strict` |
| Wheel build | **Successful** with setuptools deprecation warnings (license table/classifier) | `.venv/bin/python -m build --wheel` (isolated) |
| Clean install | **Successful**; `parallm` console script created; Python 3.14.10, PyBaMM 26.8.0.0, NumPy 2.5.5, Typer 0.29.2, Rich 14.3.4 | fresh venv in `/tmp/opencode/parallm-audit/clean`, `pip install <wheel>` |
| `parallm --version` | `parallm 0.1.0b1`, exit 0, from `/tmp` | clean venv executable |
| `parallm --help` | Full workflow help, exit 0 | clean venv executable |
| `parallm doctor` / `--deep` | 14 passed/8 warnings/0 failed (no config); 16 passed/6 warnings after init; `--deep`: 18 parameter sets, Chen2020 present; exit 0 | clean venv, isolated HOME |
| `init` non-interactive / closed stdin | Workspace + config created; no prompt; exit 0; `--force` refusal works with E105 | isolated HOME `/tmp/opencode/parallm-audit/home` |
| `status` | Reports config/workspace/path existence, exit 0 | same isolated HOME |
| Archived fixture validation | `REJECTED`, **1 FAILED**: `physical_plausibility: unit mismatch for volume_fraction: got dimensionless, expected fraction`; exit 1 | `parallm validate examples/candidate_archived.json` |
| Archived fixture with source docs | `check_provenance PASSED` (quote verified) but the same unit check still FAILED | `--documents data/raw_documents --registry data/registry --check-pybamm-names` |
| Fixture location | User brief says `fixtures/examples/candidate_archived.json`; actual file is **`examples/candidate_archived.json`** | `find . -name candidate_archived.json` |
| JSON mode | One valid JSON object on stdout, zero bytes on stderr, exit 1 on scientific failure | `parallm --json validate …` piped to `python -m json.tool` |
| Quiet mode | Single compact `input=…` line | `parallm --quiet validate …` |
| Piped output | 0 ESC sequences by default; `FORCE_COLOR=1` intentionally forces 27 | `parallm doctor > file`, `grep -c $'\033'` |
| Overwrite protection | `export` refuses existing output with **E403**, exit 2; `simulate`/`calibrate synthetic` refuse non-empty dirs | repeated `parallm export --from … --output …` |
| `simulate` | Real DFN/Chen2020/IDAKLU run completed; 4 artifacts; exit 0 | `parallm simulate --config configs/baseline_dfn.yaml --out …` |
| `calibrate synthetic` without extra | **E301**, exit 3, actionable message | clean venv (no PyBOP) |
| `assemble` | 96 dossiers, decisions `FIX=66/USE=24/CALIBRATE=6`, traceability `ok=96 fail=0`; no gate → `{}`; with gate → 90 exported | clean venv, temporary outputs |
| `export --format pybamm` | With `--registry`: 83 installed names, 5 skipped. **Without** registry: `PARAMETERS = {}`, exit 0 | temporary outputs in `/tmp` |
| Missing argument / bad flag | **E199** "Unexpected CLI failure" instead of usage error | `parallm validate`, `parallm --badflag` |
| PDF ingestion without pypdf | **E199** (RuntimeError), exit 2, not documented E301 | `parallm extract <pdf> --parameter porosity` |
| Documentation commands | Quickstart references three non-existent config files and a missing gate file | `ls configs/p2`, `ls reports/gate.json` |
| CI matrix | 3.10/3.11/3.12 + ecosystem 3.12 + wheel smoke test; no 3.13–3.15 job | `.github/workflows/ci.yml:15,100–120` |
| Optional dependency honesty | `doctor` lists PyBOP/pypdf/SALib/PINTS/PyProBE as MISSING when absent; no auto-install | `doctor` output |

---

## C. Findings by severity

### BLOCKER

**None identified.** Installation, entry points, core workflows and the approval gate all function, and no scientific result was found to be fabricated or silently substituted.

### HIGH

#### H1 — Typer usage errors are misreported as internal bugs
- **File/module:** `src/pybamm_closed_loop/cli.py:59–96`; `src/pybamm_closed_loop/cli_app/errors.py`.
- **Problem:** `main()` catches `click.exceptions.Exit/Abort/ClickException`, but Typer 0.29.2 raises `typer._click.exceptions.MissingParameter`, `NoSuchOption`, etc. These fall through to the generic `except Exception`, producing `E199 Unexpected CLI failure — Re-run with --debug … or report this as a bug`.
- **Why it matters:** Automation receives a "bug" diagnostic and exit code 2 for ordinary user mistakes; `--json` consumers get a misleading `code: E199` instead of a usage error. The design system's E1xx/E2xx contract is not honoured.
- **Reproduction:** `parallm validate` (no argument); `parallm --badflag`; `parallm validate candidates.json --json` (option after subcommand).
- **Recommended resolution:** Catch the vendored Typer exception hierarchy (or `click.ClickException` from both modules) and map it to `E100`/exit 2 with `format_message()`; add unit tests for missing-argument and unknown-option paths. This requires no change to scientific behaviour.

#### H2 — Documented JSON examples use an option placement that fails
- **File/module:** `docs/CLI.md:44,164,195–197` (contradicting `README.md:85–87` and `docs/CLI.md:44`).
- **Problem:** The guide says global options go *before* the subcommand but then shows `parallm validate candidates.json --json --strict > validation.json`, `parallm extract … --quiet`, and `parallm export … --json`. Typer rejects these; the first produces a header on stdout plus an E199 JSON error (exit 2).
- **Why it matters:** The primary automation examples in the CLI reference cannot be copied successfully.
- **Reproduction:** `parallm validate examples/candidate_archived.json --json`.
- **Recommended resolution:** Correct the examples to `parallm --json --strict validate …` etc., and add a documentation smoke test that executes every fenced `bash` command in `docs/CLI.md` with `--help`-safe arguments.

#### H3 — PyBaMM export can be silently empty
- **File/module:** `src/pybamm_closed_loop/cli_app/commands/export.py:58–75,99–125`; `src/pybamm_closed_loop/cli_app/commands/assemble.py:115–159`.
- **Problem:** `assemble` records the registry path and SHA-256 in `manifest.json`, but `export` never reads that manifest. With a fresh workspace config (registry path that does not exist locally) and no explicit `--registry`, `records` stays empty, every approved value is skipped as "no PyBaMM name recorded", and `--format pybamm` writes `PARAMETERS = {}` with exit 0.
- **Why it matters:** A researcher can believe they exported an approved PyBaMM overlay while receiving an empty dictionary. This is a scientifically misleading success.
- **Reproduction:** `parallm assemble … --registry data/registry/registry.json --gate gate.json`; then, in a fresh workspace, `parallm export --from <outdir> --format pybamm --output parameters.py` → `PARAMETERS = {}`, exit 0.
- **Recommended resolution:** Resolve the registry from the assembly manifest when `--registry` is absent; if zero parameters are mapped in `--format pybamm`, fail with a non-zero exit and an actionable E4xx error (or require an explicit `--allow-empty`).

#### H4 — Contradictory calibration state in `explain`
- **File/module:** `src/pybamm_closed_loop/cli_app/commands/science.py:593–606,630`; `src/pybamm_closed_loop/registry/model.py:17–24`.
- **Problem:** `explain` sets the Calibration field solely from a recorded *synthetic* fit report (`recovery` mapping), ignoring `record.status`. For `neg_particle_diffusivity`, whose registry status is `CALIBRATED` (a literature Sand-equation fit), the screen shows `Origin CALIBRATED` and `Calibration NOT CALIBRATED` simultaneously; no P2 report in `results/p2/` even has a `recovery` key. `evidence inspect` uses the opposite rule (`status != "CALIBRATED"` → `NOT CALIBRATED`) and therefore disagrees.
- **Why it matters:** The distinction between "literature-fitted", "synthetically recovered" and "not calibrated" is central to the project's scientific claim. Contradictory labels erode trust.
- **Reproduction:** `parallm explain neg_particle_diffusivity --registry data/registry/registry.json`.
- **Recommended resolution:** Represent three explicit values — `LITERATURE_FIT` (status-derived), `SYNTHETIC_FIT RECORDED` (report-derived) and `NOT CALIBRATED` — and use the same helper in `evidence inspect` and `explain` without changing underlying data.

#### H5 — Missing PDF dependency produces the wrong error contract
- **File/module:** `src/pybamm_closed_loop/cli_app/commands/science.py:172–180`; `src/pybamm_closed_loop/literature/ingest.py`; `docs/CLI.md:226,225–231`.
- **Problem:** `ingest_pdf` raises `RuntimeError("pypdf is required for PDF ingestion …")`, but the CLI catches only `ModuleNotFoundError`. The result is E199/exit 2, while the docs promise E301 and exit 3 with an install hint.
- **Why it matters:** One of the most likely first-run failures (PDF without the optional extra) is both misclassified and contradicted by troubleshooting documentation.
- **Reproduction:** clean core install; `parallm extract <any.pdf> --out DIR --parameter porosity`.
- **Recommended resolution:** Catch `RuntimeError`/`ImportError` at this boundary and raise `DependencyError` with the existing E301/exit 3; add a test with a stubbed failing ingest.

#### H6 — Quick-start commands do not run as written
- **File/module:** `README.md:109–133` (especially 116–129); `docs/QUICKSTART.md:22–35,61–64,74–79`.
- **Problem:** Referenced files `configs/p2/recovery_single.yaml`, `configs/p2/recovery_multi.yaml` and `configs/p3/*.yaml` do not exist (actual names: `configs/p2/recovery_single_1C.yaml`, `configs/p2/recovery_multi_0p5_1_2C.yaml`). The assemble example uses `.venv/bin/parallm`, which is absent in the current checkout (stale editable install under the old `pybamm_closed_loop-0.1.0` distribution name), and `--gate reports/gate.json`, which does not exist. QUICKSTART also states 184/201 passed and expects `extraction_summary.json`, while the engine writes `extraction_metadata.json`.
- **Why it matters:** A new researcher's first copy-pasted commands fail before reaching any scientific workflow.
- **Reproduction:** `ls configs/p2 reports/gate.json .venv/bin/parallm`; run the README quick-start block verbatim.
- **Recommended resolution:** Update command examples to real paths, document a minimal gate JSON example (or show that omitting `--gate` yields an empty export), prefer `python -m pybamm_closed_loop` in a fresh checkout, and refresh the recorded counts to 499 passed / 8 skipped.

### MEDIUM

#### M1 — Approval state is not reflected in dossiers
- **File/module:** `src/pybamm_closed_loop/assembly/dossier.py:54–59`; `src/pybamm_closed_loop/cli_app/commands/assemble.py:97–113`.
- **Problem:** `dossier()` always stamps `approval.status = "pending"`; the loaded `ApprovalGate` is used only for `pybamm_export()`. In an audit run with 96 gate approvals, all 96 dossier approval fields remained `pending`, and `explain` displayed `Approval PENDING` for values that were in fact exported as approved.
- **Why it matters:** The provenance surface contradicts the export audit trail.
- **Resolution:** Stamp approval decisions (approver, timestamp, rubric version) onto dossier copies before writing `report.json`, while keeping the gate as the authority.

#### M2 — `validate --registry` has surprising semantics and side effects
- **File/module:** `src/pybamm_closed_loop/registry/store.py:43–47`; `src/pybamm_closed_loop/cli_app/commands/science.py:340–341,41–44`.
- **Problem:** `validate --registry` expects a *directory*, but `RegistryStore.__init__` calls `mkdir(parents=True, exist_ok=True)`, so a read-only validation silently creates a directory. Passing a JSON file (the natural interpretation, and what `evidence --registry` requires) yields E199 `FileExistsError`.
- **Resolution:** Validate the path before constructing the store; never create directories in read-only commands; accept both a directory and a `registry.json` file, with a clear `InputError` otherwise.

#### M3 — Approval gate can be bypassed for arbitrary JSON sources
- **File/module:** `src/pybamm_closed_loop/cli_app/commands/export.py:76–104`.
- **Problem:** Gate enforcement is applied only when the source payload is a JSON *list* (registry records). A dict of names→values passed via `--from` is exported as `approved_only: true` without any gate.
- **Why it matters:** The JSON envelope asserts "approved_only" even when no approval was checked.
- **Resolution:** Require provenance/approval metadata for any dict source unless it is the exact manifest-paired `pybamm_export.json`; otherwise set `approved_only: false` and emit a warning.

#### M4 — PyBaMM overlay lacks units, provenance and unit verification
- **File/module:** `src/pybamm_closed_loop/cli_app/commands/export.py:125,132`; `src/pybamm_closed_loop/assembly/report.py:186–202`.
- **Problem:** `export --format pybamm` writes `PARAMETERS = {name: value}` with no units, no source IDs, no calibration state and no check that numeric values are in the units implied by PyBaMM name suffixes. It also exports the *as-printed* `selected.value` rather than `normalized_value`; the shipped registry happens to keep them equal, but other registries would not.
- **Why it matters:** A bare overlay cannot be defended from the dossier alone and is not demonstrably simulation-ready.
- **Resolution:** Emit a companion provenance manifest for the overlay, verify value units against `pybamm_unit_suffix`, prefer canonical values, and document that manual review is required before simulation.

#### M5 — Direct PyBaMM imports outside the engine facade
- **File/module:** `src/pybamm_closed_loop/calibration/fitting.py:15`, `calibration/synthetic.py:18`, `registry/seed.py:1371`, `reporting/manifest.py:54`.
- **Problem:** `AGENTS.md` requires all PyBaMM interaction to go through `pybamm_engine/`; four scientific modules import PyBaMM directly. `docs/CLI_CAPABILITY_MATRIX.md:31` acknowledges this only partially.
- **Resolution:** Move the required introspection/constants behind explicit `pybamm_engine` helpers, or record an approved exception in the architecture documentation.

#### M6 — Python support claim exceeds CI coverage
- **File/module:** `pyproject.toml:7`; `.github/workflows/ci.yml:15`; `README.md:43–55`; `docs/INSTALLATION.md:5–9`.
- **Problem:** Metadata and docs claim 3.10–3.15; CI tests only 3.10, 3.11 and 3.12 (plus ecosystem 3.12). This audit verified 3.14.10 only. No job covers 3.13 or 3.15.
- **Resolution:** Add 3.13/3.15 jobs or narrow `requires-python` and the documented matrix to versions actually verified.

#### M7 — Undeclared direct `click` import
- **File/module:** `src/pybamm_closed_loop/cli.py:14`; `pyproject.toml:20–32`.
- **Problem:** `import click` is used for exception handling but `click` is not declared; it is currently present only transitively via `scipy` (PyBOP/black also pull it). A future SciPy version dropping Click would break CLI startup.
- **Resolution:** Declare `click` explicitly, or drop the direct import by handling exceptions through Typer's own API (which also addresses H1).

#### M8 — Stale quantitative documentation
- **File/module:** `README.md:135–138`; `docs/QUICKSTART.md:61–69`.
- **Problem:** Recorded counts (462 and 184/201) no longer match the repository (496 for the README's marker subset; 499 passed / 8 skipped for the default run).
- **Resolution:** Refresh counts and state the precise Python/version command used; add a CI check that the documented numbers match a machine-readable baseline.

#### M9 — `assemble` overwrites prior artifacts without confirmation
- **File/module:** `src/pybamm_closed_loop/cli_app/commands/assemble.py:63–66,106–159`.
- **Problem:** `mkdir(exist_ok=True)` then unconditional writes replace `report.json`, `report.md`, `pybamm_export.json` and `manifest.json`. `export`, `simulate` and `calibrate synthetic` all require explicit overwrite opt-in.
- **Resolution:** Add `--overwrite` to `assemble` with the same E403 behaviour, or write to a versioned subdirectory.

### LOW

- **L1 — Empty document store reported as PASSED.** `src/pybamm_closed_loop/cli_app/commands/core.py:198–204`: an existing but empty directory gets `Documents PASSED (0 entries)`. Prefer `WARNING` when `n_docs == 0`.
- **L2 — Stale developer environment.** The existing `.venv` has an editable install under the old distribution name `pybamm_closed_loop-0.1.0` and no `parallm` script; a fresh `pip install -e .` is required after the rename. Does not affect clean installs.
- **L3 — Config schema version is not validated.** `src/pybamm_closed_loop/cli_app/config.py:19,67–80`: `SCHEMA_VERSION` is defined but incoming `schema_version` is neither checked nor migrated.
- **L4 — `FORCE_COLOR` defeats pipe safety.** `src/pybamm_closed_loop/cli_app/render.py:81–87`: documented "no formatting when piped" holds by default, but `FORCE_COLOR=1` injects ANSI into redirected output.
- **L5 — Fixture path mismatch in the brief.** The archived fixture is `examples/candidate_archived.json`, not `fixtures/examples/candidate_archived.json`. No functional impact; documentation consistently uses the real path.
- **L6 — Plausibility check uses exact unit names.** `src/pybamm_closed_loop/validation/checks.py:179–185` with `registry/units.py:17–20`: `dimensionless` and `fraction` have the same dimension signature, but the fixture's `dimensionless` is FAILED against the expected `fraction`. The failure is a naming-convention mismatch, not a dimensional error. **Do not change the fixture or the demo**; document this explicitly so readers do not infer a physical impossibility.
- **L7 — Build warnings.** Wheel builds emit setuptools deprecation notices for the license table/classifier in `pyproject.toml:6,13`; non-fatal, but noisy for a release gate.

---

## D. Scientific integrity review

### Extraction

`literature/extraction.py` produces `ExtractionCandidate` objects that are explicitly *proposals*: each carries `schema_ok`, `proposed_by`, segment IDs and a source object with document ID, page, locator and quote. The offline extractor is labelled `deterministic:offline-pattern-extractor` and abstains when no numeric evidence exists; the LLM client requires both `--provider llm --live` and `PYCL_LLM_API_KEY`/`PYCL_LLM_MODEL`, and hardens URL and redirect handling for the API key. `extract` writes `candidates.json` and prints `CANDIDATES ONLY — not validated, not calibrated`. No extraction command writes to the registry. **Assessment: sound and conservatively worded.**

### Validation

`validation/checks.py` implements pure deterministic checks: schema, definition, conditions, qualifier, verbatim quote verification (with fabricated-quote detection), unit conversion, physical plausibility ranges, conflict preservation and PyBaMM-name mapping. The CLI reports four distinct statuses and maps `NOT CHECKED` to `NEEDS_REVIEW`, never to a pass; `--strict` makes warnings and unchecked results fail with exit 1. Quote verification was confirmed live: the archived Chen2020 full text verifies the archived quote, while the unit check still fails. **Assessment: scientifically honest; H2/M2/L6 are presentation/boundary issues, not fabricated results.**

### Calibration

Only synthetic recovery is exposed (`calibrate synthetic` via PyBOP), with `report["synthetic"] = True`, a `scientific_note`, seed/noise/config SHA provenance and a non-zero exit on non-convergence. `calibrate report` only summarises recorded runs. `docs/REAL_DATA_FITTING_FEASIBILITY.md` and `CLI.md` explicitly state that real-data fitting is not implemented. The 4 registry records with `status=CALIBRATED` are literature fits (e.g., Sand-equation GITT fits), not CLI calibration runs — the source of the H4 label contradiction. **Assessment: no overclaim in the algorithms; the UI must stop mixing the two senses of "calibrated".**

### Units and dimensional consistency

`registry/units.py` is an explicit, tested conversion table with a deliberate refusal to guess ambiguous `C`. It rejects unknown units rather than substituting. The archived fixture's failed check is caused by exact canonical-name comparison (`dimensionless` vs `fraction`) even though both share the same dimension signature; the failure remains visible in text, JSON and the VHS demo and was not modified. **Assessment: unit handling is defensible; the specific failure should be explained, not hidden (L6).**

### Provenance and experimental conditions

`SourceRef`, `ValueEntry` and `ParameterRecord` retain document ID, DOI/URL, locator, page, character offsets, verbatim quote, conditions, method, uncertainty and review state. `verify_record_quotes` stamps non-mutating copies and records `n_no_text`/`failed verbatim check` states. Dossiers carry nine mandatory fields including alternatives/conflicts, applicability rules, identifiability, recommendation and human approval. The assembly manifest records SHA-256 hashes of target, registry and gate. The target specification carries cell product, chemistry, format, temperature, SOC and model. Offline extraction leaves temperature `null` and cell `UNRESOLVED`; the CLI renders these as unavailable/`WARNING` rather than passes. `check_conditions` currently hardcodes the Chen2020 range 273.15–333.15 K for all parameters, which is appropriate for this target but should be surfaced as a target-derived assumption rather than a universal rule. **Assessment: strong provenance model; H4/M1/M4 are the main trust gaps.**

### PyBaMM compatibility and export

PyBaMM is pinned to `26.8.0.0`; `pybamm_engine` verifies the pin before simulation, introspects installed parameter sets and names, and `doctor --deep` reports 18 installed sets including Chen2020. `validate --check-pybamm-names` verifies registry names against the installed set. Export skips unmapped/uninstalled names and reports limitations. However, the overlay carries no units or provenance, does not prefer canonical values, and can be empty with exit 0 (H3/M4). No exported set should be described as simulation-ready without manual review and the missing checks. **Assessment: compatibility checking is real; export readiness is overstated by its success signal.**

---

## E. Release checklist

| Task | Status | Notes |
|---|---|---|
| Ruff clean | **Verified** | `ruff check .`, 0.17.5 |
| Default test suite | **Verified** | 499 passed, 8 skipped, 1 deprecation warning |
| Marker-scoped core suite | **Verified** | 496 passed, 8 skipped, 3 deselected |
| Strict MkDocs build | **Verified** | Adds no nav warnings for this report (`validation.nav.omitted_files: info`) |
| Wheel/sdist build | **Verified** | Isolation build succeeds; deprecation warnings only |
| Clean-environment install + console script | **Verified (3.14.10 only)** | `parallm --help/--version/doctor` from `/tmp` |
| Multi-version clean-install matrix 3.10–3.15 | **Incomplete** | CI covers 3.10–3.12; only 3.14 exercised here |
| First-run `init`/`doctor`/`status` | **Verified** | Non-interactive and closed-stdin paths; no auto-install |
| Extraction → validation workflow | **Verified** | Candidates only; genuine failure preserved |
| Deterministic validation + quote verification | **Verified** | Archived quote verified; no fabricated values |
| Approval gate controls export | **Verified** | No gate → `{}`; gate → 90 approved in audit fixture |
| Synthetic calibration labelling | **Verified** | E301 without extra; synthetic report notes |
| PyBaMM version pin and name checks | **Verified** | Engine + `doctor --deep` + `validate --check-pybamm-names` |
| Export correctness and non-empty guard | **Incomplete** | H3, M3, M4 |
| Usage-error and dependency-error contract | **Incomplete** | H1, H2, H5 |
| Scientific state labelling consistency | **Incomplete** | H4, M1 |
| Documentation command examples | **Blocked** | H6, M8 — stale counts and missing files |
| CLI release checklist completed | **Incomplete** | `docs/CLI_RELEASE_CHECKLIST.md` items all unchecked |
| Cross-platform terminal smoke test | **Not applicable / not performed** | Linux only in this audit |
| Data/third-party licence review | **Verified (documentation)** | `docs/DATA_PROVENANCE.md`; PDF not redistributed |
| Public release / commit / push | **Not applicable** | Explicitly out of scope for this audit |

---

## F. Final recommendation

**CONDITIONALLY READY — only the specified issues need resolution.**

Rationale: the project clears the two highest bars for scientific software — it installs and runs in a clean environment, and it does not fabricate or silently promote scientific results. The approval gate, provenance records and synthetic-only calibration boundary are genuine, and the archived failed example remains visible. However, six HIGH issues would make a public release confusing or misleading: usage errors labelled as bugs (H1), broken documented automation examples (H2), a silent empty PyBaMM export (H3), contradictory calibration labels (H4), a wrong error contract for missing PDF support (H5), and quick-start commands that reference non-existent files (H6).

Recommended remediation order: **H3 and H4 first** (scientific trust), then **H1/H5** (error contract), then **H2/H6** (documentation), followed by the MEDIUM items. Re-run Ruff, the full test suite, the strict docs build and the clean-install wheel smoke test after remediation. No change to the approved CLI design, scientific algorithms, CI strategy or archived fixture is required.

**No remediation was started at the time of the audit.** Sections A–F above are the original, unchanged audit record. The approved remediation of the six HIGH findings is recorded in section G below, which supersedes section F.

---

## G. Remediation record (2026-11-23, targeted to the six HIGH findings only)

### Scope and integrity constraints honoured

Only H1–H6 were changed. No scientific algorithm, CLI screen/layout, CI workflow or archived fixture was modified. No commit, push or release was performed. The archived fixture `examples/candidate_archived.json` is byte-for-byte unchanged and still fails `physical_plausibility` (`dimensionless` vs expected `fraction`).

### G.1 Finding-by-finding record

| Finding | What changed | Relevant files | Tests added |
|---|---|---|---|
| **H1** Typer usage errors as E199 | `main()` now builds exception tuples from both the external Click hierarchy and Typer's public exception hierarchy (`typer.exceptions.TyperException`, `Exit`, `Abort`), with an `ImportError` fallback for older Typer versions that use real Click. Usage errors now emit `E100`, exit 2 and `format_message()`; `SystemExit`/exit/abort are handled explicitly. No string matching on exception messages. | `src/pybamm_closed_loop/cli.py` | `test_invalid_arguments_are_usage_errors_not_internal_bugs`, `test_version_callback_still_exits_cleanly` |
| **H2** Broken `--json` examples | Corrected global-option placement in the documented automation commands (`--json` before `validate`; `--quiet` before `extract`); `--strict` stays after the subcommand because it is a subcommand option. Documented `E100`, `E404` and `PARTIAL` semantics. | `docs/CLI.md` | `test_documented_json_examples_execute_and_emit_valid_json` (runs both documented commands, validates the JSON envelope, asserts zero stderr and checks every documented `parallm` command with a global option) |
| **H3** Silent empty PyBaMM export | New `ExportError` (`E404`, exit 2). Export resolves the registry from `--registry`, then the assembly `manifest.json` `registry.path`, then config. A missing registry or zero mapped names aborts before any file is written. JSON/pyBaMM outputs now report `n_requested`, `n_exported`, `skipped` and `complete`; partial exports are labelled `PARTIAL` with limitations. JSON artifacts gain `complete` and `n_requested`. | `src/pybamm_closed_loop/cli_app/errors.py`, `.../commands/export.py`, `docs/CLI.md` | `test_pybamm_export_refuses_missing_registry_without_writing`, `test_pybamm_export_refuses_empty_mapping_without_writing`, `test_pybamm_export_uses_manifest_registry_and_marks_partial` |
| **H4** Contradictory calibration state | Added `calibration_state(record, fit)` as the single authoritative mapping: recorded synthetic fit → `SYNTHETIC FIT RECORDED`; origin `CALIBRATED` with no fit → `LITERATURE FIT REPORTED`; otherwise `NOT CALIBRATED`. Shared fit discovery used by both commands. Origin metadata is never promoted to a recorded calibration. Both human output and JSON envelope now agree. | `src/pybamm_closed_loop/cli_app/commands/science.py` | `test_calibration_state_is_identical_in_explain_and_evidence_inspect`, `test_calibration_state_helper_distinguishes_origin_from_recorded_fit` |
| **H5** Missing pypdf as E199 | Pre-flight `importlib.util.find_spec("pypdf")` check in the PDF ingestion branch raises the existing `DependencyError` (`E301`, exit 3) with the documented install hint; the narrow `ModuleNotFoundError` handler is retained. No broad `RuntimeError` catch. | `src/pybamm_closed_loop/cli_app/commands/science.py` | `test_missing_pypdf_maps_to_e301` |
| **H6** Invalid quick-start commands | README and QUICKSTART now use the real config filenames, a real target config, `python -m pybamm_closed_loop` instead of a possibly absent console script, and an assemble example with no invented gate file (documenting that the export is empty until approvals exist). QUICKSTART gained a first-run section derived from actual `init` behaviour. Test counts refreshed. | `README.md`, `docs/QUICKSTART.md` | `test_quickstart_commands_reference_real_files_and_clean_init`, `test_archived_fixture_still_fails_its_unit_check` |

All new tests live in `tests/unit/test_cli_release_findings.py` (**11 tests**).

### G.2 Verification results (actual, post-remediation)

| Check | Actual result |
|---|---|
| Targeted regression tests | **11 passed** in 1.68 s |
| Ruff | **All checks passed!** (ruff 0.17.5) |
| Full pytest suite | **510 passed, 8 skipped, 1 warning** in 13.44 s (CPython 3.14.10) |
| Marker-scoped core suite | **507 passed, 8 skipped, 3 deselected** in 10.25 s |
| Strict MkDocs build | **Successful** (0.82 s; only INFO about the audit page not being in `nav`) |
| Package build | **sdist + wheel built successfully** (setuptools licence deprecation warnings only) |
| Clean wheel install | Fresh Python 3.14.10 venv, `parallm` console script created, PyBaMM 26.8.0.0 / Typer 0.29.2 / Click 8.5.1 |
| CLI smoke from `/tmp` | `--version`, `--help`, `doctor` all exit 0; missing argument → `Missing argument`, exit 2; `--badflag` → `E100`, exit 2 |
| Documented JSON commands from clean install | `--json doctor` exit 0, valid JSON; `--json validate … --strict` exit 1, valid JSON; stderr empty |
| H3 clean-install check | Missing registry → `E404`, exit 2, **no file written** |
| H4 clean-install check | `explain` and `evidence inspect` both show `LITERATURE FIT REPORTED` for `neg_particle_diffusivity` |
| H5 clean-install check | PDF without pypdf → `E301`, exit 3 |
| Archived fixture | Still `REJECTED` with `physical_plausibility FAILED`, exit 1 (unchanged) |
| Git | No commit, push, tag or release; no change to CI, scientific algorithms or the archived fixture |

### G.3 Remaining limitations (out of the approved scope)

- **MEDIUM items M1–M9 and LOW items L1–L7** from section C remain open, notably: approval status in dossiers is still `pending` even for gate-approved values (M1); `export --format json` still accepts an arbitrary dict without a gate (M3); PyBaMM overlays still contain no units or provenance (M4); direct PyBaMM imports outside `pybamm_engine/` remain (M5); CI still covers only Python 3.10–3.12 (M6). None of these is a new regression from this remediation.
- The empty-export guard applies to `--format pybamm`. Empty JSON exports remain allowed because the documented no-gate workflow intentionally writes `{}`.
- `click` is still an undeclared direct import (M7), though the H1 fix reduces dependence on its exact version.
- Clean-install verification was performed on CPython 3.14.10 only.

### G.4 Updated release recommendation

**CONDITIONALLY READY — all six approved HIGH findings are resolved and verified; the remaining MEDIUM/LOW items are outside this remediation's scope and should be scheduled separately before or shortly after a public release.**

No further changes were made in that remediation step, and no commit, push or publication was performed.

---

## H. Resolved finding M3 — JSON export gate bypass (2026-11-23)

The approved JSON export trust model (`docs/JSON_EXPORT_TRUST_MODEL.md`) has been implemented; see that document §11 for the implementation status and deviations.

| Original finding | Resolution | Verification |
|---|---|---|
| **M3 — approval gate bypass for arbitrary JSON sources** | Direct JSON inputs are now `UNVERIFIED`; `approved_only: true` requires a verified gate/manifest/registry/artifact hash chain. User-supplied approval claims are never trusted. `REJECTED` validation fails closed; `NEEDS_REVIEW` requires explicit approval with a warning. Nested re-export and v1→v2 migration are safe; empty exports are explicitly classified. | 22 new tests in `tests/unit/test_json_export_trust.py`; full suite 532 passed, 8 skipped. |
| **M4 — PyBaMM overlay lacks units/provenance** | Deliberately unchanged by approved design decision: metadata lives in the JSON artifact only; no ParaLLM fields are injected into `PARAMETERS`. This remains a documented limitation, not a defect introduced here. | `test_pybamm_overlay_unchanged`. |
| **M1 — dossier approval still pending** | Optional stamping was permitted but not required by the confirmed decisions; not implemented. The gate file remains authoritative. | Documented deviation §11.4. |

**Updated release recommendation:** **CONDITIONALLY READY** — all six HIGH findings and M3 are resolved and verified. Remaining MEDIUM/LOW items (M1, M4 by design, M5–M9, L1–L7) are outside this implementation's scope. No commit, push or publication was performed. Awaiting further approval.

---

## I. Adversarial-audit remediation (2026-11-23)

| Finding | Resolution | Regression tests (all in `tests/unit/test_export_trust_hardening.py`) | Status |
|---|---|---|---|
| **H1** stored v2 validation metadata bypassed the UNKNOWN guard | Canonical `normalise_validation_state()` applied to every source and after metadata merging; null/absent → `NOT_RECORDED`, unrecognised types/strings → `UNKNOWN` (skipped, `E404`) | `test_h1_*` (6 tests + 9-case parametrised normaliser test) | Resolved |
| **H2** contradictory gate records resolved by order | `validate_gate_records()` rejects duplicate parameter ids in assembly, attestation and both export formats with `E201`; approval counts use validated unique records | `test_h2_*` (5 tests incl. both orders and assembly) | Resolved |
| **H3** v2 re-export passed the wrong claim object and always downgraded | Correct embedded attestation passed; `derived_content_sha256`, original-chain re-verification and value comparison; trust preserved only when all checks pass; accurate `downgraded_from` | `test_h3_*` (9 tests incl. tampered value/metadata/attestation and modified original chain) | Resolved |
| **M1** v1 empty export claimed `complete: true` | v1 `complete` now requires at least one exported value; v2 status `INTENTIONALLY_EMPTY` | `test_m1_intentional_empty_not_marked_complete` | Resolved |
| **M2** NaN/±Infinity/booleans accepted | `E201` on non-finite/boolean values; strict `allow_nan=False` serialisation | `test_m2_*` (2 tests, 5 cases) | Resolved |
| **M3** duplicate JSON keys / canonical ids silently collapsed | Domain `E201` identifying the duplicate | `test_m3_*` (2 tests) | Resolved |
| **M4** PyBaMM export needed redundant `--registry` for registry-list source | Registry-list `--from` used as registry source | `test_m4_pybamm_registry_list_source_without_redundant_registry` | Resolved |
| **M5** malformed gate fell through to `E199` | Gate domain errors mapped to `E201` in assembly and export | `test_m5_malformed_gate_is_domain_error` (4 cases) | Resolved |
| **Phase 5** | Boolean schema version rejected; relative manifest paths resolved against manifest dir with `..` refused; null validation semantics unified; integrity vs authenticity documented in `docs/JSON_EXPORT_TRUST_MODEL.md` §10.1 | `test_boolean_schema_version_rejected`, normaliser tests | Resolved |

**Verification:** Ruff clean; full pytest **583 passed, 8 skipped, 1 warning** (baseline 532 passed); 51 new tests added; no existing tests removed or weakened (the round-trip test was tightened). Archived fixture hash unchanged.

**Deviations / remaining risks:**
- `derived_content_sha256` is a new proposed v2 field; v1 remains byte-shape compatible except that empty exports now set `complete: false`.
- SHA-256 attestation proves internal consistency only; replacing the whole chain together still produces `ATTESTED`. Documented in §10.1; signatures out of scope.
- `target_config.sha256` and `report.json` are recorded but not verified by export (documented).
- Symlinks are followed; hashes verify content, not file identity. Relative `..` traversal is refused.
- Dossier approval stamping (optional decision 5) remains unimplemented; the gate file is authoritative.
- Clean-install verification in this cycle covers CPython 3.14.10 only; CI matrix remains 3.10–3.12.

**Updated release recommendation:** **CONDITIONALLY READY** — the three HIGH adversarial findings and all selected MEDIUM/LOW findings are resolved. Remaining risks are documented limitations, not known defects. No commit, push or publication was performed. Awaiting further approval.
