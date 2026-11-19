"""Deterministic RNG helpers that never leave global numpy state modified.

Some third-party APIs (``pybop.add_noise``, SALib's ``saltelli.sample``, PINTS
samplers) draw from numpy's legacy global RNG and expose no generator argument.
For those calls we seed the legacy RNG for the duration of the call and always
restore the caller's previous state. Code we own uses an explicitly passed
``numpy.random.Generator`` instead.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import numpy as np


@contextmanager
def isolated_numpy_seed(seed: int) -> Iterator[None]:
    """Seed the legacy global RNG inside a block, then restore the exact state."""
    previous = np.random.get_state()
    np.random.seed(int(seed))
    try:
        yield
    finally:
        np.random.set_state(previous)


def legacy_seed(rng: np.random.Generator) -> int:
    """Derive a legacy-RNG seed from an explicitly supplied generator."""
    return int(rng.integers(0, 2**31 - 1, dtype=np.uint32))
