"""Writes the records of SpecStream lists into one Qdrant collection, one point per record.

Each point's id is derived from its list and record, and a list's old points are deleted before its new
ones are written, so loading a list again replaces it instead of doubling it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from qdrant_client import QdrantClient, models

from specstream_qdrant.api import SpecStreamAPI, shape_record

DEFAULT_COLLECTION = "specstream"
BATCH = 64

# Texts in, one vector per text out.
Embed = Callable[[list[str]], Sequence[Sequence[float]]]

# Fixed namespace so a record keeps the same point id across loads and machines.
_POINT_NAMESPACE = uuid.UUID("5f0c8a5e-4b1d-4f63-9d0e-3a52c1e7b7a1")


def point_id(list_id: str, record_id: str) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{list_id}/{record_id}"))


def record_text(list_name: str, record: dict[str, Any]) -> str:
    """The text that is embedded: the list name, then one `Label: value` line per value found."""
    lines = [f"List: {list_name}"] if list_name else []
    lines += [f"{label}: {value}" for label, value in record["fields"].items() if value not in (None, "")]
    return "\n".join(lines)


def payloads(collection: dict[str, Any], loaded_at: datetime) -> list[dict[str, Any]]:
    name = collection.get("name") or ""
    out = []
    for raw in collection.get("rows") or []:
        record = shape_record(raw)
        out.append(
            {
                "list_id": collection["id"],
                "list_name": name,
                "list_kind": collection.get("kind") or "",
                "list_created_at": collection.get("created_at"),
                "link": f"https://specstream.ai/workspace/collections/{collection['id']}",
                "record_id": record["record_id"],
                "entity_id": record["entity_id"],
                "fields": record["fields"],
                "sources": {c["label"]: c["source_url"] for c in record["cells"] if c["source_url"]},
                "cells": record["cells"],
                "text": record_text(name, record),
                "loaded_at": loaded_at.isoformat(),
            }
        )
    return out


def _list_filter(list_id: str) -> models.Filter:
    return models.Filter(must=[models.FieldCondition(key="list_id", match=models.MatchValue(value=list_id))])


def ensure_collection(
    client: QdrantClient, name: str, size: int, indexed: Sequence[str] = ("list_id", "entity_id")
) -> None:
    if client.collection_exists(name):
        info = client.get_collection(name)
        vectors = info.config.params.vectors
        existing = getattr(vectors, "size", None)
        if existing is not None and existing != size:
            raise ValueError(
                f"Collection {name!r} holds vectors of size {existing}, the embedding model gives {size}. "
                "Use another --collection or the model the collection was made with."
            )
        return
    client.create_collection(name, vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE))
    for key in indexed:
        client.create_payload_index(name, field_name=key, field_schema=models.PayloadSchemaType.KEYWORD)


def is_loaded(client: QdrantClient, collection: str, list_id: str) -> bool:
    if not client.collection_exists(collection):
        return False
    return client.count(collection, count_filter=_list_filter(list_id), exact=True).count > 0


@dataclass
class LoadResult:
    lists: int = 0
    records: int = 0
    list_ids: list[str] = field(default_factory=list)


def load(
    client: QdrantClient,
    api: SpecStreamAPI,
    embed: Embed,
    collection: str = DEFAULT_COLLECTION,
    list_ids: list[str] | None = None,
    full: bool = False,
) -> LoadResult:
    """Load lists into a Qdrant collection, created on first use with the embedding's vector size.

    With `list_ids`, those lists are (re)loaded. Otherwise lists are read newest first until one that is
    already in the collection; `full` reads every list again.
    """
    if list_ids:
        wanted = list(dict.fromkeys(list_ids))
    else:
        wanted = []
        for summary in api.lists():
            if not full and is_loaded(client, collection, summary["id"]):
                break  # Newest first: the rest were loaded before.
            wanted.append(summary["id"])

    result = LoadResult()
    for list_id in wanted:
        found = api.list(list_id)
        items = payloads(found, datetime.now(timezone.utc))
        if client.collection_exists(collection):
            client.delete(collection, points_selector=models.FilterSelector(filter=_list_filter(list_id)))
        for start in range(0, len(items), BATCH):
            batch = items[start : start + BATCH]
            vectors = [list(map(float, v)) for v in embed([p["text"] for p in batch])]
            if len(vectors) != len(batch):
                raise ValueError(f"The embedding returned {len(vectors)} vectors for {len(batch)} texts.")
            ensure_collection(client, collection, len(vectors[0]))
            client.upsert(
                collection,
                points=[
                    models.PointStruct(id=point_id(list_id, p["record_id"]), vector=v, payload=p)
                    for p, v in zip(batch, vectors)
                ],
                wait=True,
            )
        result.lists += 1
        result.records += len(items)
        result.list_ids.append(list_id)
    return result


def fastembed(model_name: str) -> Embed:
    """Embeds on this machine with FastEmbed (`pip install specstream-qdrant[fastembed]`)."""
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:  # pragma: no cover - depends on the extra
        raise ValueError(
            "FastEmbed is not installed. Run: pip install 'specstream-qdrant[fastembed]'"
        ) from exc
    model = TextEmbedding(model_name=model_name)
    return lambda texts: [vector.tolist() for vector in model.embed(texts)]
