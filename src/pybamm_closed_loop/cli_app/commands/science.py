"""Scientific workflow commands: extraction, validation, evidence and provenance."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import typer

from ..paths import input_path
from ..context import State
from ..errors import DependencyError, InputError, ParseError
from ..inputs import load_json
from ..render import footer, kv, make_progress, notice, section, status_text, table

evidence_app = typer.Typer(
    name="evidence",
    help="Inspect the evidence attached to registry parameters and dossiers.",
    add_completion=False,
    no_args_is_help=True,
)


def _state(ctx: typer.Context) -> State:
    state = ctx.obj
    if not isinstance(state, State):
        raise InputError("CLI state was not initialised.", action="Report this as a CLI bug.")
    return state


def calibration_state(record: dict[str, Any], fit: dict[str, Any] | None) -> str:
    """Single source of truth for the human-readable calibration state.

    A recorded synthetic fit is the only positive evidence of a calibration
    run.  ``status=CALIBRATED`` in a registry record describes how the literature
    value was originally obtained; it is reported as a literature fit and is
    never promoted to a recorded calibration by origin metadata alone.
    """
    if fit is not None:
        return "SYNTHETIC FIT RECORDED"
    if record.get("status") == "CALIBRATED":
        return "LITERATURE FIT REPORTED"
    return "NOT CALIBRATED"


def _find_calibration_fit(
    state: State, parameter: str, explicit: Path | None = None
) -> tuple[Path | None, dict[str, Any] | None]:
    """Locate a recorded synthetic fit for ``parameter`` (never infer one)."""
    fit: dict[str, Any] | None = None
    fit_path = explicit
    if fit_path is None and state.config is not None:
        candidate = state.config.resolve(state.config.paths.p2_results)
        if candidate is not None and candidate.is_dir():
            for report_file in sorted(candidate.rglob("report.json")):
                payload = load_json(report_file, description="calibration report")
                if isinstance(payload, dict) and parameter in (payload.get("recovery") or {}):
                    fit_path, fit = report_file, payload
                    break
    if fit is None and fit_path is not None:
        payload = load_json(fit_path.expanduser().resolve(), description="calibration report")
        recovery = payload.get("recovery") if isinstance(payload, dict) else None
        fit = payload if isinstance(recovery, dict) and parameter in recovery else None
    return fit_path, fit


def _load_records(state: State, explicit: Path | None) -> list[dict[str, Any]]:
    path = input_path(state, explicit, "registry", what="registry", expect="file")
    data = load_json(path, description="registry")
    if not isinstance(data, list):
        raise InputError("Registry must be a JSON list.", action="Point --registry at a registry file.")
    return data


def _load_dossiers(state: State, explicit: Path | None, *, optional: bool) -> list[dict[str, Any]]:
    if explicit is None:
        config = state.config
        default = (
            state.workspace() / "reports" / "assembly"
            if config is not None and config.workspace is not None
            else Path.cwd() / "reports" / "assembly"
        )
    else:
        default = explicit.expanduser().resolve()
    report_file = default / "report.json" if default.is_dir() else default
    if not report_file.is_file():
        if optional:
            state.warn(f"Assembly report not found at {report_file}; dossier fields are unavailable.")
            return []
        raise InputError(
            "Assembly report not found.",
            why=f"Expected: {report_file}",
            action="Run `parallm assemble` or pass --report-dir.",
        )
    payload = load_json(report_file, description="assembly report")
    dossiers = payload.get("parameters", []) if isinstance(payload, dict) else []
    if not isinstance(dossiers, list):
        raise ParseError("Assembly report has no 'parameters' list.", why=str(report_file))
    return dossiers


def _find_records(records: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    exact = [r for r in records if r.get("canonical_id") == name]
    if exact:
        return exact
    needle = name.lower()
    return [r for r in records if needle in str(r.get("canonical_id", "")).lower()]


def _load_extract_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    file = path.expanduser().resolve()
    if not file.is_file():
        raise InputError("Extraction config not found.", why=f"Expected: {file}", action="Pass an existing YAML/JSON file.")
    raw = file.read_text(encoding="utf-8")
    try:
        if file.suffix.lower() == ".json":
            data = json.loads(raw)
        else:
            import yaml

            data = yaml.safe_load(raw)
    except (ValueError, OSError) as exc:
        raise ParseError("Extraction config is invalid.", why=str(exc)) from exc
    if not isinstance(data, dict):
        raise ParseError("Extraction config must be a mapping.", why=str(file))
    return data


def extract(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="PDF/text file or directory of source documents."),
    out: Path = typer.Option(..., "--out", help="Output directory for candidates and store."),
    extract_config: Path | None = typer.Option(
        None, "--extract-config", help="YAML/JSON with parameter_names, document_kind and k."
    ),
    parameter: list[str] = typer.Option(
        [], "--parameter", help="Canonical parameter name to look for (repeatable)."
    ),
    provider: str = typer.Option("offline", "--provider", help="offline (default) or llm."),
    live: bool = typer.Option(
        False, "--live", help="Explicit opt-in for a network LLM call."
    ),
    k: int = typer.Option(8, "--k", help="Number of passages to retrieve."),
) -> int:
    """Extract candidate parameters from local PDF/text documents."""
    from ...literature.extraction import run_extraction
    from ...literature.index import build_index
    from ...literature.ingest import DocumentStore, validate_document_id
    from ...literature.retrieval import RetrievalFacets, build_rag_context

    state = _state(ctx)
    cfg = _load_extract_config(extract_config)
    names = list(parameter) or list(cfg.get("parameter_names") or [])
    if not names:
        raise InputError(
            "No target parameter names were given.",
            why="The offline extractor only recognises explicitly named parameters.",
            action="Pass --parameter NAME at least once or set parameter_names in --extract-config.",
        )
    if provider not in ("offline", "llm"):
        raise InputError("Unsupported extraction provider.", why=f"Got {provider!r}.", action="Use offline or llm.")
    if provider == "llm" and not live:
        raise InputError(
            "Network extraction requires explicit opt-in.",
            why="--provider llm was given without --live.",
            action="Add --live and set PYCL_LLM_API_KEY / PYCL_LLM_MODEL to run a live extraction.",
        )
    k = int(cfg.get("k", k))
    document_kind = str(cfg.get("document_kind", "paper"))
    source_path = source.expanduser().resolve()
    if not source_path.exists():
        raise InputError("Source not found.", why=f"Expected: {source_path}", action="Pass an existing file or directory.")

    files: list[Path]
    if source_path.is_dir():
        files = sorted(
            p
            for p in source_path.rglob("*")
            if p.is_file() and p.suffix.lower() in (".pdf", ".txt", ".md")
        )
        if not files:
            raise InputError("No supported documents found.", why=f"Searched: {source_path}", action="Provide PDF or text files.")
    else:
        if source_path.suffix.lower() not in (".pdf", ".txt", ".md"):
            raise InputError(
                "Unsupported document format.",
                why=f"Got {source_path.suffix!r}; ingestion supports PDF and text.",
                action="Convert the document to PDF or plain text first.",
            )
        files = [source_path]

    out_dir = out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    store_root = out_dir / "literature_store"
    store = DocumentStore(store_root)
    progress = make_progress(state.console, "Ingesting documents", enabled=not state.quiet)
    ingested_ids: list[str] = []
    with progress:
        task = progress.add_task("Ingesting documents", total=len(files))
        for file in files:
            stem = re.sub(r"[^A-Za-z0-9._-]", "_", file.stem)[:80]
            document_id = stem or "document"
            validate_document_id(document_id)
            if file.suffix.lower() == ".pdf":
                if importlib.util.find_spec("pypdf") is None:
                    raise DependencyError(
                        "PDF ingestion requires pypdf.",
                        why="pypdf is an optional dependency and is not installed in this environment.",
                        action="Install the ecosystem extra: pip install 'parallm-pybamm[ecosystem]'.",
                    )
                try:
                    store.ingest_pdf(document_id, file, kind="pdf")
                except ModuleNotFoundError as exc:
                    raise DependencyError(
                        "PDF ingestion requires pypdf.",
                        why=f"{exc}",
                        action="Install the ecosystem extra: pip install 'parallm-pybamm[ecosystem]'.",
                    ) from exc
            else:
                store.ingest_text(document_id, file.read_text(encoding="utf-8", errors="replace"), kind=document_kind)
            ingested_ids.append(document_id)
            progress.update(task, advance=1)

    index = build_index(store)
    extractor = _client(provider, live)
    # Resolve the requested names' declared units from the configured registry;
    # unknown names are left out so the extractor simply abstains for them.
    parameter_units: dict[str, str] = {}
    registry_path = (
        state.config.resolve(state.config.paths.registry)
        if state.config is not None else None
    )
    if registry_path is None or not registry_path.is_file():
        repo_registry = Path(__file__).resolve().parents[4] / "data/registry/registry.json"
        if repo_registry.is_file():
            registry_path = repo_registry
    if registry_path is not None and registry_path.is_file():
        for record in load_json(registry_path, description="registry"):
            if isinstance(record, dict) and record.get("canonical_id") in names:
                unit = record.get("value_unit") or record.get("normalized_value_unit")
                if isinstance(unit, str) and unit:
                    parameter_units[str(record["canonical_id"])] = unit
    batches = []
    n_evidence = 0
    for document_id in ingested_ids:
        facets = RetrievalFacets(parameter_names=names,
                                 parameter_units=parameter_units)
        context = build_rag_context(facets, index, k=k)
        n_evidence += len(context.segments)
        batches.append(run_extraction(extractor, context))

    candidates = [candidate.to_dict() for batch in batches for candidate in batch.candidates]
    valid = sum(1 for c in candidates if c.get("schema_ok"))
    invalid = len(candidates) - valid
    result = {
        "provider": batches[0].provider if batches else "none",
        "documents": ingested_ids,
        "parameter_names": names,
        "n_evidence_segments": n_evidence,
        "candidates": candidates,
        "n_candidates": len(candidates),
        "n_schema_valid": valid,
        "n_schema_invalid": invalid,
        "abstained": [b.abstain_reason for b in batches if b.abstained],
    }
    (out_dir / "candidates.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )

    if not state.quiet and not state.json_mode:
        section(state.console, "EXTRACTION")
        kv(
            state.console,
            (
                ("Status", "COMPLETED"),
                ("Documents", len(ingested_ids)),
                ("Parameters requested", len(names)),
                ("Evidence segments", n_evidence),
                ("Candidates", len(candidates)),
                ("Schema valid", valid),
                ("Schema invalid", invalid),
                ("Abstained", len(result["abstained"])),
                ("Output", str(out_dir / "candidates.json")),
            ),
        )
        notice(state.console, "CANDIDATES ONLY — not validated, not calibrated.")
        footer(
            state.console,
            f"parallm validate {out_dir / 'candidates.json'} --documents {store_root}",
        )
        for reason in result["abstained"]:
            state.warn(reason)
    state.emit(result)
    return 0


def _client(provider: str, live: bool) -> Any:
    if provider == "offline":
        from ...literature.extraction import OfflineDeterministicExtractor

        return OfflineDeterministicExtractor()
    from ...literature.extraction import OpenAICompatibleClient

    try:
        return OpenAICompatibleClient()
    except RuntimeError as exc:
        raise DependencyError(
            "LLM client is not configured.",
            why=str(exc),
            action="Set PYCL_LLM_API_KEY and PYCL_LLM_MODEL, or use --provider offline.",
        ) from exc


def _payload_from_record(record: dict[str, Any]) -> dict[str, Any]:
    evidence = record.get("evidence") or {}
    source = evidence.get("source") or {}
    conditions = record.get("conditions") or {}
    status = str(record.get("status", ""))
    qualifier = {
        "CALCULATED": "calculated",
        "ASSUMED": "assumed",
        "CALIBRATED": "fitted",
        "USER_SUPPLIED": "measured",
    }.get(status, "unknown")
    return {
        "parameter_name": record.get("canonical_id", ""),
        "value": record.get("value"),
        "unit": record.get("value_unit") or "dimensionless",
        "definition": record.get("definition") or "UNRESOLVED",
        "material": "UNRESOLVED",
        "temperature": conditions.get("temperature_k"),
        "cell_config": conditions.get("cell") or "UNRESOLVED",
        "measurement_method": record.get("method") or "UNRESOLVED",
        "qualifier": qualifier,
        "context": evidence.get("context") or "",
        "source": {
            "document_id": source.get("document_id") or "",
            "locator": source.get("locator"),
            "page": source.get("page"),
            "quote": source.get("quote") or "",
        },
        "reported_uncertainty": record.get("reported_uncertainty"),
    }


def validate(
    ctx: typer.Context,
    input_file: Path = typer.Argument(..., help="Extraction payload JSON (one or a list)."),
    documents: Path | None = typer.Option(None, "--documents", help="Raw document store for quote verification."),
    registry: Path | None = typer.Option(None, "--registry", help="Registry directory for conflict and mapping checks."),
    check_pybamm_names: bool = typer.Option(
        False, "--check-pybamm-names", help="Verify PyBaMM mappings against the installed library."
    ),
    parameter_set: str = typer.Option("Chen2020", "--parameter-set"),
    strict: bool = typer.Option(False, "--strict", help="Treat warnings and NOT CHECKED as failures."),
) -> int:
    """Run deterministic scientific checks over extraction candidates."""
    from ...registry.model import validate_extraction_schema
    from ...registry.store import RegistryStore
    from ...validation.checks import (
        ReviewReport,
        check_conditions,
        check_definition,
        check_plausibility,
        check_provenance,
        check_pybamm_mapping,
        check_qualifier,
        check_value_unit,
        detect_conflict,
    )

    state = _state(ctx)
    path = input_file.expanduser().resolve()
    data = load_json(path, description="validation input")
    if isinstance(data, dict) and "canonical_id" in data and "value_unit" in data:
        items = [(_payload_from_record(data), "registry record")]
    elif isinstance(data, dict) and isinstance(data.get("candidates"), list):
        # The exact output of `parallm extract`: validate one result per
        # candidate payload, never the envelope as a single payload.
        items = []
        for index, item in enumerate(data["candidates"]):
            payload = item.get("payload") if isinstance(item, dict) else item
            if not isinstance(payload, dict):
                raise ParseError(
                    f"candidate #{index} is not an object.", why=str(path)
                )
            items.append((payload, "extraction candidate"))
    elif isinstance(data, dict):
        items = [(data, "extraction payload")]
    elif isinstance(data, list):
        items = [
            (_payload_from_record(item), "registry record")
            if isinstance(item, dict) and "canonical_id" in item and "value_unit" in item
            else (item, "extraction payload")
            for item in data
        ]
    else:
        raise ParseError("Validation input must be an object or a list of objects.", why=str(path))

    doc_texts: dict[str, str] = {}
    if documents is not None:
        from ..inputs import load_doc_texts

        doc_texts = load_doc_texts(documents.expanduser().resolve())

    store: RegistryStore | None = None
    if registry is not None:
        store = RegistryStore(registry.expanduser().resolve())
    elif state.config is not None:
        registry_path = state.config.resolve(state.config.paths.registry)
        if registry_path is not None and registry_path.parent.is_dir():
            store = RegistryStore(registry_path.parent)

    installed_names: list[str] | None = None
    if check_pybamm_names:
        from ...pybamm_engine import installed_parameter_names

        installed_names = installed_parameter_names(parameter_set)

    results: list[dict[str, Any]] = []
    total = {"PASSED": 0, "WARNING": 0, "FAILED": 0, "NOT CHECKED": 0}
    for payload, kind in items:
        report = ReviewReport()
        schema_ok, schema_reason = validate_extraction_schema(payload)
        report.add("schema", "ok" if schema_ok else "fail", schema_reason)
        for fn in (check_definition, check_conditions, check_qualifier):
            level, detail = fn(payload)
            report.add(fn.__name__, level, detail)
        if doc_texts:
            level, detail = check_provenance(payload, doc_texts)
            report.add("check_provenance", level, detail)
        else:
            report.add("check_provenance", "not_checked", "no --documents store supplied")
        try:
            canonical, value, _ = check_value_unit(payload)
            report.add("unit_conversion", "ok", f"converted to {value:g} {canonical}")
        except (ValueError, KeyError) as exc:
            report.add("unit_conversion", "fail", str(exc))
        level, detail = check_plausibility(payload, None)
        report.add("physical_plausibility", level, detail)
        if store is not None:
            level, detail = detect_conflict(payload, store)
            report.add("conflicting_evidence", level, detail)
            if installed_names is not None:
                level, detail = check_pybamm_mapping(payload, store, installed_names)
            else:
                level, detail = check_pybamm_mapping(payload, store)
            report.add("pybamm_mapping", level, detail)
        else:
            report.add("conflicting_evidence", "not_checked", "no registry supplied")
            report.add("pybamm_mapping", "not_checked", "no registry supplied")
        levels = {c.level for c in report.checks}
        state_name = (
            "REJECTED" if "fail" in levels
            else "NEEDS_REVIEW" if "warn" in levels or "not_checked" in levels
            else "ACCEPTED"
        )
        for check in report.checks:
            total[status_text(check.level).plain] += 1
        results.append(
            {
                "parameter": payload.get("parameter_name", ""),
                "kind": kind,
                "state": state_name,
                "checks": [
                    {"name": c.name, "level": status_text(c.level).plain, "detail": c.detail}
                    for c in report.checks
                ],
            }
        )

    failed = total["FAILED"] > 0
    needs_review = total["WARNING"] > 0 or total["NOT CHECKED"] > 0
    if not state.quiet and not state.json_mode:
        section(state.console, "VALIDATION REPORT")
        kv(
            state.console,
            (
                ("Input", str(path)),
                ("Items", len(results)),
                ("PASSED", total["PASSED"]),
                ("WARNING", total["WARNING"]),
                ("FAILED", total["FAILED"]),
                ("NOT CHECKED", total["NOT CHECKED"]),
            ),
        )
        for result in results:
            if len(results) > 1:
                section(state.console, result["parameter"] or "unnamed")
            table(
                state.console,
                ("CHECK", "STATUS", "DETAIL"),
                [(c["name"], c["level"], c["detail"]) for c in result["checks"]],
                status_columns=(1,),
            )
            kv(state.console, (("Decision", result["state"]),))
        notice(state.console, "A passed check is not proof of identifiability; extraction is not calibration.")
    state.emit(
        {"input": str(path), "summary": total, "results": results,
         "candidates": [payload for payload, _ in items]},
        status="failed" if failed else "completed",
    )
    return 1 if failed or (strict and needs_review) else 0


def evidence_list(
    ctx: typer.Context,
    registry: Path | None = typer.Option(None, "--registry", help="Registry JSON file."),
    limit: int = typer.Option(50, "--limit", min=1),
) -> int:
    """List registered parameters and their recorded source references."""
    state = _state(ctx)
    records = _load_records(state, registry)
    rows = []
    for record in records[:limit]:
        evidence = record.get("evidence") or {}
        source = evidence.get("source") or {}
        rows.append(
            (
                record.get("canonical_id", ""),
                record.get("value"),
                record.get("value_unit") or "",
                record.get("status") or "UNRESOLVED",
                source.get("document_id") or "unavailable",
                source.get("locator") or "unavailable",
            )
        )
    if not state.quiet and not state.json_mode:
        section(state.console, "EVIDENCE INDEX")
        table(
            state.console,
            ("PARAMETER", "VALUE", "UNIT", "STATUS", "DOCUMENT", "LOCATOR"),
            rows,
        )
        if len(records) > limit:
            notice(state.console, f"Showing {limit} of {len(records)}; use --limit to see more.")
    state.emit({"count": len(records), "records": records[:limit]})
    return 0


def evidence_inspect(
    ctx: typer.Context,
    parameter: str = typer.Argument(..., help="Canonical id (or unique substring)."),
    registry: Path | None = typer.Option(None, "--registry"),
    report_dir: Path | None = typer.Option(None, "--report-dir"),
) -> int:
    """Inspect one parameter's registry evidence and dossier status."""
    state = _state(ctx)
    records = _find_records(_load_records(state, registry), parameter)
    if not records:
        raise InputError("Parameter not found.", why=f"No registry record matches {parameter!r}.", action="Run `parallm evidence list`.")
    if len(records) > 1:
        raise InputError("Parameter name is ambiguous.", why=f"Matches: {[r.get('canonical_id') for r in records]}", action="Use an exact canonical id.")
    record = records[0]
    dossiers = _load_dossiers(state, report_dir, optional=True)
    dossier = next((d for d in dossiers if d.get("parameter") == record.get("canonical_id")), None)
    fit_path, fit = _find_calibration_fit(state, record.get("canonical_id", parameter))
    evidence = record.get("evidence") or {}
    source = evidence.get("source") or {}
    conditions = record.get("conditions") or {}
    if not state.quiet and not state.json_mode:
        section(state.console, "PARAMETER RECORD")
        kv(
            state.console,
            (
                ("Name", record.get("canonical_id")),
                ("Definition", record.get("definition")),
                ("Value", record.get("value")),
                ("Unit", record.get("value_unit")),
                ("Status", record.get("status")),
                ("Method", record.get("method") or "unavailable"),
            ),
        )
        section(state.console, "SOURCE")
        kv(
            state.console,
            (
                ("Document", source.get("document_id") or "unavailable"),
                ("DOI / URL", source.get("doi_or_url") or "unavailable"),
                ("Locator", source.get("locator") or "unavailable"),
                ("Page", source.get("page")),
                ("Quoted text", source.get("quote") or "unavailable"),
            ),
        )
        section(state.console, "CONDITIONS")
        kv(state.console, tuple((k, v) for k, v in conditions.items()) or (("Recorded", "unavailable"),))
        section(state.console, "VALIDATION")
        if dossier:
            d_evidence = dossier.get("evidence") or {}
            kv(
                state.console,
                (
                    ("Decision", dossier.get("decision")),
                    ("Evidence check", status_text("PASSED" if d_evidence.get("quote_verified") else "NOT CHECKED")),
                    ("Unit check", "not evaluated by this command"),
                    ("Condition match", status_text("NOT CHECKED")),
                    ("Traceability", dossier.get("traceability") or "unavailable"),
                ),
            )
        else:
            notice(state.console, "No dossier available; validation fields are unavailable.")
        section(state.console, "CALIBRATION")
        kv(state.console, (("Status", calibration_state(record, fit)),))
        if fit is None and record.get("status") == "CALIBRATED":
            notice(
                state.console,
                "Origin records a literature fit; no synthetic calibration report is attached.",
            )
        notice(state.console, "Unavailable fields are shown as unavailable, never inferred.")
    state.emit(
        {
            "record": record,
            "dossier": dossier,
            "calibration": {
                "status": calibration_state(record, fit),
                "path": str(fit_path) if fit_path else None,
                "report": fit,
            },
        }
    )
    return 0


def evidence_report(
    ctx: typer.Context,
    report_dir: Path | None = typer.Option(None, "--report-dir"),
) -> int:
    """Summarise an assembly report: decisions, conflicts and traceability."""
    from ...assembly.dossier import check_traceability

    state = _state(ctx)
    dossiers = _load_dossiers(state, report_dir, optional=False)
    trace = {"ok": 0, "warn": 0, "fail": 0}
    for dossier in dossiers:
        level, _ = check_traceability(dossier)
        trace[level] += 1
    decisions: dict[str, int] = {}
    for dossier in dossiers:
        decision = str(dossier.get("decision", "UNKNOWN"))
        decisions[decision] = decisions.get(decision, 0) + 1
    if not state.quiet and not state.json_mode:
        section(state.console, "EVIDENCE REPORT")
        kv(
            state.console,
            (
                ("Parameters", len(dossiers)),
                ("Decisions", decisions),
                ("Traceability", trace),
            ),
        )
        notice(state.console, "Dossiers describe evidence, not experimental validation.")
    state.emit({"parameters": len(dossiers), "decisions": decisions, "traceability": trace})
    return 1 if trace["fail"] else 0


def explain(
    ctx: typer.Context,
    parameter: str = typer.Argument(..., help="Canonical id whose provenance to explain."),
    registry: Path | None = typer.Option(None, "--registry"),
    report_dir: Path | None = typer.Option(None, "--report-dir"),
    calibration_report: Path | None = typer.Option(
        None, "--calibration-report", help="Synthetic fit report JSON, if available."
    ),
) -> int:
    """Produce a traceable provenance report for a single parameter."""
    from ...assembly.dossier import check_traceability

    state = _state(ctx)
    records = _find_records(_load_records(state, registry), parameter)
    if not records:
        raise InputError("Parameter not found.", why=f"No registry record matches {parameter!r}.", action="Run `parallm evidence list`.")
    if len(records) > 1:
        raise InputError("Parameter name is ambiguous.", why=f"Matches: {[r.get('canonical_id') for r in records]}", action="Use an exact canonical id.")
    record = records[0]
    dossiers = _load_dossiers(state, report_dir, optional=True)
    dossier = next((d for d in dossiers if d.get("parameter") == record.get("canonical_id")), None)
    fit_path, fit = _find_calibration_fit(state, record.get("canonical_id", parameter), calibration_report)

    evidence = record.get("evidence") or {}
    source = evidence.get("source") or {}
    identifiability = (dossier or {}).get("identifiability") or {}
    approval = (dossier or {}).get("approval") or {}
    trace_level = check_traceability(dossier)[0] if dossier else "NOT CHECKED"
    if not state.quiet and not state.json_mode:
        section(state.console, "PARAMETER PROVENANCE")
        kv(
            state.console,
            (
                ("Parameter", record.get("canonical_id")),
                ("Origin", record.get("status") or "UNRESOLVED"),
                ("Value", record.get("value")),
                ("Unit", record.get("value_unit")),
                ("Method", record.get("method") or "unavailable"),
                ("Source", source.get("document_id") or "unavailable"),
                ("Location", source.get("locator") or "unavailable"),
                ("Conditions", record.get("conditions") or "unavailable"),
                ("Validation", status_text(trace_level)),
                ("Decision", (dossier or {}).get("decision") or "unavailable"),
                ("Identifiability", status_text(identifiability.get("status") or "not_assessed")),
                ("Approval", status_text(approval.get("status") or "pending")),
                ("Calibration", calibration_state(record, fit)),
            ),
        )
        notice(state.console, "Unavailable fields are shown as unavailable, never inferred.")
        if fit is None and record.get("status") == "CALIBRATED":
            notice(
                state.console,
                "Origin records a literature fit; no synthetic calibration report is attached.",
            )
        if fit:
            entry = (fit.get("recovery") or {}).get(parameter, {})
            kv(
                state.console,
                (
                    ("Fit source", str(fit_path)),
                    ("Estimate", entry.get("estimate")),
                    ("Truth", entry.get("truth")),
                    ("Relative error", entry.get("rel_error_pct")),
                ),
            )
            notice(state.console, "SYNTHETIC recovery only — not experimental validation.", "warn")
    state.emit(
        {
            "record": record,
            "dossier": dossier,
            "traceability": trace_level,
            "calibration": {
                "status": calibration_state(record, fit),
                "path": str(fit_path) if fit_path else None,
                "report": fit,
            },
        }
    )
    return 0


evidence_app.command("list")(evidence_list)
evidence_app.command("inspect")(evidence_inspect)
evidence_app.command("report")(evidence_report)
