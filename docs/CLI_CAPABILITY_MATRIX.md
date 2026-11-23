# CLI capability matrix

Status: derived from direct source inspection on 2026-11-23 (not from
documentation claims). The `parallm` CLI exposes only capabilities in the first
two categories. Scientific algorithms are never reimplemented in command
handlers.

## Fully implemented (library-level, safe to expose)

| Capability | Public API | CLI exposure |
|---|---|---|
| Document ingestion (text, PDF) | `literature.ingest.DocumentStore.ingest_text/ingest_pdf` | `extract` (PDF/text file or directory of them) |
| BM25 retrieval + RAG context | `literature.index.build_index`, `literature.retrieval.build_rag_context` | `extract` (internal step) |
| Extraction: offline deterministic + opt-in OpenAI-compatible LLM | `literature.extraction.run_extraction`, `OfflineDeterministicExtractor`, `OpenAICompatibleClient` | `extract` (offline default; LLM only with explicit `--live`) |
| Extraction schema validation | `registry.model.validate_extraction_schema` | `validate`, `extract` |
| Deterministic scientific checks | `validation.checks.review_candidate` and its individual checks | `validate` |
| Units canonicalisation | `registry.units.to_canonical`, `dimension_of` | `validate`, `explain` (via checks) |
| Evidence windows, conditions, quote verification | `literature.evidence.*` | `evidence`, `explain`, `assemble` (verification) |
| Registry (append-first, revisioned) | `registry.store.RegistryStore` | `evidence`, `explain`, `export` (read-only) |
| Dossiers, rubric, conflict resolution, traceability, human gate | `assembly.*` | `assemble`, `explain` |
| Observability join | `assembly.observability.load_observability` | `assemble` |
| PyBaMM baseline simulation | `pybamm_engine.run`, `BaselineRunConfig.from_yaml` | `simulate` |
| Synthetic fitting + identifiability | `calibration.fitting.*`, `calibration.synthetic.*`, `calibration.identifiability.*` | `calibrate synthetic` (synthetic only) |
| Approved-only PyBaMM export | `assembly.AssemblyReport.pybamm_export(gate)` | `export` |

## Partially implemented (must be surfaced with limitations)

| Capability | Limitation |
|---|---|
| Experimental-condition extraction | Weak recall; offline extractor emits `temperature=None` / `cell_config=UNRESOLVED`; `condition_completeness` metric is 0.0 in offline reports. CLI renders `NOT CHECKED`/`UNRESOLVED`, never a pass. |
| Direct PyBaMM API containment | `pybamm_engine/` is the facade, but some scientific modules import PyBaMM directly. CLI reaches PyBaMM only through `pybamm_engine`. |
| Export | Registry/assembly export is a dict of approved values. No automatic Python-module generation; CLI writes a JSON artifact and an optional overlay that is validated against installed names. |
| Diagnostics | No `diagnostics` package exists; `parallm doctor` is implemented in the CLI with stdlib-only checks. |

## Not implemented (must not be exposed as operational commands)

| Capability | Evidence |
|---|---|
| Real-data calibration / fitting | `docs/REAL_DATA_FITTING_FEASIBILITY.md:3` explicitly recommends against it. |
| DOI / URL / online document acquisition | Only local text/PDF ingestion exists; `scripts/fetch_chen2020.py` requires an owner-supplied hash-verified PDF. |
| Closed-loop orchestration | `closed_loop/__init__.py` empty; `docs/ARCHITECTURE.md` marks it not started. |
| Automatic registry writes from extraction | Scientific rule 10; proposals require deterministic validation and explicit human approval. |
| Fine-tuning / online LLM for basic commands | Explicitly out of scope; help, version and doctor are fully offline. |
