# Examples gallery

Runnable, deterministic examples live in the repository's `examples/`
directory. They use only committed public data (or locally acquired private
data where noted), make no network call and no LLM call.

| Example | What it shows |
|---|---|
| `01_retrieval_recall.py` | Gold-passage recall@k for the real BM25 retrieval arm on the public v3 benchmark |
| `02_synthetic_validation_figure.py` | Regenerates the V2.4 held-out RMSE figure (5-seed stability + 18-run mismatch) |
| `03_assemble_dossiers.py` | Per-parameter dossier assembly over the LG M50 registry |

Run them from the repository root:

```bash
.venv/bin/python examples/01_retrieval_recall.py
.venv/bin/python examples/02_synthetic_validation_figure.py
.venv/bin/python examples/03_assemble_dossiers.py
```

Each script accepts `--out-dir` and writes outputs under
`examples/output/<name>/` (gitignored, regenerable). Example 1 and 2 run
without the Chen2020 article; example 3 prints a note when traceability flags
are present because the article text is absent locally (see
`docs/REMAINING_TASKS.md` item 1 in the repository).

These examples demonstrate the software workflow and the retrieval/evidence
layers. They are **not** experimental validation and do not prove parameter
identifiability.
