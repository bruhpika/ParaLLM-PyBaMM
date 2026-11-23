# CLI design system — ParaLLM-PyBaMM

Status: authoritative reference for the `parallm` terminal interface (v0.1.0b1).

## 1. Design exploration record

Stitch MCP was used for genuine visual exploration before implementation.

- Stitch project: `projects/10889469672586309247` — "ParaLLM-PyBaMM CLI Design System".
- Nine terminal-oriented references were generated: startup/identity, first-run
  setup, research workspace overview, extraction output, evidence provenance,
  validation report, calibration results, export confirmation, and diagnostics/
  error presentation.
- Stitch returned screen IDs successfully, but `get_screen_code`,
  `get_screen_image` and `generate_and_fetch_code` failed in this environment
  (`invalid argument` / HTTP `401` on the download URL). The rendered assets
  could therefore not be inspected directly.
- **Documented alternative:** the visual direction was fixed from (a) the
  explicit design prompts used for those references, (b) the palette and layout
  constraints in the project brief, and (c) local Rich rendering tests that
  assert exact rendered text at 80/100/120 column widths. No implementation
  work was blocked on the unavailable Stitch asset retrieval.
- Root cause investigated against upstream reports (2026-11-23): the direct
  `htmlCode.downloadUrl` / `screenshot.downloadUrl` fetches require Google
  credentials and redirect API-key-only clients to sign-in
  (`google-labs-code/stitch-skills#94`, closed with a "Remix the project"
  mitigation); the required remedy is the MCP `download_file` tool using the
  file resource name from `get_screen`, not the raw URL. The separate
  `invalid argument` failures match a client/schema compatibility issue
  (`gemini-cli-extensions/stitch#12`) and the need for the bare numeric
  `projectId`. This client exposes neither `download_file` nor `list_screens`,
  so retrying `get_screen_code`, `get_screen_image` and
  `generate_and_fetch_code` (including on a fresh project) could not be made
  to work without changing the MCP connection (OAuth/gcloud ADC via the Stitch
  stdio proxy is the documented stable setup). The documented alternative
  above therefore remains the design basis.

Stitch references are *layout* references only. Browser components are not
reproduced in the terminal; they are translated into aligned text, tables,
thin rules and compact status lines.

Implementation status: all components in §5 are implemented in
`cli_app/render.py`, including the optional `footer(next_command)` used by
`doctor` (when no configuration exists) and `extract` (suggesting `validate`).
The first-run screen is unchanged from the approved reference. Textual is
deliberately not adopted: no workflow requires a full-screen interactive TUI.
Visual regression is verified by `tests/unit/test_cli_rendering.py` and by the
reproducible VHS tapes in `demos/`.

## 2. Visual principles

1. Information hierarchy over decoration. Heading, label, value, note — in that
   order, always aligned identically.
2. Meaningful colour only. Colour encodes status; it never decorates.
3. Precision. Uppercase section labels, fixed label column, right-aligned
   numerics, fixed scientific notation (`1.20e-12`).
4. Restraint. No banner ASCII art, gradients, emoji, fake confidence scores,
   spinners without progress, or animation delays.
5. Consistency. Every command uses the same header, section, status and footer
   components through a shared rendering layer.

## 3. Palette

Foreground colours only; the terminal background is never repainted except for
the narrow error notice. Values are hex (Rich truecolor) with ANSI-safe intent.

| Role | Hex | Rich style intent | Use |
|---|---|---|---|
| Background (panels only) | `#12161B` | `on #12161B` | error/notice panel only |
| Primary text | `#E6EDF2` | default/bold for headings | labels, values |
| Secondary text | `#8B98A5` | `dim` | metadata, notes, unavailable fields |
| Accent | `#5FB6C4` | `bold #5FB6C4` | section labels, identifiers, links |
| Accent dim | `#2E5F6B` | `#2E5F6B` | rules, separators |
| Success | `#7FB98A` | `bold #7FB98A` | PASSED, COMPLETED, FOUND |
| Warning | `#D9A441` | `bold #D9A441` | WARNING, UNCERTAIN, MISSING |
| Error | `#C96A65` | `bold #C96A65` | FAILED, ERROR |
| Neutral line | `#2A333C` | `#2A333C` | horizontal rules |

Colour is disabled automatically when output is redirected/piped, when
`NO_COLOR` is set, or with `--no-color`. Status words are always printed even
without colour, so meaning survives.

## 4. Typography and layout

- Monospace throughout; no font switching, italics, or unusual glyphs beyond
  the block character `█` used in progress bars.
- Headings: `UPPERCASE`, bold accent, followed by a thin rule.
- Key/value rows: label padded to a 14-character column, two spaces, value.
  Long labels wrap onto the next line with a four-space continuation indent.
- Tables: no box, no row separators, one space of cell padding. Numeric columns
  are right-aligned; text columns left-aligned.
- Notes: `dim`, indented two spaces, never more than two lines where possible.
- Content width: 100 columns default; reduced to terminal width (minimum 40).
  Tables truncate long parameter names with `…` and expose full values in
  `--json` output. No horizontal scrolling.

## 5. Component vocabulary

| Component | Definition |
|---|---|
| `header(title, context)` | `ParaLLM-PyBaMM  v0.1.0b1` left, `context` right; one rule below. Printed once per invocation. |
| `section(title)` | Uppercase accent label + rule. |
| `kv(rows)` | Aligned label/value grid. Missing values render as `unavailable`, never blank-inferred. |
| `table(columns, rows)` | Boxless aligned table; status column uses badges. |
| `badge(status)` | `PASSED`, `WARNING`, `FAILED`, `NOT CHECKED`, `UNRESOLVED`, `NOT CALIBRATED`. |
| `notice(kind, text)` | One-line indented note; `WARN`/`ERROR` variants use the status colour. |
| `error(code, what, why, action)` | Thin-bordered panel with four labelled lines; no stack trace unless `--debug`. |
| `progress` | Block-character bar plus processed/total/elapsed/current rows. Only for operations with real progress; suppressed in quiet/JSON/non-TTY modes. |
| `footer(next_command)` | `next: parallm …` in dim text, optional. |

## 6. Status conventions

Validation/machine statuses (never conflated):

- `PASSED` — check was executed and found no problem.
- `WARNING` — check was executed; review is needed.
- `FAILED` — check was executed and found a problem.
- `NOT CHECKED` — check was **not executed** (missing input/dependency). Never
  rendered as a pass.

Scientific provenance statuses are taken verbatim from the registry:
`LITERATURE_DERIVED`, `CALCULATED`, `ASSUMED`, `CALIBRATED`, `USER_SUPPLIED`,
`UNRESOLVED`. A parameter is labelled `NOT CALIBRATED` unless a calibration
record actually exists for it. Extraction output is always prefixed
`CANDIDATES ONLY — not validated, not calibrated`.

## 7. Header/footer conventions

```
ParaLLM-PyBaMM                                  v0.1.0b1
Literature-driven parameter intelligence
────────────────────────────────────────────────────────────
```

Footer is a single dim `next:` line where a next step genuinely exists.
`--quiet` and `--json` suppress header, footer and all decorative rules.

## 8. Error model

Structured errors carry a stable code, what happened, known cause, and a
concrete next action. Reserved ranges:

| Range | Meaning |
|---|---|
| `E1xx` | configuration / workspace |
| `E2xx` | input / file format |
| `E3xx` | environment / dependency |
| `E4xx` | scientific check / export safety |

Examples: `E104` config not found; `E202` malformed JSON; `E301` optional
dependency missing; `E302` PyBaMM version mismatch; `E402` traceability failure;
`E403` overwrite refused.

Exit codes: `0` success, `1` scientific/check failure, `2` usage/config error,
`3` missing dependency/environment, `130` interrupted.

## 9. JSON envelope

`--json` emits exactly one JSON object on stdout, with no styling:

```json
{"schema_version":1,"command":"validate","status":"completed","data":{},"diagnostics":[]}
```

Human-readable diagnostics and errors go to stderr in normal mode; in `--json`
mode they are carried in `diagnostics` so machine consumers never need to parse
prose.
