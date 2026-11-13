"""Reads web pages with the SpecStream Extract API and writes their text into a Pinecone index, one vector per
chunk of a page.

A vector id is `page:<digest of the URL>#<chunk number>`, apart from the ids of lists (`<list id>#...`) and
public records (`records:...`, `feed:...`) in the same index. After a page's new chunks are written, its other
ids (found by that prefix) are deleted, so reading a page again replaces it instead of doubling it. A page that
gives no text (blocked, not found, empty, failed) writes nothing, is not charged, and is reported back.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from specstream_pinecone.api import EXTRACT_MAX_PAGES, SpecStreamAPI
from specstream_pinecone.load import BATCH, DEFAULT_NAMESPACE, DELETE_BATCH, Embed, _ids

DEFAULT_CHUNK_CHARS = 2000
DEFAULT_OVERLAP_CHARS = 200


def page_prefix(url: str) -> str:
    return f"page:{hashlib.sha256(url.encode('utf-8')).hexdigest()[:32]}#"


def chunk_id(url: str, chunk: int) -> str:
    return f"{page_prefix(url)}{chunk}"


def split_text(text: str, size: int = DEFAULT_CHUNK_CHARS, overlap: int = DEFAULT_OVERLAP_CHARS) -> list[str]:
    """Chunks of at most `size` characters, cut between paragraphs where it can. A paragraph longer than
    `size` is cut into windows that share `overlap` characters with the one before."""
    if size < 1 or not 0 <= overlap < size:
        raise ValueError("The chunk size must be at least 1 and the overlap smaller than the chunk size.")
    chunks: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in text.split("\n\n")):
        if not paragraph:
            continue
        if len(paragraph) > size:
            if current:
                chunks.append(current)
                current = ""
            step = size - overlap
            for start in range(0, len(paragraph), step):
                chunks.append(paragraph[start : start + size])
                if start + size >= len(paragraph):
                    break
            continue
        joined = f"{current}\n\n{paragraph}" if current else paragraph
        if len(joined) > size:
            chunks.append(current)
            current = paragraph
        else:
            current = joined
    if current:
        chunks.append(current)
    return chunks


def page_metadata(page: dict[str, Any], loaded_at: datetime, size: int, overlap: int) -> list[dict[str, Any]]:
    """One metadata dict per chunk. Pinecone refuses a null metadata value, so a missing value is left out."""
    parts = split_text(page.get("text") or "", size, overlap)
    items = []
    for number, part in enumerate(parts):
        item = {
            "kind": "page",
            "url": page.get("url") or "",
            "final_url": page.get("final_url"),
            "title": page.get("title") or "",
            "published": page.get("published"),
            "modified": page.get("modified"),
            "read_from": page.get("read_from"),
            "chunk": number,
            "chunks": len(parts),
            "text": part,
            "loaded_at": loaded_at.isoformat(),
        }
        items.append({k: v for k, v in item.items() if v is not None})
    return items


def _embedded_text(meta: dict[str, Any]) -> str:
    return f"{meta['title']}\n\n{meta['text']}" if meta["title"] else meta["text"]


@dataclass
class PagesResult:
    pages: int = 0
    chunks: int = 0
    price_usd: float = 0.0
    loaded: list[str] = field(default_factory=list)
    # (url, status, reason) for each page that gave no text.
    skipped: list[tuple[str, str, str | None]] = field(default_factory=list)


def _write_page(index: Any, embed: Embed, url: str, items: list[dict[str, Any]], namespace: str,
                dimension: int | None, opened: Callable[[int], Any],
                prefix: str | None = None) -> tuple[Any, int | None]:
    """Write one document's chunks, then delete its other ids. `prefix` is the id prefix of the document:
    the page's own by default, a research report's when research.py calls."""
    prefix = prefix or page_prefix(url)
    written: set[str] = set()
    for first in range(0, len(items), BATCH):
        batch = items[first : first + BATCH]
        vectors = [list(map(float, v)) for v in embed([_embedded_text(m) for m in batch])]
        if len(vectors) != len(batch):
            raise ValueError(f"The embedding returned {len(vectors)} vectors for {len(batch)} texts.")
        size = dimension or len(vectors[0])
        if any(len(v) != size for v in vectors):
            raise ValueError(f"The index holds vectors of size {size}, the embedding gives {len(vectors[0])}. "
                             "Use another --index or the model the index was made with.")
        if index is None:
            index = opened(size)
        dimension = size
        records = [{"id": f"{prefix}{m['chunk']}", "values": v, "metadata": m} for m, v in zip(batch, vectors)]
        index.upsert(vectors=records, namespace=namespace)
        written.update(r["id"] for r in records)
    stale = sorted(
        i for page in index.list(prefix=prefix, namespace=namespace) for i in _ids(page) if i not in written
    )
    for first in range(0, len(stale), DELETE_BATCH):
        index.delete(ids=stale[first : first + DELETE_BATCH], namespace=namespace)
    return index, dimension


def load_pages(
    api: SpecStreamAPI,
    embed: Embed,
    urls: list[str],
    index: Any = None,
    open: Callable[[int], Any] | None = None,
    namespace: str = DEFAULT_NAMESPACE,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    format: str = "markdown",
    dimension: int | None = None,
) -> PagesResult:
    """Read `urls` with the Extract API (20 to a call, $0.80 per 1,000 pages with text) and write each page's
    chunks into a Pinecone index.

    Pass the `index`, or `open`: a function that gets the embedding's vector size and gives the index, called
    once before the first write (for example `lambda d: open_index(pc, "specstream", d)`). With `dimension`, a
    vector of another size is refused before anything is written."""
    split_text("", chunk_chars, overlap_chars)  # Refuse a bad size before anything is read or charged.
    if index is None and open is None:
        raise ValueError("Give the Pinecone index, or a function that opens it.")
    wanted = list(dict.fromkeys(u.strip() for u in urls if u and u.strip()))
    if not wanted:
        raise ValueError("Give at least one URL to read.")

    def opened(size: int) -> Any:
        assert open is not None
        return open(size)

    result = PagesResult()
    for start in range(0, len(wanted), EXTRACT_MAX_PAGES):
        answer = api.extract(wanted[start : start + EXTRACT_MAX_PAGES], format=format)
        result.price_usd += float(answer.get("price_usd") or 0)
        for page in answer.get("results") or []:
            url = page.get("url") or ""
            if page.get("status") != "ok" or not (page.get("text") or "").strip():
                result.skipped.append((url, page.get("status") or "failed", page.get("reason")))
                continue
            items = page_metadata(page, datetime.now(timezone.utc), chunk_chars, overlap_chars)
            index, dimension = _write_page(index, embed, url, items, namespace, dimension, opened)
            result.pages += 1
            result.chunks += len(items)
            result.loaded.append(url)
    return result
