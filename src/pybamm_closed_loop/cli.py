"""parallm command-line interface (V2.2).

``parallm assemble`` turns the parameter registry into per-parameter dossiers
for a target cell: a JSON + Markdown report, a PyBaMM-style export of
*human-approved* parameters only, and a reproducibility manifest.

Design commitments kept by this CLI:
- the LLM never enters the numeric decision path (decision D7);
- the human approval gate is mandatory (decision D6): without a gate file the
  PyBaMM export is empty by design;
- every dossier field traces to a *verified* quote or carries an explicit
  status flag (deterministic ``check_traceability``; a fail exits non-zero);
- inputs are never modified; every run is reproducible from the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from .assembly import ApprovalGate, Rubric, TargetSpecification, assemble
from .assembly.dossier import check_traceability
from .assembly.observability import (
    BOOTSTRAP_REL_STD_OBSERVABILITY,
    SENSITIVITY_OBSERVABILITY_THRESHOLD,
    load_observability,
)
from .assembly.report import verify_record_quotes


def load_target(path: Path) -> TargetSpecification:
    """Load a target specification from YAML (``target:`` mapping)."""
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    t = raw.get("target") if isinstance(raw, dict) and "target" in raw else raw
    if not isinstance(t, dict):
        raise SystemExit(f"target spec {path} has no 'target' mapping")
    try:
        return TargetSpecification(
            target_id=t["target_id"],
            cell_product=t["cell_product"],
            chemistry_families=tuple(t.get("chemistry_families") or ()),
            format=t.get("format"),
            temperature_k=t.get("temperature_k"),
            temperature_range_k=(
                tuple(t["temperature_range_k"]) if t.get("temperature_range_k") else None
            ),
            soc=t.get("soc"),
            electrolyte=t.get("electrolyte"),
            model=t.get("model") or "DFN",
            parameter_set=t.get("parameter_set") or "Chen2020",
            notes=t.get("notes") or "",
        )
    except KeyError as exc:
        raise SystemExit(f"target spec {path} missing required key {exc}") from exc


def load_doc_texts(documents: Path) -> dict[str, str]:
    """Map document id -> full text from a raw-document store directory.

    Each ``<documents>/<doc_id>/`` directory is expected to hold a
    ``*_fulltext.txt`` file; the first one found is used.
    """
    if not documents.is_dir():
        raise SystemExit(f"documents directory not found: {documents}")
    out: dict[str, str] = {}
    for sub in sorted(documents.iterdir()):
        if not sub.is_dir():
            continue
        fulltexts = sorted(sub.glob("*_fulltext.txt"))
        if fulltexts:
            out[sub.name] = fulltexts[0].read_text(encoding="utf-8", errors="replace")
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tool_version() -> str:
    try:
        from importlib.metadata import version

        return version("parallm-pybamm")
    except Exception:
        return "unknown"


def _cmd_assemble(args: argparse.Namespace) -> int:
    target_path = Path(args.target)
    registry_path = Path(args.registry)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    target = load_target(target_path)
    records = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise SystemExit(f"registry {registry_path} must be a JSON list of records")

    doc_texts: dict[str, str] = {}
    quote_stats: dict[str, int] = {}
    if args.documents:
        doc_texts = load_doc_texts(Path(args.documents))
        records, quote_stats = verify_record_quotes(records, doc_texts)

    rubric = Rubric(args.rubric_version)
    observability = load_observability(
        Path(args.p2_results), records, set(args.accuracy_critical or ())
    )
    report = assemble(records, target, rubric, observability=observability)

    trace: list[dict] = []
    counts = {"ok": 0, "warn": 0, "fail": 0}
    for d in report.dossiers:
        level, messages = check_traceability(d)
        counts[level] += 1
        trace.append(
            {"parameter": d.get("parameter"), "level": level, "messages": messages}
        )

    gate_path = Path(args.gate) if args.gate else None
    gate = ApprovalGate()
    if gate_path is not None:
        gate = ApprovalGate.from_dict(
            json.loads(gate_path.read_text(encoding="utf-8"))
        )

    payload = report.to_dict()
    payload["traceability"] = trace
    (out_dir / "report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "report.md").write_text(report.to_markdown(), encoding="utf-8")
    exported = report.pybamm_export(gate)
    (out_dir / "pybamm_export.json").write_text(
        json.dumps(exported, indent=2, sort_keys=True), encoding="utf-8"
    )

    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "command": "parallm assemble",
        "tool": {"parallm_pybamm": _tool_version(), "python": platform.python_version()},
        "rubric_version": rubric.version,
        "target": target.to_dict(),
        "target_config": {"path": str(target_path), "sha256": _sha256(target_path)},
        "registry": {
            "path": str(registry_path),
            "sha256": _sha256(registry_path),
            "n_records": len(records),
        },
        "documents": {
            "path": str(args.documents) if args.documents else None,
            "n_documents": len(doc_texts),
            "quote_verification": quote_stats,
        },
        "gate": {
            "path": str(gate_path) if gate_path else None,
            "sha256": _sha256(gate_path) if gate_path else None,
            "n_approved": len(gate.approved_parameters()),
        },
        "observability": {
            "p2_results": str(args.p2_results),
            "assessed_parameters": sorted(observability),
            "accuracy_critical": sorted(args.accuracy_critical or ()),
            "thresholds": {
                "sensitivity_observability": SENSITIVITY_OBSERVABILITY_THRESHOLD,
                "bootstrap_rel_std_observability": BOOTSTRAP_REL_STD_OBSERVABILITY,
            },
            "action_matrix": report.action_matrix(),
        },
        "traceability": counts,
        "n_exported": len(exported),
        "outputs": ["report.json", "report.md", "pybamm_export.json", "manifest.json"],
        "note": (
            "Every dossier field traces to a verified quote or carries an "
            "explicit status flag (see report.json 'traceability'). The PyBaMM "
            "export contains only human-approved parameters (decision D6); "
            "with no gate file it is empty by design."
        ),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    summary = report.summary()
    print(
        f"target: {target.target_id} | rubric: {rubric.version} | "
        f"parameters: {summary['n_parameters']}"
    )
    print(
        f"decisions: {summary['decisions']} | conflicts: {summary['n_conflicts']} "
        f"(same-source {summary['same_source_conflicts']}, "
        f"cross-source {summary['cross_source_conflicts']})"
    )
    print(f"traceability: ok={counts['ok']} warn={counts['warn']} fail={counts['fail']}")
    print(f"action matrix: {report.action_matrix()}")
    print(
        f"approved export: {len(exported)} parameter(s) "
        f"(gate: {str(gate_path) if gate_path else 'none provided'})"
    )
    for t in trace:
        for m in t["messages"]:
            print(f"  [{t['level']}] {m}")
    print(
        f"wrote {out_dir}/report.json, report.md, pybamm_export.json, manifest.json"
    )
    return 1 if counts["fail"] else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="parallm", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    a = sub.add_parser(
        "assemble", help="assemble parameter dossiers for a target cell"
    )
    a.add_argument("--target", required=True, help="target specification YAML")
    a.add_argument("--registry", required=True, help="registry records JSON")
    a.add_argument("--out", required=True, help="output directory")
    a.add_argument(
        "--documents",
        default=None,
        help="raw document store for deterministic quote verification",
    )
    a.add_argument(
        "--gate",
        default=None,
        help="approval gate JSON (only approved parameters are exported)",
    )
    a.add_argument(
        "--p2-results",
        default="results/p2",
        help="recorded P2 identifiability artifacts for the observability join (V2.3)",
    )
    a.add_argument(
        "--accuracy-critical",
        nargs="*",
        default=[],
        metavar="CANONICAL_ID",
        help="parameters whose accuracy is critical: unobservable ones become "
        "MEASURE instead of FIX in the action matrix",
    )
    a.add_argument("--rubric-version", default="rubric-v2")
    args = ap.parse_args(argv)
    if args.command == "assemble":
        return _cmd_assemble(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
