"""Retrieval index for literature passages (P3, Part C).

A small, deterministic BM25 implementation over ingested segments, with a
documented synonym table for parameter names, materials, chemistries, cell
formats, experimental conditions and measurement techniques. This is a
research-specific retrieval layer, not a reimplementation of PyBaMM/PyBOP/
PyProBE functionality.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

from .ingest import DocumentStore, Segment
from ..registry.textnorm import ascii_fold

# Retrieval-only synonym/alias groups. Aliases are used to expand queries;
# they never change how a value is interpreted (extraction/validation keep
# definitions strict).
SYNONYMS: dict[str, tuple[str, ...]] = {
    "volume_fraction": (
        "active material volume fraction", "active-material volume fraction",
        "volume fraction", "electrode volume fraction",
    ),
    "porosity": ("porosity", "electrolyte volume fraction", "pore volume fraction"),
    "diffusivity": (
        "diffusivity", "diffusion coefficient", "solid phase lithium diffusivity",
        "particle diffusivity", "apparent diffusion", "Ds",
    ),
    "electrolyte_diffusivity": (
        "electrolyte diffusivity", "electrolyte ionic diffusivity",
        "ionic diffusivity",
    ),
    "conductivity": ("conductivity", "electronic conductivity", "ionic conductivity"),
    "exchange_current": (
        "exchange current", "exchange current density", "exchange-current density",
        "j0", "reaction rate", "charge transfer resistance", "Rct",
    ),
    "bruggeman": ("bruggeman", "bruggeman exponent", "tortuosity exponent"),
    "transference": ("transference number", "t+", "cation transference"),
    "stoichiometry": ("stoichiometry", "stoichiometries", "sto"),
    "particle_radius": ("particle radius", "particle radii", "particle size", "mean particle radius", "average particle"),
    "thickness": ("thickness", "electrode thickness", "coating thickness"),
    "ocp": ("open circuit potential", "open-circuit potential", "ocv", "ocp", "emf"),
    "capacity": ("capacity", "rated capacity", "nominal capacity"),
    "nmc811": ("nmc811", "nmc 811", "nmc", "nickel rich", "LiNi0.8Mn0.08Co0.08Al0.04O2"),
    "graphite_siox": ("graphite", "graphite-siox", "c6", "siox", "bi-component"),
    "lgm50": ("lg m50", "lgm50", "m50", "21700", "cylindrical cell"),
    "chemistry": ("chemistry", "electrode material", "active material"),
    "cell_format": ("cell format", "cylindrical", "21700", "pouch", "prismatic"),
    "temperature": ("temperature", "isothermal", "room temperature", "25 c", "298"),
    "c_rate": ("c-rate", "c/2", "1c", "1.5c", "2c", "0.5c", "current rate"),
    "voltage_window": ("voltage window", "cut-off", "cutoff", "2.5 v", "4.2 v"),
    "gitt": ("gitt", "galvanostatic intermittent titration", "titration"),
    "eis": ("eis", "peis", "impedance spectroscopy", "electrochemical impedance"),
    "four_point": ("four-point probe", "4-point probe", "conductivity measurement"),
    "sem": ("sem", "fib-sem", "microscopy", "imagej", "eds"),
    "icp": ("icp", "icp-oes", "elemental analysis"),
    "teardown": ("teardown", "tear-down", "disassembly", "post-mortem"),
    "uncertainty": ("uncertainty", "error", "standard deviation", "variation"),
    "sei": ("sei", "solid electrolyte interphase", "degradation"),
    "electrolyte": ("electrolyte", "lipf6", "ec:emc", "ec:emc (3:7)"),
    "experiment": ("experiment", "measurement", "characterisation", "characterization"),
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def expand_query(query: str) -> list[str]:
    """Expand a query with alias groups that share any token with it.

    When a group is triggered, all of its aliases are added (full-group
    expansion), so e.g. 'particle radius' also retrieves 'particle size'.
    Duplicate terms are removed while preserving first-occurrence order so a
    synonym listed twice cannot silently double-weight a query term.
    """
    q_tokens = set(tokenize(query))
    terms = tokenize(query)
    folded = ascii_fold(query.lower())

    def alias_matches(alias: str) -> bool:
        a_tokens = tokenize(alias)
        if alias in folded:
            return True
        if len(a_tokens) == 1:
            return a_tokens[0] in q_tokens
        # A multi-word alias needs all of its tokens. Triggering on any one
        # shared token made "electrolyte diffusivity" expand to porosity merely
        # because both phrases contain "electrolyte".
        return bool(a_tokens) and set(a_tokens) <= q_tokens

    for _key, aliases in SYNONYMS.items():
        if any(alias_matches(alias) for alias in aliases):
            for alias in aliases:
                terms.extend(tokenize(alias))
    return list(dict.fromkeys(terms))


class BM25Index:
    """Deterministic BM25 over a list of segments (k1=1.5, b=0.75).

    An inverted index (term -> [(segment index, term frequency)]) keeps the
    scoring formula unchanged while only visiting documents that contain each
    query term.
    """

    def __init__(self, segments: list[Segment], k1: float = 1.5, b: float = 0.75):
        self.segments = segments
        self.k1 = k1
        self.b = b
        self._docs_tokens: list[list[str]] = [tokenize(s.text) for s in segments]
        self._doc_len: list[int] = [len(t) for t in self._docs_tokens]
        self._avgdl = (sum(self._doc_len) / len(self._doc_len)) if segments else 0.0
        self._postings: dict[str, list[tuple[int, int]]] = {}
        for i, toks in enumerate(self._docs_tokens):
            for term, tf in Counter(toks).items():
                self._postings.setdefault(term, []).append((i, tf))
        self._df: Counter[str] = Counter(
            {term: len(postings) for term, postings in self._postings.items()}
        )

    def score_terms(self, terms: Sequence[str]) -> list[float]:
        """Raw BM25 scores for already-tokenised terms (one per segment)."""
        if not self.segments:
            return []
        n = len(self.segments)
        scores: list[float] = [0.0] * n
        for term in terms:
            postings = self._postings.get(term)
            if not postings:
                continue
            df = self._df[term]
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for i, tf in postings:
                denom = tf + self.k1 * (
                    1 - self.b + self.b * self._doc_len[i] / (self._avgdl or 1)
                )
                scores[i] += idf * (tf * (self.k1 + 1)) / denom
        return scores

    def search(self, query: str, k: int = 8) -> list[tuple[Segment, float]]:
        terms = expand_query(query)
        if not terms or not self.segments:
            return []
        scores = self.score_terms(terms)
        ranked = sorted(range(len(self.segments)), key=lambda i: scores[i], reverse=True)
        return [(self.segments[i], scores[i]) for i in ranked[:k] if scores[i] > 0]


def build_index(store: DocumentStore) -> BM25Index:
    return BM25Index(store.segments())
