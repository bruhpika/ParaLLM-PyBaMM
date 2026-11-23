# CLI release checklist

No release, push, tag or public asset update is performed without explicit
owner approval. This checklist is the evidence required before requesting one.

## Code and architecture

- [ ] `parallm --help`, `--version`, `doctor`, `init`, `status` run with no
      network access and no LLM credentials.
- [ ] Command handlers contain no extraction, validation or calibration logic;
      all scientific work delegates to `pybamm_closed_loop` core packages.
- [ ] `main(argv)` and `load_target` remain import-compatible with existing
      callers (including `scripts/` and benchmark harnesses).
- [ ] `ruff check src tests` passes.
- [ ] No secrets, tokens, generated caches or user data are staged.

## Testing

- [ ] `.venv/bin/python -m pytest -q` passes (unit + integration +
      characterization). Record the exact count and Python/version matrix.
- [ ] `.venv/bin/python -m pytest -q -m "not benchmark and not characterization"`
      passes; pre-existing failures are reported separately.
- [ ] New CLI tests cover help/version, init, status, doctor, projects,
      extraction, validation, evidence, explain, export, calibrate report,
      quiet/JSON modes, narrow widths and missing data.
- [ ] `python -m pybamm_closed_loop --help` works without installation.
- [ ] Regression: `parallm assemble` still writes `report.json`, `report.md`,
      `pybamm_export.json` and `manifest.json`, with an empty export when no
      approval gate is supplied.

## Scientific honesty

- [ ] No command presents an extracted value as validated or calibrated.
- [ ] No command exposes real-data fitting; synthetic fits are labelled
      SYNTHETIC and carry the "not experimental validation" note.
- [ ] `NOT CHECKED` is never rendered as a pass.
- [ ] Export contains only human-approved values; overwrite requires
      `--overwrite`.
- [ ] Evidence/provenance output uses only fields present in the underlying
      record.

## Documentation

- [ ] README quickstart includes the CLI and the install command.
- [ ] `docs/CLI.md`, `docs/CLI_CAPABILITY_MATRIX.md` and
      `docs/CLI_DESIGN_SYSTEM.md` are in the MkDocs nav.
- [ ] Configuration reference, exit codes, JSON envelope and troubleshooting
      are documented.
- [ ] `CHANGELOG.md` records the CLI addition under Unreleased.
- [ ] Version strings agree in `pyproject.toml` and
      `src/pybamm_closed_loop/__init__.py`.

## Packaging

- [ ] `typer`, `rich`, `questionary` and the conditional `tomli` are declared
      in `pyproject.toml`; lockfiles/regenerated environments are updated by
      the owner.
- [ ] `[project.scripts] parallm = pybamm_closed_loop.cli:main` is unchanged.
- [ ] Build/install verified in a clean environment for each supported Python
      version.
- [ ] Cross-platform smoke test (Linux, macOS, Windows terminal) recorded,
      including redirected output and `NO_COLOR`.
