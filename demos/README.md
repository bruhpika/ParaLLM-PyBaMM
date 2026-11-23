# Reproducible terminal demonstrations

VHS tapes for the CLI demonstrations embedded in the README. They run from the
repository root and use only committed fixtures; no network or LLM call is made.

Prerequisites (local tooling only, not project dependencies):

- `vhs` (`go install github.com/charmbracelet/vhs@latest`)
- `ttyd` (official prebuilt binary from `github.com/tsl0922/ttyd`)
- `ffmpeg`
- an editable/core install so `.venv/bin/python -m pybamm_closed_loop` works

Regenerate all GIFs:

```bash
export PATH="$(go env GOPATH)/bin:$PATH"
vhs demos/doctor.tape
vhs demos/evidence.tape
vhs demos/validate.tape
```

| Tape | Output | Command shown |
|---|---|---|
| `doctor.tape` | `docs/assets/parallm-doctor.gif` | `parallm doctor --deep` |
| `evidence.tape` | `docs/assets/parallm-evidence.gif` | `parallm evidence inspect ambient_temperature` |
| `validate.tape` | `docs/assets/parallm-validate.gif` | `parallm validate examples/candidate_archived.json` |

`examples/candidate_archived.json` is a verbatim archived extraction candidate;
the validation tape deliberately shows the genuine `FAILED` unit check and
`NOT CHECKED` states rather than a curated success.
