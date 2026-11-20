"""Evidence arms for the extraction benchmarks.

Two evidence sources are deliberately kept apart:

``oracle-located (probe window; NOT a performance upper bound)``
    The existing benchmark path builds a window around the fixture's
    hand-written probe. It is useful as a location oracle but it hands the
    model the answer location and only a small window, so it is *not* a
    retrieval result and *not* a performance upper bound.

``real retrieval (BM25)``
    A query is built from the item's parameter description only, and BM25 runs
    over the complete document store. The probe, the gold passage, the target
    document id and gold conditions are never used for retrieval.

The recall helpers in this module use the probe only *after* retrieval, to
label the gold segment for evaluation. That label is never part of a query.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from ..literature.index import BM25Index
from ..literature.ingest import DocumentStore, validate_document_id
from ..literature.retrieval import RAGContext, RetrievalFacets, RetrievedSegment
from ..registry.textnorm import ascii_fold

ORACLE_LABEL = "oracle-located (probe window; NOT a performance upper bound)"
REAL_RETRIEVAL_LABEL = "real retrieval (BM25)"
TUNED_RETRIEVAL_LABEL = "real retrieval (BM25, tuned b=0.5)"
DEFAULT_RETRIEVAL_K = 8
RECALL_KS: tuple[int, ...] = (1, 3, 5, 10)
# Selected on v4/small dev only (configs/retrieval/lexical_config.json).
TUNED_BM25_K1 = 1.5
TUNED_BM25_B = 0.5


def tuned_index(index: BM25Index) -> BM25Index:
    """BM25 index with the dev-selected parameters, same segments."""
    return BM25Index(index.segments, k1=TUNED_BM25_K1, b=TUNED_BM25_B)


def query_from_facets(item: Any) -> str:
    """v3 query: the declared retrieval facets only (no probe/document id)."""
    return RetrievalFacets(**item.facets).query_text()


def query_from_parameter(item: Any) -> str:
    """v4 query: parameter name and unit only.

    Deliberately excluded: ``probe``, ``gold_conditions``, ``notes``, the
    target ``document_id``, the printed value and the gold value. Including any
    of them would turn the real-retrieval arm back into an oracle.
    """
    parameter = item.parameter if isinstance(item.parameter, Mapping) else {}
    name = str(parameter.get("name") or "").strip()
    unit = str(parameter.get("unit") or "").strip()
    query = " ".join(part for part in (name, unit) if part)
    if not query:
        raise ValueError(f"item {getattr(item, 'item_id', '?')} has no queryable parameter name/unit")
    return query


def query_for_item(item: Any) -> str:
    """Return the query allowed for this fixture type (never the probe)."""
    if hasattr(item, "facets"):
        return query_from_facets(item)
    return query_from_parameter(item)


def facets_for_item(item: Any) -> dict[str, Any]:
    """Public query facets recorded alongside the retrieval audit."""
    if hasattr(item, "facets"):
        return dict(item.facets)
    parameter = item.parameter if isinstance(item.parameter, Mapping) else {}
    return {
        "parameter_names": [str(parameter.get("name") or "").strip()],
        "unit": str(parameter.get("unit") or "").strip(),
    }


def _probe_for(item: Any) -> str:
    probe = getattr(item, "passage_probe", None) or getattr(item, "probe", None)
    if not probe:
        raise ValueError(f"item {getattr(item, 'item_id', '?')} has no gold probe")
    return str(probe)


def gold_segment_ids(item: Any, store: DocumentStore) -> list[str]:
    """Segment ids containing the gold probe (evaluation label only).

    The probe locates the gold passage for recall scoring. It is never passed
    to :func:`query_for_item` or used to filter the BM25 search.
    """
    document_id = str(item.document_id)
    validate_document_id(document_id)
    raw = (store.raw_dir / f"{document_id}.txt").read_text()
    probe = _probe_for(item)
    idx = ascii_fold(raw).find(ascii_fold(probe))
    if idx < 0:
        raise ValueError(
            f"gold probe for {getattr(item, 'item_id', '?')} not found in {document_id}"
        )
    start, end = idx, idx + len(probe)
    segments = store.segments(document_id)
    overlapping = [
        seg.segment_id
        for seg in segments
        if seg.char_start < end and seg.char_end > start
    ]
    if overlapping:
        return overlapping
    if not segments:
        raise ValueError(f"document {document_id} has no segments")
    nearest = min(
        segments,
        key=lambda seg: min(abs(seg.char_start - idx), abs(seg.char_end - idx)),
    )
    return [nearest.segment_id]


def retrieve_context(
    store: DocumentStore,
    query: str,
    *,
    k: int = DEFAULT_RETRIEVAL_K,
    index: BM25Index | None = None,
    facets: Mapping[str, Any] | None = None,
) -> RAGContext:
    """Run BM25 over the complete store and return provenance-carrying hits."""
    if not query.strip():
        raise ValueError("retrieval query is empty")
    index = index or BM25Index(store.segments())
    hits = index.search(query, k=k)
    segments = [
        RetrievedSegment.from_segment(segment, float(score))
        for segment, score in hits
    ]
    return RAGContext(
        query=query,
        facets=dict(facets or {}),
        segments=segments,
        retrieved_from=sorted({segment.document_id for segment in segments}),
    )


def retrieval_context_for_item(
    item: Any,
    store: DocumentStore,
    *,
    k: int = DEFAULT_RETRIEVAL_K,
    index: BM25Index | None = None,
) -> RAGContext:
    """Real-retrieval context for one v3/v4 item (query-only, full store)."""
    return retrieve_context(
        store,
        query_for_item(item),
        k=k,
        index=index,
        facets=facets_for_item(item),
    )


def recall_at_k(hit_segment_ids: Sequence[str], gold_segment_ids_: Sequence[str], k: int) -> float:
    """Item-level recall: did any gold segment appear in the top ``k``?"""
    if k <= 0:
        raise ValueError("k must be positive")
    gold = set(gold_segment_ids_)
    return 1.0 if gold & set(hit_segment_ids[:k]) else 0.0


def evaluate_recall(
    items: Sequence[Any],
    store: DocumentStore,
    *,
    query_builder: Callable[[Any], str] = query_for_item,
    index: BM25Index | None = None,
    k_values: Sequence[int] = RECALL_KS,
    evidence_k: int = DEFAULT_RETRIEVAL_K,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Aggregate recall@k plus per-item audit rows (no passage text copied)."""
    index = index or BM25Index(store.segments())
    search_k = max(max(k_values), evidence_k)
    rows: list[dict[str, Any]] = []
    totals = {k: 0.0 for k in k_values}
    for item in items:
        query = query_builder(item)
        gold = gold_segment_ids(item, store)
        hits = index.search(query, k=search_k)
        hit_ids = [segment.segment_id for segment, _score in hits]
        values = {
            f"recall@{k}": recall_at_k(hit_ids, gold, k)
            for k in k_values
        }
        for k in k_values:
            totals[k] += values[f"recall@{k}"]
        rows.append(
            {
                "item_id": getattr(item, "item_id", "?"),
                "query": query,
                "gold_segment_ids": gold,
                "retrieved_segment_ids": hit_ids,
                "retrieved_documents": sorted({segment.document_id for segment, _ in hits}),
                "recall": values,
            }
        )
    n = len(rows)
    summary = {
        "n_items": n,
        "k_values": list(k_values),
        "evidence_k": evidence_k,
        "recall": {
            f"recall@{k}": (totals[k] / n if n else None)
            for k in k_values
        },
    }
    return summary, rows
