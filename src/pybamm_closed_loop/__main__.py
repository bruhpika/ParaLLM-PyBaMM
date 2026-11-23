"""Allow ``python -m pybamm_closed_loop`` as an install-free entry point."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
