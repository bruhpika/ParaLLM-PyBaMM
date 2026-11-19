"""Unit tests: literature ingestion + retrieval (P3)."""

import pytest

from pybamm_closed_loop.literature.index import BM25Index, expand_query
from pybamm_closed_loop.literature.ingest import DocumentStore
from pybamm_closed_loop.literature.retrieval import RetrievalFacets, build_rag_context

TEXT_A = """Table II. Geometrical measurements for the LGM50.

The mean particle radius of the positive electrode is 5.22 um and the
negative electrode is 5.86 um as measured by SEM.

A second paragraph about electrolyte volume fraction of 33.5% in the
positive electrode.
"""

TEXT_B = """Discussion section.

The electrolyte diffusivity was taken from Nyman et al. as a fitted
expression. No scalar value is given here.
"""


def test_ingest_text_segments_have_offsets(tmp_path):
    store = DocumentStore(tmp_path)
    doc = store.ingest_text("docA", TEXT_A, title="Test A")
    segs = store.segments("docA")
    assert doc.n_segments == len(segs) >= 2
    for seg in segs:
        assert TEXT_A[seg.char_start : seg.char_end].strip() == seg.text.strip()
        assert seg.page is None  # text documents carry no page numbers
    assert segs[0].heading is not None  # Table II caption tracked


def test_headings_track_captions_and_titles_not_sentences(tmp_path):
    text = """Table 3: Cycling conditions.

The cells were cycled at 25 C between 2.5 and 4.2 V, a full sentence.

A Short Title

Another full sentence with a period."""
    store = DocumentStore(tmp_path)
    store.ingest_text("docA", text)
    segs = store.segments("docA")
    headings = [s.heading for s in segs]
    assert "Table 3: Cycling conditions." in headings
    assert "A Short Title" in headings
    assert (
        "The cells were cycled at 25 C between 2.5 and 4.2 V, a full sentence."
        not in headings
    )
    assert "Another full sentence with a period." not in headings


def test_ingest_is_immutable(tmp_path):
    store = DocumentStore(tmp_path)
    store.ingest_text("docA", TEXT_A)
    store.ingest_text("docA", TEXT_A)  # idempotent for identical content
    with pytest.raises(ValueError, match="immutable"):
        store.ingest_text("docA", TEXT_B)


def test_pdf_ingest_records_real_pages(tmp_path):
    pytest.importorskip("pypdf")
    pdf_path = tmp_path / "two_pages.pdf"
    _write_minimal_pdf(pdf_path, ["Hello page one", "Second page text"])
    store = DocumentStore(tmp_path)
    doc = store.ingest_pdf("docP", pdf_path, kind="pdf")
    assert doc.page_structure is True
    pages = {s.page for s in store.segments("docP")}
    assert pages == {1, 2}
    for seg in store.segments("docP"):
        assert seg.page in (1, 2)


def test_bm25_ranks_relevant_segment_first(tmp_path):
    store = DocumentStore(tmp_path)
    store.ingest_text("docA", TEXT_A)
    store.ingest_text("docB", TEXT_B)
    index = BM25Index(store.segments())
    hits = index.search("electrolyte diffusivity Nyman", k=3)
    assert hits
    assert hits[0][0].document_id == "docB"


def test_synonym_expansion():
    terms = expand_query("particle radius")
    assert "particle" in terms and "radius" in terms
    assert "size" in terms  # via particle_radius alias group


def test_query_expansion_is_deduplicated():
    terms = expand_query("particle radius particle")
    assert len(terms) == len(set(terms))
    assert terms.count("particle") == 1
    assert terms.count("radius") == 1


def test_inverted_index_matches_naive_bm25(tmp_path):
    import math
    from collections import Counter

    from pybamm_closed_loop.literature.index import tokenize

    store = DocumentStore(tmp_path)
    store.ingest_text("docA", TEXT_A)
    store.ingest_text("docB", TEXT_B)
    segments = store.segments()
    index = BM25Index(segments)
    query = "electrolyte diffusivity Nyman particle radius"
    terms = expand_query(query)
    n = len(segments)
    docs_tokens = [tokenize(s.text) for s in segments]
    doc_len = [len(t) for t in docs_tokens]
    avgdl = sum(doc_len) / n
    df = Counter(term for toks in docs_tokens for term in set(toks))
    expected = [0.0] * n
    for term in terms:
        if df[term] == 0:
            continue
        idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
        for i, toks in enumerate(docs_tokens):
            tf = toks.count(term)
            if tf == 0:
                continue
            denom = tf + 1.5 * (1 - 0.75 + 0.75 * doc_len[i] / avgdl)
            expected[i] += idf * (tf * (1.5 + 1)) / denom
    expected_order = [i for i in sorted(range(n), key=lambda i: expected[i], reverse=True) if expected[i] > 0]
    actual = index.search(query, k=n)
    assert [seg.segment_id for seg, _ in actual] == [segments[i].segment_id for i in expected_order]
    assert [score for _, score in actual] == pytest.approx([expected[i] for i in expected_order])


def test_rag_context_only_contains_retrieved_passages(tmp_path):
    store = DocumentStore(tmp_path)
    store.ingest_text("docA", TEXT_A)
    store.ingest_text("docB", TEXT_B)
    index = BM25Index(store.segments())
    facets = RetrievalFacets(parameter_names=["electrolyte diffusivity"], materials=["graphite"])
    ctx = build_rag_context(facets, index, k=2)
    block = ctx.to_prompt_block()
    assert "RULE: extract ONLY statements supported by the evidence" in block
    assert ctx.retrieved_from  # at least one source document
    for seg in ctx.segments:
        assert seg.text  # real passage text


def _write_minimal_pdf(path, page_texts):
    """Hand-built minimal PDF with Helvetica text on each page."""
    objects = []
    n_pages = len(page_texts)
    font_obj_num = 3 + 2 * n_pages
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>")
    for i, text in enumerate(page_texts):
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        content_obj = 4 + 2 * i
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_obj} 0 R /Resources << /Font << /F1 {font_obj_num} 0 R >> >> >>"
        )
        objects.append(f"<< /Length {len(content)} >>\nstream\n{content}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    path.write_bytes(out)
