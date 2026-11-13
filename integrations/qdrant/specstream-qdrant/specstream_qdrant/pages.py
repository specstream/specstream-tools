"""Reads web pages with the SpecStream Extract API and writes their text into a Qdrant collection, one point
per chunk of a page.

Each point's id is derived from the page URL and the chunk's number, and a page's old points are deleted
before its new ones are written, so reading a page again replaces it instead of doubling it. A page that
gives no text (blocked, not found, empty, failed) writes nothing, is not charged, and is reported back.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from qdrant_client import QdrantClient, models

from specstream_qdrant.api import EXTRACT_MAX_PAGES, SpecStreamAPI
from specstream_qdrant.load import BATCH, Embed, ensure_collection

DEFAULT_PAGES_COLLECTION = "specstream_pages"
DEFAULT_CHUNK_CHARS = 2000
DEFAULT_OVERLAP_CHARS = 200

# Fixed namespace so a chunk keeps the same point id across loads and machines.
_PAGE_NAMESPACE = uuid.UUID("0d6f2b8e-7c43-4a1e-b5a9-6e2f81c4d3b7")


def chunk_id(url: str, chunk: int) -> str:
    return str(uuid.uuid5(_PAGE_NAMESPACE, f"{url}#{chunk}"))


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


def page_payloads(page: dict[str, Any], loaded_at: datetime, size: int, overlap: int) -> list[dict[str, Any]]:
    url = page.get("url") or ""
    title = page.get("title") or ""
    parts = split_text(page.get("text") or "", size, overlap)
    return [
        {
            "url": url,
            "final_url": page.get("final_url"),
            "title": title,
            "published": page.get("published"),
            "modified": page.get("modified"),
            "read_from": page.get("read_from"),
            "chunk": number,
            "chunks": len(parts),
            "text": part,
            "loaded_at": loaded_at.isoformat(),
        }
        for number, part in enumerate(parts)
    ]


def _embedded_text(payload: dict[str, Any]) -> str:
    return f"{payload['title']}\n\n{payload['text']}" if payload["title"] else payload["text"]


def _url_filter(url: str) -> models.Filter:
    return models.Filter(must=[models.FieldCondition(key="url", match=models.MatchValue(value=url))])


@dataclass
class PagesResult:
    pages: int = 0
    chunks: int = 0
    price_usd: float = 0.0
    loaded: list[str] = field(default_factory=list)
    # (url, status, reason) for each page that gave no text.
    skipped: list[tuple[str, str, str | None]] = field(default_factory=list)


def load_pages(
    client: QdrantClient,
    api: SpecStreamAPI,
    embed: Embed,
    urls: list[str],
    collection: str = DEFAULT_PAGES_COLLECTION,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    format: str = "markdown",
) -> PagesResult:
    """Read `urls` with the Extract API (20 to a call) and write each page's chunks into a Qdrant collection,
    created on first use with the embedding's vector size and a payload index on `url`."""
    split_text("", chunk_chars, overlap_chars)  # Refuse a bad size before anything is read or charged.
    wanted = list(dict.fromkeys(u.strip() for u in urls if u and u.strip()))
    if not wanted:
        raise ValueError("Give at least one URL to read.")

    result = PagesResult()
    for start in range(0, len(wanted), EXTRACT_MAX_PAGES):
        answer = api.extract(wanted[start : start + EXTRACT_MAX_PAGES], format=format)
        result.price_usd += float(answer.get("price_usd") or 0)
        for page in answer.get("results") or []:
            url = page.get("url") or ""
            if page.get("status") != "ok" or not (page.get("text") or "").strip():
                result.skipped.append((url, page.get("status") or "failed", page.get("reason")))
                continue
            items = page_payloads(page, datetime.now(timezone.utc), chunk_chars, overlap_chars)
            if client.collection_exists(collection):
                client.delete(collection, points_selector=models.FilterSelector(filter=_url_filter(url)))
            for first in range(0, len(items), BATCH):
                batch = items[first : first + BATCH]
                vectors = [list(map(float, v)) for v in embed([_embedded_text(p) for p in batch])]
                if len(vectors) != len(batch):
                    raise ValueError(f"The embedding returned {len(vectors)} vectors for {len(batch)} texts.")
                ensure_collection(client, collection, len(vectors[0]), indexed=("url",))
                client.upsert(
                    collection,
                    points=[
                        models.PointStruct(id=chunk_id(url, p["chunk"]), vector=v, payload=p)
                        for p, v in zip(batch, vectors)
                    ],
                    wait=True,
                )
            result.pages += 1
            result.chunks += len(items)
            result.loaded.append(url)
    return result
