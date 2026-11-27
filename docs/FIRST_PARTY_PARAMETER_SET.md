# ParaLLM-Chen2020-ext — first-party candidate parameter set (v0.3)

**Status:** candidate artifact with per-field provenance; **not** an approved
PyBaMM parameter set. Generated 2026-11-27 from committed inputs by
`scripts/v03/build_param_set.py` (config: `configs/v03/param_set.yaml`).

## What this artifact is

A versioned, deterministic JSON artifact that collects the **27 families**
documented by `data/registry/chen2020_discrepancies.json` into one place with a
source, locator, status and approval state for every field:

- `results/v03/param_set/parallm_chen2020_ext.json` — the artifact;
- `results/v03/param_set/manifest.json` — its attestation (tool versions,
  input SHA-256 hashes, name/value verification, counts).

The name "ext" refers to the *extended* Chen2020 corpus; it is **not** a name
registered with PyBaMM. No PyBaMM parameter set is created, updated or
registered by the builder.

### The 11-vs-16 distinction

| group | count | paper-side value? | status of copied value |
|---|---|---|---|
| `discrepancies` | 11 | yes — value, unit, conditions, verbatim quote, char offsets | copied PyBaMM/Chen2020 operative value (`LITERATURE_DERIVED`, `CALCULATED`, `CALIBRATED` or `ASSUMED` per the registry) |
| `set_extensions.families` | 16 | **no** — paper never parameterizes them | `UNRESOLVED` (15) or `ASSUMED` (1, contact resistance); copied from installed PyBaMM defaults |

Both groups are kept because both matter to a modeller, but only the 11
discrepancy families have literature evidence. The 16 set-extension values are
shipped PyBaMM defaults (the PyBaMM docs call the SEI values "example
parameters"); they are *not* measurements from Chen2020 and must not be used in
calibration before their primary sources are traced.

## How values enter the artifact

The builder is a read-only transformation. Every numeric value, unit, quote,
locator and PyBaMM name is read from `data/registry/registry.json` and
`data/registry/chen2020_discrepancies.json`; none is authored in the script.
It refuses to build if:

- a PyBaMM name is absent from the pinned installed set;
- the installed PyBaMM version is not `26.8.0.0`;
- the discrepancy artifact and registry disagree on a name or an operative
  value;
- the copied operative value disagrees with the installed PyBaMM default;
- a set-extension field unexpectedly has a literature source or a status other
  than `UNRESOLVED`/`ASSUMED`.

Name and value verification go through `pybamm_closed_loop.pybamm_engine`
(introspection of `pybamm.ParameterValues("Chen2020")`). The check on values is
an **internal consistency check**, not literature validation: agreement with a
PyBaMM default only proves the value was copied faithfully.

Per field the artifact records:

- `pybamm_names` — verified against installed PyBaMM;
- `operative` — copied value, unit, registry status and validation state;
- `paper_evidence` — the paper's own value/method/conditions/quote for the 11
  discrepancy families, or `NOT_APPLICABLE` for the 16 set extensions;
- `preserved_conflicts` — all competing registry values, never dropped;
- `provenance` — status, source (document, DOI, locator, quote, char offsets,
  or explicit `NOT_RECORDED` sentinels), and registry source location;
- `approval` — `NOT_RECORDED` unless an explicit human gate file is supplied.

## Trust boundary and human gate

This artifact is **decision support only** (`docs/JSON_EXPORT_TRUST_MODEL.md`):
the only supported PyBaMM export path remains
`AssemblyReport.pybamm_export(gate)`, which emits a plain `{name: value}` dict
for gate-approved `USE`/`FIX` decisions and `{}` without a gate. The builder:

- does not write to `data/registry/` or to any raw document;
- does not create or modify a gate file;
- annotates approvals from an optional `--gate` file but never exports values
  (`status.exportable = false`) and never registers a PyBaMM set
  (`status.pybamm_set_registered = false`) — AGENTS.md rules 6 and 10.

No gate file exists for this set, so all fields are `PENDING_HUMAN_APPROVAL`
with `approval.status = NOT_RECORDED`. Turning this candidate into a usable
parameter set requires explicit scientific review and a human gate decision;
that step is deliberately outside this milestone.

## Regeneration

```bash
.venv/bin/python scripts/v03/build_param_set.py --config configs/v03/param_set.yaml
.venv/bin/python -m pytest -q -m "not benchmark and not characterization"
```

The build has no wall-clock timestamp: identical inputs and tool versions
produce byte-identical outputs. The manifest records the config hash, input
hashes, generator/script versions (Python, package, PyBaMM), the full name
verification result, and `content_sha256` of the parameter fields.

## Scientific limitations

1. The operative values are the PyBaMM/Chen2020 values, including the paper's
   tuned Table IX values; a successful build says nothing about electrochemical
   truth or identifiability (AGENTS.md rules 7 and 8).
2. The 16 set-extension values have no literature provenance; example values
   must not be treated as measured or calibrated for this cell.
3. Cause tags are documented expert judgments, not measurements.
4. No independent experimental data is used or claimed (D4 of
   `docs/ROADMAP_V0.2.md`).
5. Values are not "resolved" by this artifact: where the paper and PyBaMM
   disagree, both sides are preserved and the decision is left pending.
6. This is not an approval, an export or a validation result; hash-based
   reproducibility is an integrity check, not scientific authenticity.

## Unresolved issues

- No human gate file approves this set; no field may be exported or registered.
- The primary sources of the 16 set-extension defaults remain untraced.
- Whether to adopt the paper's measured values in place of the tuned operatives
  is a scientific decision for the project owner, not a builder rule.
- The artifact schema is v0.3 candidate (`schema_version: 1`); it is not the
  assembly export artifact v2 and must not be fed into `parallm export` as an
  attested source.
