"""Availability checks for locally acquired, non-redistributed source texts.

Some fixtures cite documents that cannot be redistributed in this repository
(Chen2020 article and supplementary information, ECS © / CC BY-NC-ND). Those
items must degrade to an explicit skip when the locally acquired text is
absent, while remaining fully checked when it is present.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]

SUPPLEMENT_DOCUMENT_ID = "chen2020_supplement_s1"
SUPPLEMENT_RAW_FILENAME = f"{SUPPLEMENT_DOCUMENT_ID}.txt"
SUPPLEMENT_MISSING_REASON = (
    "Chen2020 supplement text not present locally: acquire the PDF from "
    "doi:10.1149/1945-7111/ab9050 and ingest it into data/literature_store"
)

ARTICLE_DOCUMENT_ID = "chen2020_jes_167_080534"
ARTICLE_RAW_FILENAME = f"{ARTICLE_DOCUMENT_ID}.txt"
ARTICLE_SOURCE_PATH = (
    REPO_ROOT
    / "data/raw_documents/chen2020_jes_167_080534"
    / f"{ARTICLE_DOCUMENT_ID}_fulltext.txt"
)
ARTICLE_MISSING_REASON = (
    "Chen2020 article text not present locally: run "
    "scripts/fetch_chen2020.py --pdf <owner-supplied publisher PDF>"
)


def supplement_text_path(store_root: str | Path) -> Path:
    return Path(store_root) / "raw" / SUPPLEMENT_RAW_FILENAME


def supplement_text_available(store_root: str | Path) -> bool:
    return supplement_text_path(store_root).is_file()


def article_text_path(store_root: str | Path) -> Path:
    return Path(store_root) / "raw" / ARTICLE_RAW_FILENAME


def article_text_available(store_root: str | Path) -> bool:
    """True when the article raw text exists in the local literature store."""
    return article_text_path(store_root).is_file()


def article_source_text_available() -> bool:
    """True when the standalone archived article extract exists locally."""
    return ARTICLE_SOURCE_PATH.is_file()


def _without_items(
    items: Iterable[Any],
    store_root: str | Path,
    document_id: str,
    available: Callable[[str | Path], bool],
    reason: str,
    label: str,
    *,
    log: Callable[[str], None] | None = print,
    document_id_of: Callable[[Any], str] | None = None,
) -> list[Any]:
    items = list(items)
    if available(store_root):
        return items
    get_id = document_id_of or (lambda it: getattr(it, "document_id", None))
    skipped = [str(get_id(it)) for it in items if get_id(it) == document_id]
    if skipped and log is not None:
        log(f"SKIP {len(skipped)} {label} item(s) {skipped}: {reason}")
    return [it for it in items if get_id(it) != document_id]


def without_supplement_items(
    items: Iterable[Any],
    store_root: str | Path,
    *,
    log: Callable[[str], None] | None = print,
    document_id_of: Callable[[Any], str] | None = None,
) -> list[Any]:
    """Return all items when the supplement is present; otherwise drop its items.

    ``document_id_of`` supports both dataclass benchmark items (``.document_id``)
    and raw fixture dicts (``["document_id"]``). Every skipped id is reported.
    """
    return _without_items(
        items,
        store_root,
        SUPPLEMENT_DOCUMENT_ID,
        supplement_text_available,
        SUPPLEMENT_MISSING_REASON,
        "supplement",
        log=log,
        document_id_of=document_id_of,
    )


def without_article_items(
    items: Iterable[Any],
    store_root: str | Path,
    *,
    log: Callable[[str], None] | None = print,
    document_id_of: Callable[[Any], str] | None = None,
) -> list[Any]:
    """Drop Chen2020-article items when its local text is absent."""
    return _without_items(
        items,
        store_root,
        ARTICLE_DOCUMENT_ID,
        article_text_available,
        ARTICLE_MISSING_REASON,
        "Chen2020 article",
        log=log,
        document_id_of=document_id_of,
    )
