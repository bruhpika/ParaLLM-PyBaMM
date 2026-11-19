"""Availability checks for locally acquired, non-redistributed source texts.

Some fixtures cite documents that cannot be redistributed in this repository
(Chen2020 supplementary information, ECS ©, permission unverified). Those items
must degrade to an explicit skip when the locally acquired text is absent,
while remaining fully checked when it is present.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

SUPPLEMENT_DOCUMENT_ID = "chen2020_supplement_s1"
SUPPLEMENT_RAW_FILENAME = f"{SUPPLEMENT_DOCUMENT_ID}.txt"
SUPPLEMENT_MISSING_REASON = (
    "Chen2020 supplement text not present locally: acquire the PDF from "
    "doi:10.1149/1945-7111/ab9050 and ingest it into data/literature_store"
)


def supplement_text_path(store_root: str | Path) -> Path:
    return Path(store_root) / "raw" / SUPPLEMENT_RAW_FILENAME


def supplement_text_available(store_root: str | Path) -> bool:
    return supplement_text_path(store_root).is_file()


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
    items = list(items)
    if supplement_text_available(store_root):
        return items
    get_id = document_id_of or (lambda it: getattr(it, "document_id", None))
    skipped = [str(get_id(it)) for it in items if get_id(it) == SUPPLEMENT_DOCUMENT_ID]
    if skipped and log is not None:
        log(
            f"SKIP {len(skipped)} supplement item(s) {skipped}: "
            f"{SUPPLEMENT_MISSING_REASON}"
        )
    return [it for it in items if get_id(it) != SUPPLEMENT_DOCUMENT_ID]
