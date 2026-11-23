# JSON Export Trust Model and Schema — Design Proposal

**Status:** proposal only. No implementation, schema file, test, or source change is included.  
**Date:** 2026-11-23  
**Scope:** `parallm export --format json` and its relationship to assembly, approval, validation, provenance and the PyBaMM overlay.  
**Notation:** fields marked `[PROPOSED]` do not yet exist in the repository. Everything else is taken from current code, fixtures or tests.

---

## 1. Current architecture and trust boundary

The existing design is deliberate and should be preserved:

1. `pybamm_closed_loop/registry/` holds provenance-first `ParameterRecord`s (96 seeded records). Values enter only through deterministic seeding, validated extraction plus explicit approval, or user approval (`AGENTS.md` rule 10).
2. `assembly/` turns registry records plus a target cell specification into nine-field dossiers. `ApprovalGate` (`assembly/gate.py`) records human approvals; `AssemblyReport.pybamm_export()` (`assembly/report.py:186–202`) emits **only** gate-approved parameters whose decision is `USE`/`FIX`. Without a gate the artifact is `{}` by design (D6).
3. `parallm assemble` (`cli_app/commands/assemble.py`) writes `report.json`, `report.md`, `pybamm_export.json` and `manifest.json`. The manifest already records `registry.path`/`sha256`, `gate.path`/`sha256`/`n_approved`, `target_config.sha256`, quote-verification counts, traceability counts, tool version and `n_exported` — i.e. a reproducible attestation chain, **except that it does not hash `pybamm_export.json` itself**.
4. `parallm export` (`cli_app/commands/export.py`) is a formatter. For a JSON **list** payload (registry records) it requires a gate; for a JSON **dict** payload (assembly export or any other object) it does not, because the dict is assumed to be an already-approved export artifact. The PyBaMM formatter additionally requires a readable registry and at least one mapped, installed parameter name (`E404`, added during remediation).

This separation — approval at assembly, formatting at export — is sound. The problems found are about **what the formatter claims** and **what metadata it carries forward**, not about where approval is enforced.

Two distinct JSON envelopes must not be confused:

| Envelope | Current version | Defined at | Purpose |
|---|---|---|---|
| CLI response envelope | `schema_version: 1` | `cli_app/context.py:70`, `cli.py:65` | `{command,status,data,diagnostics}` on stdout |
| Export artifact | `schema_version: 1` | `cli_app/commands/export.py:184` | The written `--output` file |

This proposal changes only the **export artifact** (to version 2). The CLI response envelope stays at version 1.

---

## 2. Problems confirmed by source inspection

| # | Confirmed behaviour | Evidence |
|---|---|---|
| P1 | Any JSON dict passed via `--from` bypasses the gate; the config `paths.gate` is ignored for dict payloads. | `export.py:108–129`; verified with a config gate approving nobody — export still succeeded. |
| P2 | The artifact asserts `"approved_only": true` unconditionally for dict payloads. | `export.py:186`. |
| P3 | The artifact carries only `value`, `unit`, `pybamm_names`; no origin, source document, locator, quote, traceability, quote-verification, validation, approval, calibration or conditions. | `export.py:181`; `docs/CLI.md:183–188` documents no artifact schema. |
| P4 | `validation_state` is written by seeding (`registry/seed.py:1252,1309`) and stored (`registry/store.py:151`) but never read by assembly or export. A `REJECTED` record assembled with a gate and exported normally. | empirical reproduction in a temp directory. |
| P5 | Re-exporting an existing artifact (`parameters` entries are dicts) yields `{}` with `complete: true`, exit 0. | `export.py:125–128` filters to numeric values only; reproduced. |
| P6 | An intentionally empty export (`{}` with no gate) and a failure-looking empty export are not distinguished; `complete: true` is reported for the former. | committed `reports/assembly/pybamm_export.json` and `manifest.json` (`n_approved: 0`, `n_exported: 0`). |
| P7 | Dossier `approval.status` remains `pending` even for gate-approved values (audit M1), so dossiers cannot serve as the approval source. | `assembly/dossier.py:54–59`; `assemble.py:97–113`. |
| P8 | PyBaMM overlay has no units or provenance and is indistinguishable from a native PyBaMM set (audit M4). | `export.py:174`. |

`UNRESOLVED` has a specific documented meaning — "shipped value with untraced provenance" (`docs/PARAMETER_REGISTRY.md` §2) — and `check_traceability()` deliberately accepts it as an explicit flag (`assembly/dossier.py:125–158`). Therefore "insufficient evidence" is sometimes *explicitly recorded*, not missing data; the schema must preserve that distinction rather than treating all sparse records as errors.

---

## 3. Proposed trust model

### 3.1 Principle

Approval remains established **only** by an `ApprovalGate` record created during assembly. Export never creates, infers or upgrades approval. The export artifact must state **how its own approval claim was established**; if it cannot be established, it must say so.

### 3.2 Never infer approval from

- file extension (`.json`) or filename (`pybamm_export.json`);
- presence, shape or numeric type of values;
- `origin`/`status` metadata (`CALIBRATED`, `LITERATURE_DERIVED`, …);
- a user-supplied `approved_only`, `approval`, or `attestation` field in the input.

A user-supplied claim may be **preserved as a claim** under `[PROPOSED] artifact.reported_claims`, but it must never raise the trust level.

### 3.3 Trust levels (artifact-level)

| Level | Meaning | Basis |
|---|---|---|
| `ATTESTED` | Approval is established by a verifiable chain. | Source is an assembly report directory with `manifest.json`; manifest `gate.path`/`sha256` resolve to an existing gate file with matching SHA-256; `manifest.gate.n_approved > 0` or the artifact is the recorded empty export; `registry.sha256` matches; and `[PROPOSED] manifest.outputs_sha256["pybamm_export.json"]` matches the file being exported. |
| `ATTESTED_EMPTY` | Same chain, but the assembly deliberately produced `{}` because no gate/approvals existed. | `manifest.gate.n_approved == 0`, `manifest.n_exported == 0`, file is `{}`. |
| `UNVERIFIED` | Approval cannot be established; values are still exported as a convenience. | Any direct JSON file, or a manifest whose chain cannot be fully verified. `approved_only` is `false`; each parameter's approval status is `not_recorded`. |
| `UNKNOWN` | The input claims an artifact structure but required evidence is contradictory or unreadable. | Hash mismatch, unknown schema version, malformed manifest. Fail closed by default: do not write an output; require an explicit `--unverified` opt-in to downgrade to `UNVERIFIED`. |

### 3.4 Parameter-level states (independent of artifact trust)

Even in an `ATTESTED` artifact, every parameter carries its own statuses. Artifact trust answers "is this file the approved artifact?"; parameter statuses answer "what is known about this number?".

- `approval.status`: `APPROVED` | `REJECTED` | `NOT_RECORDED`.
  Authoritative source: the gate `approvals[]` record (`parameter`, `decision`, `approved`, `approver`, `rubric_version`, `timestamp`, `note`). Dossier `approval.status` stays informational until M1 is resolved.
- `validation.state`: `ACCEPTED` | `NEEDS_REVIEW` | `REJECTED` | `NOT_RECORDED` | `NOT_PERFORMED` | `UNKNOWN`.
  Source: registry `validation_state` for registry-backed values; `NOT_PERFORMED` when no deterministic validation run is recorded. The `validate` CLI currently produces a transient `ReviewReport` and does not persist it; this proposal does **not** invent a persistence mechanism.
- `calibration.status`: `NOT_CALIBRATED` | `LITERATURE_FIT_REPORTED` | `SYNTHETIC_FIT_RECORDED` (the same three-value vocabulary already agreed for `explain`/`evidence inspect`).
- `evidence.quote_verification`: `verified` | `failed` | `not_performed` | `not_applicable` | `not_recorded`, derived from `verify_record_quotes()` stamps and the `NOT CHECKED` convention.

### 3.5 Missing-information vocabulary

Distinguish, rather than emitting a bare `null`:

| Sentinel | Meaning | Example |
|---|---|---|
| `NOT_RECORDED` | No field exists in the source artifact. | direct JSON input has no source document |
| `NOT_PERFORMED` | A check could have run but did not. | quote verification without `--documents` |
| `NOT_APPLICABLE` | Concept does not apply. | `page` for a source with no real page structure; `quote` for a user-supplied value |
| `UNKNOWN` | Field exists but its value is unrecognised. | unrecognised `validation_state` string |

Concrete values are never replaced by a sentinel, and sentinels are never replaced by a guessed value.

---

## 4. Proposed JSON schema (artifact version 2)

Top-level shape. Existing v1 keys (`schema_version`, `source`, `approved_only`, `parameter_set`, `parameters`, `limitations`, `n_requested`) are retained or explicitly superseded; see §8.

```jsonc
{
  "schema_version": 2,
  "artifact": {                                  // [PROPOSED] whole object
    "kind": "parallm.parameter_export",
    "generated": "2026-11-23T10:00:00Z",
    "generator": {"name": "parallm-pybamm", "version": "0.1.0b1", "python": "3.14.10"},
    "migrated_from": null,                       // 1 when upgraded from a v1 artifact
    "source": {
      "path": "/abs/path/reports/assembly",
      "kind": "assembly_report | direct_json | parallm_export",
      "content_sha256": "..."                    // hash of the file actually consumed
    },
    "attestation": {
      "level": "ATTESTED | ATTESTED_EMPTY | UNVERIFIED | UNKNOWN",
      "basis": "manifest+gate+registry | none",
      "gate": {"path": "...", "sha256": "...", "n_approved": 1},
      "registry": {"path": "...", "sha256": "..."},
      "failures": []
    },
    "reported_claims": {},                       // user-supplied claims, never trusted
    "policy": {
      "approval_source": "gate",
      "validation_policy": "reject_rejected|flag_others",
      "missing_metadata": "preserve_sentinel"
    },
    "rubric_version": "rubric-v2"
  },
  "export": {                                    // [PROPOSED] whole object
    "status": "COMPLETE | PARTIAL | INTENTIONALLY_EMPTY | EMPTY_AFTER_FILTERING | EMPTY_UNVERIFIED",
    "n_requested": 1,
    "n_exported": 1,
    "n_skipped": 0,
    "n_rejected_validation": 0,
    "skipped": [],
    "limitations": []
  },
  "approved_only": true,                         // true ONLY when attested AND every entry APPROVED
  "approval_basis": "gate+manifest | unverified | not_applicable",   // [PROPOSED]
  "parameter_set": null,
  "parameters": {
    "ambient_temperature": {                     // entry keys remain canonical ids
      "value": 298.15,                           // existing numeric value
      "unit": "K",                               // existing field, string or NOT_RECORDED
      "original": {"value": 298.15, "unit": "K", "status": "recorded"},  // [PROPOSED]
      "canonical": {"value": 298.15, "unit": "K", "status": "recorded"}, // [PROPOSED]
      "pybamm_names": ["Ambient temperature [K]"],
      "origin": "ASSUMED",                       // [PROPOSED] registry status
      "source": {                                // [PROPOSED] from SourceRef / dossier.evidence
        "document_id": "chen2020_jes_167_080534",
        "doi_or_url": "10.1149/1945-7111/ab9050",
        "locator": "section \"Electrochemical properties and parameterization\"",
        "page": "NOT_APPLICABLE",
        "table": "NOT_RECORDED",
        "figure": "NOT_RECORDED",
        "quote": "...",
        "char_start": "NOT_RECORDED",
        "char_end": "NOT_RECORDED"
      },
      "evidence": {                              // [PROPOSED]
        "traceability": "ok",
        "quote_present": true,
        "quote_verification": "verified",
        "review_required": false
      },
      "validation": {                            // [PROPOSED]
        "state": "ACCEPTED",
        "results": "NOT_PERFORMED",
        "basis": "registry.validation_state"
      },
      "approval": {                              // [PROPOSED] from gate record
        "status": "APPROVED",
        "decision": "FIX",
        "approver": "owner",
        "timestamp": "2026-11-23T09:00:00Z",
        "rubric_version": "rubric-v2",
        "note": ""
      },
      "calibration": {"status": "NOT_CALIBRATED", "basis": "origin metadata; no fit report"},
      "conditions": {"cell": "LG M50 21700, extracted electrodes"},
      "notes": []
    }
  }
}
```

`table`/`figure` are proposed decomposed locator fields; today a single free-text `locator` may contain either (`docs/PARAMETER_REGISTRY.md` §1 item 9). Until the registry is extended they stay `NOT_RECORDED`, not guessed.

The PyBaMM overlay remains a bare `PARAMETERS = {name: value}` mapping (`export.py:174`); **no ParaLLM metadata is added to it**.

---

## 5. Validation and approval policy

Human approval and deterministic validation are different decisions and are reported separately.

| State (actual model) | Semantics | Proposed default export handling |
|---|---|---|
| `ACCEPTED` (the model's "validated" state) | deterministic review accepted the record | Eligible; state recorded verbatim. |
| `NEEDS_REVIEW` / pending | review not closed | Eligible **only with an explicit human approval**, and the entry is flagged `validation.disposition: "approved_with_pending_validation"` plus a limitation. A future `--validation-policy strict` would skip these; that flag is a proposed option, not current behaviour. |
| `REJECTED` | deterministic validation rejected the record | **Fail closed by default.** Skip and record `skipped[].reason = VALIDATION_REJECTED`. Even a gate approval must not silently override: require an explicit override with a recorded reason and approver (open decision §10). |
| `UNKNOWN` / unrecognised string | data-integrity problem | Fail closed for `ATTESTED`; for `UNVERIFIED`, include with `validation.state = UNKNOWN` and a limitation. |
| Missing field | no validation state recorded | `NOT_RECORDED` for direct inputs; for registry-backed values, join from the registry by `canonical_id`. If still absent, include with `NOT_RECORDED` and a limitation (never silently accepted as validated). |
| No validation run at all | `validate` is a standalone command; results are not persisted | `validation.results = NOT_PERFORMED`, `validation.state` from registry when available. |

Approval policy:

- `ATTESTED`: every exported parameter must have `approval.status = APPROVED` from the gate record; otherwise the artifact is downgraded to `UNKNOWN` and refused.
- `UNVERIFIED`: `approval.status = NOT_RECORDED`, `approved_only = false`, with an explicit warning in the CLI output and envelope.
- Explicit gate `REJECTED` records are reported as `approval.status = REJECTED` and never exported.
- Origin `CALIBRATED` never implies a recorded calibration run or an approval; calibration state uses the three-value vocabulary from §3.4.

The current `--gate` behaviour for registry-list sources remains unchanged.

---

## 6. Empty and partial export semantics

| Status | Condition | Exit / output |
|---|---|---|
| `COMPLETE` | `n_requested > 0`, `n_exported == n_requested`, no skips or limitations | Exit 0; `approved_only` reflects attestation. |
| `PARTIAL` | `n_exported > 0` and (`n_skipped > 0` or limitations exist) | Exit 0, but `export.status = PARTIAL`, `skipped[]` populated and a warning printed. Already partially implemented; make the reason explicit. |
| `INTENTIONALLY_EMPTY` | Attested assembly with no gate/zero approvals (`manifest.n_approved == 0`, `pybamm_export.json == {}`) | Exit 0, artifact written, status explicit, `approved_only = false`, `approval_basis = not_applicable`. Never described as an ordinary successful populated export. This is the committed `reports/assembly` case. |
| `EMPTY_AFTER_FILTERING` | `n_requested > 0` but every value was filtered (validation rejected, no mapped name, etc.) | Exit 2 (`E404`), **no file written**, same guard as the current PyBaMM path. |
| `EMPTY_UNVERIFIED` | Direct JSON input with zero usable values | Exit 2 (`E2xx`) unless an explicit `--allow-empty-unverified` override is given. |
| `INVALID_INPUT` | Malformed JSON, unsupported shape, unknown `schema_version`, contradictory manifest | Exit 2 (`E2xx`/`E404`), no file written, actionable message. |
| `FAILED` | I/O or internal error | Existing `E199`/non-zero handling; never written as a successful artifact. |

For the PyBaMM formatter, all empty cases remain fatal `E404` as implemented in the remediation (an overlay with no parameters is not useful). `export.status` is still emitted in the CLI envelope for observability.

`complete` in the CLI envelope is retained and defined precisely as `status == COMPLETE`; the v1 artifact's `complete` boolean is retained for v1 output only.

---

## 7. Re-export and schema migration strategy

1. **Versioning.** Artifact v2 is introduced behind `--schema-version {1,2}` with **v1 remaining the default** for one release; switch the default to 2 once consumers have migrated. The CLI response envelope stays at `schema_version: 1`.
2. **Reader normalisation.** A single internal reader accepts:
   - v1 flat dict (`{"p": 1.23}`) → values with `NOT_RECORDED` metadata;
   - v1 artifact (`{"parameters": {"p": {"value": 1.23, "unit": "K", "pybamm_names": [...]}}}`) → nested entries parsed and preserved;
   - v2 artifact → full metadata preserved.
   Numeric extraction must handle both scalar values and `{"value": …}` entries; this is the direct fix for P5.
3. **Re-export trust.** An incoming `artifact.attestation` is re-verified (manifest, gate hash, registry hash, artifact hash). If verification fails, the outgoing artifact is `UNVERIFIED` with `attestation.downgraded_from` and the failure reason; `approved_only` becomes `false`. A v1 artifact always migrates to `UNVERIFIED` because v1 carried no provenance.
4. **Migration metadata.** Set `artifact.migrated_from = 1`, preserve all values/units/limitations exactly, add sentinels for unavailable fields, and never synthesise approval or validation states.
5. **Unknown future versions.** Refuse with an actionable message naming the supported versions; do not silently downgrade.
6. **Round-trip invariant.** Re-exporting a v2 artifact with no new source of approval must preserve every value and every recorded status; it may only *downgrade* trust, never upgrade it.

---

## 8. Backward compatibility

Investigation results:

- There is **no JSON Schema file** in the repository; the artifact contract is implicit in `export.py`, `docs/CLI.md` and tests.
- In-repo consumers of the **CLI envelope** are `tests/unit/test_cli_core.py:35`, `tests/unit/test_cli_release_findings.py:56`, and the export tests in `test_cli_science.py` / `test_cli_pipeline.py`. They assert `schema_version == 1`, `data.parameters`, `n_exported`, `skipped`, `complete`. These keys are preserved.
- `tests/unit/test_cli.py:136` and `tests/integration/test_cli_pipeline.py:47` read the **assembly-produced** `pybamm_export.json` as a flat dict. That file and the assembly manifest are unchanged by this proposal.
- No script or benchmark consumes the export artifact; no migration of existing files is required.
- Config `schema_version = 1` (`cli_app/config.py`) is unrelated and unchanged.

Impact of the proposal:

- v1 output remains byte-shape compatible when `--schema-version 1` is used; the only behavioural changes are the trust/status classification and the new empty-export errors (P6), which are intentional correctness fixes.
- v2 adds fields but keeps `parameters[<id>].value`/`unit`/`pybamm_names`, so simple readers continue to work.
- `approved_only` stays a boolean (false for empty exports) to avoid breaking type expectations; `export.status` and `approval_basis` disambiguate. A v1 consumer reading an empty v2 artifact sees `approved_only: false` and must consult `export.status` before concluding values were unapproved.
- No existing export needs rewriting; v2 migration happens lazily on re-export.

---

## 9. Test plan

All tests are **to be added**, not part of this proposal.

**Unit (trust and status)**

- `ATTESTED` only when manifest + gate hash + registry hash + (proposed) artifact hash all verify; tampering with any one downgrades to `UNKNOWN`/`UNVERIFIED`.
- A direct dict with `approved_only: true` in the input still yields `approved_only: false` and `UNVERIFIED`; the claim is preserved under `reported_claims`.
- Config `paths.gate` is ignored for direct dict input (documented behaviour), and the emitted trust level makes that safe.
- Per-parameter approval comes from the gate record, not from dossier `approval.status` or origin metadata.
- `REJECTED` validation → skipped with `VALIDATION_REJECTED`; `NEEDS_REVIEW` → included with explicit flag/limitation; missing state → sentinel + limitation.
- `NOT_RECORDED` / `NOT_PERFORMED` / `NOT_APPLICABLE` / `UNKNOWN` sentinels survive round-trips.
- Calibration state uses the agreed three-value vocabulary and never says `NOT CALIBRATED` for an origin `CALIBRATED` record without a fit report.

**Integration (formats and files)**

- Assembly → export with gate produces `ATTESTED`, `COMPLETE`, populated artifact; no gate produces `INTENTIONALLY_EMPTY` with no file-write error.
- Partial export (e.g. `neg_activation_energy` with no PyBaMM name) produces `PARTIAL` with `skipped[]` reasons for both formats.
- All-filtered export produces `E404` and writes no file (JSON and PyBaMM).
- Re-export of `{"parameters": {"p": {"value": 1.23}}}` preserves `p` instead of emptying it.
- v1 → v2 migration preserves values, sets `migrated_from: 1` and `UNVERIFIED`.
- CLI envelope keys and `schema_version: 1` remain unchanged; `--schema-version 1` produces the legacy artifact shape.
- PyBaMM overlay still contains only `PARAMETERS = {...}` with installed names; no metadata leaks into it.

**Regression guards**

- `examples/candidate_archived.json` still fails `physical_plausibility` (no fixture edits).
- Existing `test_export_registry_requires_gate` and overwrite/E404 tests keep passing.

---

## 10. Open architectural decisions

1. **Strong attestation:** add `[PROPOSED] manifest.outputs_sha256["pybamm_export.json"]` in `assemble`. Without it, manifest-based attestation is weak (values could be edited after assembly). Recommended: add the hash; it is a one-line manifest extension and does not move the gate.
2. **Dossier approval (M1):** stamp gate approvals onto dossiers so `report.json` is self-contained. Until then, the gate file is the only authoritative approval source. Recommended: yes.
3. **REJECTED + human approval:** fail closed by default. Decide whether an explicit `--override-rejected --reason …` with recorded approver is permissible, and whether it requires two approvers.
4. **NEEDS_REVIEW default:** include with explicit flag (recommended, preserves current scientific practice of human escalation), or skip by default with an opt-in. Decide before implementing `--validation-policy strict`.
5. **Quote storage:** full verbatim quote (faithful but large) versus quote hash plus locator. Recommended: keep the quote, since dossiers are designed to be self-defending.
6. **v2 default timing:** one release of opt-in v2, then flip the default; confirm the owner accepts the deprecation window.
7. **Signing:** cryptographic signing of artifacts is out of scope; hash-based attestation only. Decide later if cross-machine trust is required.

### 10.1 What the hashes do and do not establish

`ATTESTED` means the exported values are consistent with a **locally recorded chain** of manifest, gate, registry and assembly artifact hashes. It is an integrity check, not an authenticity check:

- Replacing the manifest, gate, registry and artifact **together** can create another internally consistent chain that also verifies as `ATTESTED`.
- The hashes do not authenticate file origin, prove who wrote a gate record, or verify reviewer identity. `approver` is a string copied from the gate file.
- Digital signatures and trusted identity verification are outside the current implementation scope.
- `ATTESTED` must therefore never be described as cryptographically authenticated.

Path handling: absolute paths recorded by `parallm assemble` are used as-is; relative paths resolve against the **manifest directory**, not the process CWD; relative `..` traversal segments are refused; symlinks are followed by `Path.resolve()`, so hashes verify content, not file identity.

The manifest's `target_config.sha256` and `report.json` are **recorded for reproducibility but are not verified by export**. Only the manifest, gate, registry and assembly artifact hashes participate in attestation.
8. **Direct JSON inputs:** keep them legal but `UNVERIFIED` (recommended, preserves the documented "approved-export JSON file" source), or require a gate for every non-assembly source (stricter, would break current tests and documented usage).

---

## Concise comparison: current vs proposed

| Aspect | Current | Proposed |
|---|---|---|
| Approval source | Gate for registry lists only; ignored for dicts | Gate record required for `ATTESTED`; dict inputs `UNVERIFIED` |
| `approved_only` | Always `true` | `true` only when attested and every entry approved; `false` otherwise |
| Artifact provenance | `source` path string only | `artifact` block with attestation level, hashes, policy, generator |
| Parameter metadata | `value`, `unit`, `pybamm_names` | + origin, source/quote/locator, traceability, validation, approval, calibration, conditions |
| Missing values | `null` or absent | Explicit sentinel vocabulary |
| `REJECTED` validation | Exported normally | Skipped by default with reason; override is an open decision |
| Empty export | `complete: true`, indistinguishable | `INTENTIONALLY_EMPTY` / `EMPTY_AFTER_FILTERING` / `EMPTY_UNVERIFIED`; latter two fatal |
| Re-export | Silently empties nested entries | Nested entries parsed; trust can only downgrade; v1 migrates lazily |
| PyBaMM overlay | Bare `{name: value}` | Unchanged; metadata stays in JSON artifact |
| Schema version | Artifact v1, CLI envelope v1 | Artifact v2 opt-in, envelope unchanged at v1 |

**Preserved by design:** approval at assembly, the `ApprovalGate` record format, `pybamm_export.json` shape, manifest contents (plus one proposed hash), CLI envelope, PyBaMM overlay, `E404` empty-overlay guard, and the archived fixture's genuine failed check.

## 11. Implementation status (2026-11-23)

**Implemented.** All four phases and every confirmed decision are in place:

- **Phase 1:** `assemble` records `manifest.outputs_sha256["pybamm_export.json"]`; `cli_app/artifact.py` verifies manifest, gate, registry and artifact hashes and establishes `ATTESTED`, `ATTESTED_EMPTY`, `UNVERIFIED` or `UNKNOWN`. Contradictory/corrupted hashes fail closed with `E404`; user-supplied approval claims are recorded under `artifact.reported_claims` and never trusted.
- **Phase 2:** `read_artifact()` accepts v1 flat dicts, v1/v2 ParaLLM artifacts (including nested `{"value": …}` entries) and registry lists; unsupported schema versions are rejected with `E201`. Exports distinguish `COMPLETE`, `PARTIAL`, `INTENTIONALLY_EMPTY` and `EMPTY_AFTER_FILTERING`; overwrite protection is unchanged.
- **Phase 3:** v2 entries carry origin, original/canonical units, source document, locator, verbatim quote, traceability, quote-verification state, validation state, gate approval record, calibration state and conditions, using the proposed sentinel vocabulary. `REJECTED` validation fails closed (no override); `NEEDS_REVIEW` requires explicit approval and emits a warning; `UNKNOWN` is never promoted.
- **Phase 4:** schema v1 remains the default; v2 is opt-in via `--schema-version 2`; the CLI envelope remains `schema_version: 1`; the PyBaMM overlay is byte-shape unchanged with no ParaLLM metadata injected.

22 focused regression tests were added in `tests/unit/test_json_export_trust.py`, covering every required case and round-trip preservation of values and recorded metadata.

### Deviations / clarifications relative to the proposal

1. **Approval after re-export:** when a v2 artifact's attestation cannot be re-verified, stored approval fields are preserved for provenance but marked `"verified_on_export": false` (a small proposed field addition). `approved_only` remains `false`, so no trust is upgraded.
2. **Attested registry lists:** a direct registry list with an explicit `--gate` is classified `ATTESTED` with `basis: "gate"` (no manifest). This follows confirmed decision 2 (approval through the actual gate record) and does not weaken manifest-based attestation for assembly artifacts.
3. **Legacy manifests:** a manifest lacking the new artifact hash or gate details is **downgraded to `UNVERIFIED`** with an explicit note rather than failing closed. Hash mismatches, missing gate files and approval disagreements still fail closed with `E404`.
4. **Dossier approval stamping** (confirmed decision 5: permitted but not required) was **not** implemented; the gate file remains the sole authoritative approval source.
5. **`validation.results`** is always `NOT_PERFORMED`: the `validate` command does not persist its `ReviewReport`, and no persistence was added in this implementation.
6. **`EMPTY_UNVERIFIED`** is implemented as a fatal `E404` for direct file inputs with no values; intentionally empty assembly outputs remain a successful `INTENTIONALLY_EMPTY` export.
7. The comparison table above described the pre-implementation state; the implemented behaviour matches the "Proposed" column except for the clarifications above.

## 12. Adversarial-audit remediation (2026-11-23)

Three HIGH and four MEDIUM findings from the post-implementation adversarial audit were fixed. 51 new regression tests live in `tests/unit/test_export_trust_hardening.py`; the existing round-trip test was tightened to require preserved `ATTESTED` trust.

- **H1 — validation-state normalisation:** one `normalise_validation_state()` canonicalises every source (registry, v1, v2, nested, re-export). Null/absent → `NOT_RECORDED`; recognised sentinels and decisions survive; anything else → `UNKNOWN` and is skipped (`E404`). Normalisation is applied **after** metadata merging so a raw stored string cannot overwrite a validated state.
- **H2 — gate validation:** `assembly/gate.py::validate_gate_records()` is the single validation path used by assembly, attestation and both export formats. Duplicate parameter ids (including conflicting decisions and different representations of the same id) are rejected with `E201`; no first/last-wins resolution remains. Gate approval counts are computed from validated unique records.
- **H3 — v2 re-verification:** the reader now passes the embedded `artifact.attestation` object, not the whole artifact block. `derived_content_sha256` records a canonical digest of the derived artifact excluding the digest and volatile notes. Re-export re-verifies the original manifest/gate/registry/assembly artifact chain, the derived digest and value equality with the original artifact. `ATTESTED`/`ATTESTED_EMPTY` are preserved only when every check passes; otherwise trust is downgraded to `UNVERIFIED` with `downgraded_from` set to the original level and a reason in `notes`. Unverified claims are never upgraded.
- **M1:** v1 artifacts no longer report `complete: true` for an intentionally empty export; v2 reports `INTENTIONALLY_EMPTY`.
- **M2:** NaN, ±Infinity and boolean values are rejected with `E201`; JSON serialisation uses `allow_nan=False`.
- **M3:** duplicate JSON object keys and duplicate registry canonical ids raise `E201` instead of last-record-wins.
- **M4:** a registry-list JSON file supplied via `--from` is used as the registry for PyBaMM export; no redundant `--registry` is required.
- **M5:** malformed gate records map to `E201` in both assembly and export (no `E199`).
- **Phase 5:** boolean `schema_version` rejected; relative manifest paths resolved against the manifest directory with `..` traversal refused; null/missing validation semantics unified; see §10.1 for what is *not* verified.

**Update to deviation 1 above:** `verified_on_export: false` is now added only when a v2 artifact's attestation **cannot** be re-verified. Valid attested re-exports preserve trust and keep stored approval fields unchanged.
