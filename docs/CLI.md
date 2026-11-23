# `parallm` command-line interface

`parallm` is the terminal frontend to the ParaLLM-PyBaMM scientific engine. It
does not implement extraction, validation or calibration logic itself: every
command delegates to the existing core packages under `pybamm_closed_loop/`.

**Extracted values are candidates. They are not validated or calibrated until
they have actually been checked and approved. Synthetic recovery is not
experimental validation.**

See also: [capability matrix](CLI_CAPABILITY_MATRIX.md) and
[design system](CLI_DESIGN_SYSTEM.md). Reproducible VHS demonstrations are in
`demos/`; the rendered GIFs are embedded in the project README.

All screens are built from the shared Rich components in
`pybamm_closed_loop/cli_app/render.py`. Textual is deliberately **not** used:
the workflows are one-shot and scriptable, and the only interactive step
(first-run setup) is handled by Questionary with a plain-input fallback.

## Installation and invocation

Supported Python: 3.10–3.15. The CLI adds `typer`, `rich` and `questionary`
(`tomli` on Python <3.11) to the project's core dependencies.

```bash
pip install -e .                        # from a checkout
pip install "git+https://github.com/bruhpika/ParaLLM-PyBaMM.git"
parallm --version
parallm --help
```

Without installation, the same entry point is available as:

```bash
.venv/bin/python -m pybamm_closed_loop --help
```

PDF extraction, synthetic calibration and PyProBE linkage need the `ecosystem`
extra (`pybop`, `pypdf`, `SALib`, `pints`, `PyProBE-Data`). `parallm --help`,
`--version`, `doctor` and `init` never import PyBaMM or call a network service.

## Global options

Global options go **before** the subcommand.

| Option | Meaning |
|---|---|
| `--config PATH` / `PARALLM_CONFIG` | Use a different configuration file. |
| `--json` | Emit exactly one JSON object on stdout; no styling. |
| `--quiet` | No header, rules or notes; a compact `key=value` line instead. |
| `--debug` | Show tracebacks for unexpected errors. |
| `--no-color` / `NO_COLOR` | Disable colour; output is also unstyled when piped. |
| `--version`, `-h/--help` | Version and help. |

## First run

```bash
parallm init --workspace ./battery-research
parallm doctor
parallm status
```

`init` creates directories and a TOML configuration; it never installs or
modifies packages. Without a TTY it uses safe defaults. To replace an existing
config, pass `--force` explicitly. To use a non-default config path:

```bash
parallm --config ./lab.toml init --workspace ./battery-research --non-interactive
```

Interactive setup offers: detect an existing PyBaMM installation, configure an
existing environment, print instructions for a new environment, or configure
later. Option 3 explains the steps but does not execute them.

### Configuration file

Default: `~/.config/parallm/config.toml`. Credentials are never stored.

```toml
schema_version = 1
workspace = "/home/user/battery-research"
rubric_version = "rubric-v2"
default_export_format = "json"

[paths]
registry = "data/registry/registry.json"
documents = "data/raw_documents"
p2_results = "results/p2"
target = "configs/v2/target_lgm50.yaml"
gate = "reports/gate.json"
```

Relative paths resolve against `workspace`. `doctor` reports missing or invalid
configuration instead of failing before it can help.

## Command reference

### Diagnostics and workspace

| Command | Purpose |
|---|---|
| `parallm doctor [--deep]` | Python/version/dependency/version-pin/workspace/registry/document checks with actionable remedies. `--deep` imports PyBaMM to inspect installed parameter sets. |
| `parallm status` | Show configured paths, existence and parameter count. |
| `parallm project create NAME` | Create a project directory with standard subdirectories. Refuses to overwrite. |
| `parallm project list` | List projects in the active workspace. |
| `parallm project inspect NAME` | Show project paths and file counts. |
| `parallm simulate --config YAML --out DIR [--overwrite]` | Run a pinned PyBaMM baseline through `pybamm_engine`. |

### Scientific workflows

| Command | Purpose |
|---|---|
| `parallm extract SOURCE --out DIR [--parameter NAME]... [--extract-config FILE] [--provider offline\|llm] [--live] [--k N]` | Ingest local text/PDF, retrieve passages, and write extraction **candidates**. |
| `parallm validate FILE [--documents DIR] [--registry DIR] [--check-pybamm-names] [--strict]` | Run the existing deterministic checks over one payload or a list. |
| `parallm evidence list [--registry FILE] [--limit N]` | List registry parameters and their source references. |
| `parallm evidence inspect PARAMETER [--registry FILE] [--report-dir DIR]` | Show one parameter record and any dossier status. |
| `parallm evidence report [--report-dir DIR]` | Summarise decisions, conflicts and traceability. |
| `parallm explain PARAMETER [--registry FILE] [--report-dir DIR] [--calibration-report FILE]` | Traceable provenance report: origin, source, conditions, validation, approval, calibration. |
| `parallm assemble --target YAML --registry JSON --out DIR [--documents DIR] [--gate FILE] [--p2-results DIR] [--accuracy-critical ID]... [--rubric-version V]` | Build dossiers, report, gate-controlled export and manifest. |
| `parallm calibrate report [--results DIR]` | Summarise recorded fit reports without computing anything. |
| `parallm calibrate synthetic --config YAML --out DIR [--overwrite]` | Run one **synthetic** recovery fit via PyBOP. No real-data fitting command exists. |
| `parallm export --format json\|pybamm --from PATH --output FILE [--registry FILE] [--gate FILE] [--overwrite]` | Export only approved values; verify PyBaMM names against the installed parameter set. |

### Extraction

Supported inputs are exactly the formats the ingestion engine supports: plain
text (`.txt`, `.md`) and PDF (`.pdf`, requires `pypdf` from `ecosystem`). A
directory is processed file by file. There is no DOI or URL retrieval.

At least one target parameter name is required: the offline extractor only
recognises explicitly named parameters. Names map to the project's retrieval
alias groups (for example `mean particle radius`, `porosity`, `diffusivity`).

```bash
parallm extract paper.pdf --out results/extraction \
  --parameter "mean particle radius" \
  --parameter "porosity"
```

Output: `results/extraction/candidates.json` and an immutable
`literature_store/`. Candidates carry schema status, proposed value, unit,
qualifier, quote and source segment. Fields the engine did not resolve stay
`UNRESOLVED`/null; they are never invented. The command prints
`CANDIDATES ONLY — not validated, not calibrated`.

A live LLM is opt-in and requires both `--provider llm --live` and
`PYCL_LLM_API_KEY` / `PYCL_LLM_MODEL`. It is never used for help, version,
diagnostics, validation or assembly.

### Validation

The validation command composes the existing deterministic checks; it does not
reimplement them. It reports four statuses:

- `PASSED` — check ran and found no problem.
- `WARNING` — check ran and review is needed.
- `FAILED` — check ran and found a problem.
- `NOT CHECKED` — check could not run (no document store or registry supplied).

```bash
parallm validate candidates.json \
  --documents results/extraction/literature_store \
  --registry data/registry --check-pybamm-names
parallm --json validate candidates.json --strict > validation.json
```

`--strict` makes warnings and NOT CHECKED results fail. A passing validation is
not proof of identifiability and does not make a value calibrated.

Registry records can also be validated. The CLI maps their fields to the
extraction payload shape (status → qualifier, `value_unit` → `unit`, evidence
source → `source`) without changing scientific semantics; missing provenance is
reported as a failure, not filled in.

### Provenance

`evidence inspect` shows only fields that exist in the record. `explain` adds
the assembly decision, identifiability status, approval state and any recorded
synthetic fit, marking absent information as unavailable. Nothing is inferred.

### Export

The default source is the assembly report directory. `pybamm_export.json`
contains only values with a recorded human approval; with no gate, `parallm
assemble` writes `{}`. `export --format pybamm` maps canonical ids to PyBaMM
names from the registry and verifies them against the installed parameter set;
unmapped or uninstalled names are skipped and reported. Callables are never
turned into numeric values.

Existing output files are never overwritten without `--overwrite`.

## Automation

```bash
parallm --quiet extract paper.pdf --out results/extraction
parallm --json validate candidates.json > validation.json
parallm export --format pybamm --from reports/assembly --output parameters.py
```

`--json` output envelope:

```json
{
  "schema_version": 1,
  "command": "validate",
  "status": "completed",
  "data": {},
  "diagnostics": []
}
```

Errors use the same envelope with `status: "failed"` and a structured
diagnostic (`code`, `what`, `why`, `action`, `details`). In human mode errors
are printed to stderr as a panel with no stack trace unless `--debug`.

Exit codes: `0` success, `1` scientific/check failure, `2` usage/config error,
`3` environment/dependency error, `130` interrupted. Error codes: `E100` usage
(unknown option, missing argument), `E1xx` configuration/workspace, `E2xx`
input, `E3xx` environment, `E4xx` scientific or export safety.

A PyBaMM export is never written empty: `--format pybamm` fails with `E404` if
no readable registry exists or if no approved value maps to an installed
parameter name. When some values are skipped, the export is marked `PARTIAL`
with explicit limitations in both the JSON envelope and the written JSON
artifact; only `complete: true` means every approved value was exported.

## Troubleshooting

| Symptom | Cause / action |
|---|---|
| `E100` usage error | Check option placement: global options (`--json`, `--quiet`, `--debug`, `--no-color`) go before the subcommand; subcommand options such as `--strict` go after it. |
| `E104` config not found | Run `parallm init` or pass `--config`. |
| `E301` pypdf missing | Install `parallm-pybamm[ecosystem]` for PDF ingestion. |
| `E302` PyBaMM mismatch | The project pins `pybamm==26.8.0.0`; install that version. |
| Nothing extracted | No `--parameter` given, or no number+unit statement in the retrieved passages. |
| `check_provenance = NOT CHECKED` | No source store supplied; pass `--documents`. |
| Export is empty | No human approval gate; see `parallm assemble --gate`. |
| `E403` overwrite refused | Pass `--overwrite` explicitly or choose a new path. |
| `E404` PyBaMM export refused | No registry was found (pass `--registry` or re-run `assemble`), or no approved value maps to an installed parameter name. Nothing was written. |
| `PARTIAL` export | Some approved values were skipped; review the listed limitations before use. |

## Scientific limitations

- Experimental-condition extraction has weak recall; offline extractions
  commonly leave temperature/cell fields `UNRESOLVED`.
- Synthetic calibration (including `calibrate synthetic`) is method checking,
  not experimental validation. A successful optimisation does not prove
  identifiability.
- Real-data calibration is deliberately not exposed.
- Calibration and validation data must stay disjoint; the CLI does not merge
  them.
- Observability is `not_assessed` for parameters without recorded P2 artifacts.

## Release checklist

See [CLI_RELEASE_CHECKLIST.md](CLI_RELEASE_CHECKLIST.md). No release is
published without explicit owner approval.
