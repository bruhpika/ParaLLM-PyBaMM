"""Core commands: diagnostics, first-run setup, status, projects and simulation."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

import typer
from rich.text import Text

from ... import __version__
from ..config import CLIConfig, PathSettings, save_config
from ..context import State
from ..errors import ConfigError, InputError, OverwriteError
from ..render import footer, kv, make_progress, notice, section, status_text, success, table

PINNED_PYBAMM = "26.8.0.0"
REQUIRED_MODULES: tuple[tuple[str, str], ...] = (
    ("PyBaMM", "pybamm"),
    ("NumPy", "numpy"),
    ("SciPy", "scipy"),
    ("pandas", "pandas"),
    ("pydantic", "pydantic"),
    ("PyYAML", "yaml"),
    ("matplotlib", "matplotlib"),
    ("Typer", "typer"),
    ("Rich", "rich"),
    ("Questionary", "questionary"),
)
OPTIONAL_MODULES: tuple[tuple[str, str], ...] = (
    ("PyBOP", "pybop"),
    ("pypdf", "pypdf"),
    ("SALib", "SALib"),
    ("PINTS", "pints"),
    ("PyProBE", "pyprobe"),
)
DIST_NAMES = {"yaml": "PyYAML"}


def _state(ctx: typer.Context) -> State:
    state = ctx.obj
    if not isinstance(state, State):
        raise ConfigError("CLI state was not initialised.", action="Report this as a CLI bug.")
    return state


def _dist_version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def _module_present(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


@dataclass
class Check:
    component: str
    status: str
    detail: str
    action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "status": self.status,
            "detail": self.detail,
            "action": self.action,
        }


def doctor(
    ctx: typer.Context,
    deep: bool = typer.Option(
        False, "--deep", help="Import PyBaMM to inspect installed parameter sets."
    ),
) -> int:
    """Check the environment, dependencies and workspace with actionable results."""
    state = _state(ctx)
    checks: list[Check] = []

    python_ok = sys.version_info >= (3, 10) and sys.version_info < (3, 16)
    checks.append(
        Check(
            "Python",
            "PASSED" if python_ok else "FAILED",
            platform.python_version() + " (supported: 3.10-3.15)",
            None if python_ok else "Use a supported Python version (3.10-3.15).",
        )
    )
    checks.append(Check("ParaLLM", "PASSED", _dist_version("parallm-pybamm") or __version__))

    pybamm_version = _dist_version("pybamm")
    if pybamm_version is None:
        checks.append(
            Check(
                "PyBaMM",
                "FAILED",
                "not installed",
                "Install the pinned release: pip install pybamm==" + PINNED_PYBAMM,
            )
        )
    elif pybamm_version != PINNED_PYBAMM:
        checks.append(
            Check(
                "PyBaMM",
                "FAILED",
                f"{pybamm_version} installed, {PINNED_PYBAMM} pinned",
                f"Install pybamm=={PINNED_PYBAMM}; names and options are version-specific.",
            )
        )
    else:
        checks.append(Check("PyBaMM", "PASSED", f"{pybamm_version} (pinned)"))

    for label, module in REQUIRED_MODULES[1:]:
        present = _module_present(module)
        version = _dist_version(DIST_NAMES.get(module, module)) if present else None
        checks.append(
            Check(
                label,
                "PASSED" if present else "FAILED",
                version or "not installed",
                None if present else f"Install the '{module}' package or reinstall parallm.",
            )
        )

    for label, module in OPTIONAL_MODULES:
        if _module_present(module):
            checks.append(Check(label, "PASSED", "installed (optional)"))
        else:
            checks.append(
                Check(
                    label,
                    "MISSING",
                    "not installed (optional)",
                    f"Install the 'ecosystem' extra to use {label}-dependent commands.",
                )
            )

    if state.config_error:
        checks.append(
            Check("Configuration", "FAILED", state.config_error, "Fix the TOML file or run init.")
        )
    elif state.config is None:
        checks.append(
            Check(
                "Configuration",
                "MISSING",
                str(state.config_path),
                "Run `parallm init` to create a workspace and configuration.",
            )
        )
    else:
        checks.append(Check("Configuration", "PASSED", str(state.config_path)))

    workspace: Path | None = None
    if state.config is not None and state.config.workspace is not None:
        workspace = state.workspace()
        if workspace.is_dir() and os.access(workspace, os.W_OK):
            checks.append(Check("Workspace", "PASSED", str(workspace)))
        else:
            checks.append(
                Check(
                    "Workspace",
                    "FAILED" if workspace.exists() else "MISSING",
                    str(workspace),
                    "Run `parallm init --workspace PATH` or check directory permissions.",
                )
            )
    else:
        checks.append(Check("Workspace", "NOT CHECKED", "no workspace configured"))

    registry = (state.config.resolve(state.config.paths.registry) if state.config else None)
    registry = registry or Path.cwd() / "data" / "registry" / "registry.json"
    if registry.is_file():
        try:
            records = json.loads(registry.read_text(encoding="utf-8"))
            count = len(records) if isinstance(records, list) else "invalid"
        except (OSError, ValueError):
            count = "unreadable"
        checks.append(Check("Registry", "PASSED" if count != "unreadable" else "FAILED", f"{registry} ({count} records)"))
    else:
        checks.append(Check("Registry", "MISSING", str(registry), "Run the registry seed script or point config paths at one."))

    documents = (state.config.resolve(state.config.paths.documents) if state.config else None)
    documents = documents or Path.cwd() / "data" / "raw_documents"
    if documents.is_dir():
        n_docs = sum(1 for child in documents.iterdir() if child.is_dir())
        checks.append(Check("Documents", "PASSED", f"{documents} ({n_docs} entries)"))
    else:
        checks.append(Check("Documents", "MISSING", str(documents), "Place source texts under this directory or update config."))

    if deep:
        from ...pybamm_engine import installed_parameter_sets

        try:
            names = installed_parameter_sets()
            has_chen = "Chen2020" in names
            checks.append(
                Check(
                    "Parameter sets",
                    "PASSED" if has_chen else "FAILED",
                    f"{len(names)} installed; Chen2020 {'present' if has_chen else 'missing'}",
                    None if has_chen else "The pinned Chen2020 parameter set is required for this workflow.",
                )
            )
        except Exception as exc:
            checks.append(Check("Parameter sets", "FAILED", f"import failed: {exc}", "Check the PyBaMM installation."))
    else:
        checks.append(
            Check("Parameter sets", "NOT CHECKED", "run `parallm doctor --deep` to inspect")
        )

    failed = [c for c in checks if c.status == "FAILED"]
    warnings = [c for c in checks if c.status in ("WARNING", "MISSING")]
    if not state.quiet and not state.json_mode:
        table(
            state.console,
            ("COMPONENT", "STATUS", "DETAIL"),
            [(c.component, status_text(c.status), c.detail) for c in checks],
            status_columns=(1,),
        )
        state.console.print()
        for check in checks:
            if check.action and check.status == "FAILED":
                notice(state.console, f"{check.component}: {check.action}", "error")
        state.console.print(
            Text(
                f"{len(checks) - len(failed) - len(warnings)} passed, "
                f"{len(warnings)} warning(s), {len(failed)} failed",
                style="app.accent",
            )
        )
        if state.config is None:
            footer(state.console, "parallm init")
    state.emit(
        {
            "checks": [c.to_dict() for c in checks],
            "summary": {
                "passed": len(checks) - len(failed) - len(warnings),
                "warnings": len(warnings),
                "failed": len(failed),
            },
        },
        status="failed" if failed else "completed",
    )
    return 1 if failed else 0


def _select_setup_mode() -> str:
    choices = [
        ("Detect an existing PyBaMM installation", "detect"),
        ("Configure an existing environment", "existing"),
        ("Get instructions for a new environment", "new"),
        ("Configure later", "later"),
    ]
    if sys.stdin.isatty():
        try:
            import questionary

            answer = questionary.select(
                "Select an option:",
                choices=[questionary.Choice(title=t, value=v) for t, v in choices],
            ).ask()
            if answer in {value for _, value in choices}:
                return str(answer)
        except (ImportError, KeyboardInterrupt, EOFError):
            pass
    if not state_is_non_interactive():
        for index, (title, _) in enumerate(choices, start=1):
            print(f"[{index}] {title}")
        try:
            raw = input("Select an option [1]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "detect"
        index = int(raw) if raw.isdigit() else 1
        if 1 <= index <= len(choices):
            return choices[index - 1][1]
    return "detect"


def state_is_non_interactive() -> bool:
    return not sys.stdin.isatty()


def init(
    ctx: typer.Context,
    workspace: Path = typer.Option(
        Path("battery-research"),
        "--workspace",
        "-w",
        help="Workspace directory to create or reuse.",
    ),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Never prompt; use safe defaults."
    ),
    force: bool = typer.Option(
        False, "--force", help="Replace an existing configuration file."
    ),
) -> int:
    """Create a research workspace and configuration without installing packages."""
    state = _state(ctx)
    target = workspace.expanduser().resolve()
    config_file = state.config_path
    if config_file.exists() and not force:
        if non_interactive or not sys.stdin.isatty():
            raise ConfigError(
                "Configuration file already exists.",
                why=f"Found: {config_file}",
                action="Use --force to replace it, or --config to choose another path.",
                code="E105",
            )
        try:
            import questionary

            replace = questionary.confirm(
                f"Replace {config_file}?", default=False
            ).ask()
        except (ImportError, KeyboardInterrupt, EOFError):
            replace = input(f"Replace {config_file}? [y/N]: ").strip().lower() == "y"
        if not replace:
            raise ConfigError(
                "Existing configuration was left unchanged.",
                action="Use --force to replace it explicitly.",
                code="E105",
            )

    mode = "detect" if non_interactive or not sys.stdin.isatty() else _select_setup_mode()
    if mode == "new" and not state.json_mode:
        notice(
            state.console,
            "No packages will be installed. Create an environment yourself, e.g. "
            "`python -m venv .venv` then `pip install '.[ecosystem]'`.",
        )

    for subdir in ("data/registry", "data/raw_documents", "results", "reports", "configs", "projects"):
        (target / subdir).mkdir(parents=True, exist_ok=True)

    config = CLIConfig(
        workspace=target,
        paths=PathSettings(
            registry=Path("data/registry/registry.json"),
            documents=Path("data/raw_documents"),
            p2_results=Path("results/p2"),
        ),
    )
    save_config(config, config_file)
    pybamm_version = _dist_version("pybamm") if mode in ("detect", "existing") else None

    if not state.quiet and not state.json_mode:
        section(state.console, "WORKSPACE INITIALIZED")
        kv(
            state.console,
            (
                ("Location", str(target)),
                ("Configuration", "Created" if config_file.is_file() else "Not created"),
                ("Python", "Detected " + platform.python_version()),
                ("PyBaMM", "Detected " + pybamm_version if pybamm_version else "Not checked"),
            ),
        )
        section(state.console, "NEXT STEP")
        state.console.print(Text("parallm doctor", style="app.accent"))
        notice(state.console, "No packages were installed or modified.")
    state.emit(
        {
            "workspace": str(target),
            "configuration": str(config_file),
            "python": platform.python_version(),
            "pybamm": pybamm_version,
            "setup_mode": mode,
        }
    )
    return 0


def status(ctx: typer.Context) -> int:
    """Show the active workspace and the state of its configured inputs."""
    state = _state(ctx)
    config = state.require_config()
    workspace = state.workspace()
    rows: list[tuple[str, Any]] = [("Config", str(state.config_path)), ("Workspace", str(workspace))]
    n_records: int | None = None
    for label, configured in (
        ("Registry", config.paths.registry),
        ("Documents", config.paths.documents),
        ("P2 results", config.paths.p2_results),
        ("Target", config.paths.target),
        ("Gate", config.paths.gate),
    ):
        path = config.resolve(configured)
        if path is None:
            rows.append((label, Text("not configured", style="app.muted")))
            continue
        marker = status_text("PASSED" if path.exists() else "MISSING")
        rows.append((label, Text(f"{path} ") + marker))
        if label == "Registry" and path is not None and path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                n_records = len(data) if isinstance(data, list) else None
            except (OSError, ValueError):
                n_records = None
    if n_records is not None:
        rows.append(("Parameters", n_records))
    if not state.quiet and not state.json_mode:
        section(state.console, "RESEARCH WORKSPACE")
        kv(state.console, rows, label_width=14)
        notice(state.console, "Export contains only human-approved parameters.")
    state.emit({"workspace": str(workspace), "config": str(state.config_path), "parameters": n_records})
    return 0


def simulate(
    ctx: typer.Context,
    config: Path = typer.Option(..., "--config", help="Baseline run YAML configuration."),
    out: Path = typer.Option(..., "--out", help="Output directory for arrays and manifests."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Allow writing into a non-empty directory."),
) -> int:
    """Run a pinned PyBaMM baseline simulation through the project engine."""
    state = _state(ctx)
    config_file = config.expanduser().resolve()
    if not config_file.is_file():
        raise InputError(
            "Simulation configuration not found.",
            why=f"Expected: {config_file}",
            action="Pass an existing YAML file with --config.",
        )
    out_dir = out.expanduser().resolve()
    if out_dir.exists() and any(out_dir.iterdir()) and not overwrite:
        raise OverwriteError(
            "Output directory is not empty.",
            why=f"Refusing to write into {out_dir}",
            action="Choose a new --out path or pass --overwrite explicitly.",
        )

    from ...pybamm_engine import BaselineRunConfig, run, save_result

    run_config = BaselineRunConfig.from_yaml(config_file)
    progress = make_progress(state.console, "Solving PyBaMM model", enabled=not state.quiet)
    with progress:
        task = progress.add_task("Solving PyBaMM model", total=1)
        result = run(run_config)
        progress.update(task, completed=1)
    written = save_result(result, out_dir)
    if not state.quiet and not state.json_mode:
        section(state.console, "SIMULATION COMPLETED")
        kv(
            state.console,
            (
                ("Run", run_config.run_id),
                ("Model", run_config.pybamm.model.name),
                ("Parameter set", run_config.pybamm.parameter_set),
                ("Solver", run_config.pybamm.solver.name),
                ("Output", str(out_dir)),
                ("Files", len(written)),
            ),
        )
    state.emit({"run_id": run_config.run_id, "output": str(out_dir), "files": sorted(written)})
    return 0


project_app = typer.Typer(
    name="project",
    help="Create and inspect lightweight research projects inside the workspace.",
    add_completion=False,
    no_args_is_help=True,
)


def _project_root(ctx: typer.Context) -> Path:
    state = _state(ctx)
    return state.workspace() / "projects"


def _project_dir(ctx: typer.Context, name: str) -> Path:
    root = _project_root(ctx)
    return root / name


def create_project(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Project directory name."),
) -> int:
    """Create a new project directory with standard subdirectories."""
    state = _state(ctx)
    target = _project_dir(ctx, name)
    if target.exists():
        raise InputError(
            "Project already exists.",
            why=f"Found: {target}",
            action="Choose a different name or inspect the existing project.",
        )
    for subdir in ("data", "results", "reports", "configs"):
        (target / subdir).mkdir(parents=True, exist_ok=False)
    created = datetime.now(timezone.utc).isoformat()
    (target / "project.toml").write_text(
        f'name = {json.dumps(name)}\ncreated = {json.dumps(created)}\n', encoding="utf-8"
    )
    if not state.quiet and not state.json_mode:
        success(state.console, f"Created project {name} at {target}")
    state.emit({"name": name, "path": str(target)})
    return 0


def list_projects(ctx: typer.Context) -> int:
    """List projects in the active workspace."""
    state = _state(ctx)
    root = _project_root(ctx)
    names = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    if not state.quiet and not state.json_mode:
        section(state.console, "PROJECTS")
        if names:
            for name in names:
                state.console.print(Text(name, style="app.accent"))
        else:
            notice(state.console, "No projects yet. Run `parallm project create NAME`.")
    state.emit({"projects": names, "root": str(root)})
    return 0


def inspect_project(ctx: typer.Context, name: str = typer.Argument(...)) -> int:
    """Inspect one project's paths and file counts."""
    state = _state(ctx)
    target = _project_dir(ctx, name)
    if not target.is_dir():
        raise InputError(
            "Project not found.",
            why=f"Expected: {target}",
            action="Run `parallm project list` to see available projects.",
        )
    counts = {sub: len(list((target / sub).rglob("*"))) for sub in ("data", "results", "reports", "configs")}
    if not state.quiet and not state.json_mode:
        section(state.console, f"PROJECT {name}")
        kv(state.console, [("Path", str(target)), ("Files", sum(counts.values()))])
    state.emit({"name": name, "path": str(target), "files": counts})
    return 0


project_app.command("create")(create_project)
project_app.command("list")(list_projects)
project_app.command("inspect")(inspect_project)
