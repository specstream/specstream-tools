"""Writes the records of SpecStream lists into one Pinecone index, one vector per record.

Each vector id is `<list id>#<record id>`, so a list's vectors are found by id prefix. A list loaded again
has its new vectors written first and then its old ones that are gone deleted: loading a list again
replaces it instead of doubling it, and a search never finds the list empty in between.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from specstream_pinecone.api import SpecStreamAPI, shape_record

DEFAULT_INDEX = "specstream"
DEFAULT_NAMESPACE = "__default__"
# Pinecone-hosted embedding model used when none is given, and the size of its vectors.
DEFAULT_MODEL = "llama-text-embed-v2"
DEFAULT_DIMENSION = 1024
BATCH = 96  # The most texts Pinecone's hosted models embed in one call.
DELETE_BATCH = 1000
# Pinecone keeps at most 40 KB of metadata a vector; the stored copy of the text is cut to stay under it.
TEXT_KEPT = 10_000

# Texts in, one vector per text out.
Embed = Callable[[list[str]], Sequence[Sequence[float]]]


def _part(value: str) -> str:
    """An id part in ASCII without `#`, as Pinecone lists ids by an ASCII prefix."""
    return urllib.parse.quote(value, safe="-_.~:")


def vector_id(list_id: str, record_id: str) -> str:
    return f"{_part(list_id)}#{_part(record_id)}"


def _prefix(list_id: str) -> str:
    return f"{_part(list_id)}#"


def record_text(list_name: str, record: dict[str, Any]) -> str:
    """The text that is embedded: the list name, then one `Label: value` line per value found."""
    lines = [f"List: {list_name}"] if list_name else []
    lines += [f"{label}: {value}" for label, value in record["fields"].items() if value not in (None, "")]
    return "\n".join(lines)


def records(collection: dict[str, Any], loaded_at: datetime) -> list[tuple[str, str, dict[str, Any]]]:
    """(vector id, text to embed, metadata) for each row of a list.

    Pinecone metadata is flat (strings, numbers, booleans, lists of strings, no nulls), so the values and
    their sources are kept as JSON strings next to plain keys that filters can use.
    """
    name = collection.get("name") or ""
    out = []
    for raw in collection.get("rows") or []:
        record = shape_record(raw)
        text = record_text(name, record)
        sources = {c["label"]: c["source_url"] for c in record["cells"] if c["source_url"]}
        metadata: dict[str, Any] = {
            "list_id": collection["id"],
            "list_name": name,
            "list_kind": collection.get("kind") or "",
            "list_created_at": collection.get("created_at"),
            "link": f"https://specstream.ai/workspace/collections/{collection['id']}",
            "record_id": record["record_id"],
            "entity_id": record["entity_id"],
            "fields": json.dumps(record["fields"], ensure_ascii=False),
            "sources": json.dumps(sources, ensure_ascii=False),
            "source_urls": sorted(set(sources.values())),
            "text": text[:TEXT_KEPT],
            "loaded_at": loaded_at.isoformat(),
        }
        metadata = {key: value for key, value in metadata.items() if value is not None}
        out.append((vector_id(collection["id"], record["record_id"]), text, metadata))
    return out


def _ids(page: Any) -> list[str]:
    """The ids on a page of `Index.list`: ListResponse items in Pinecone 8+, plain strings before."""
    items = getattr(page, "vectors", page)
    return [item if isinstance(item, str) else item.id for item in items]


def stored_ids(index: Any, list_id: str, namespace: str = DEFAULT_NAMESPACE) -> set[str]:
    found: set[str] = set()
    for page in index.list(prefix=_prefix(list_id), namespace=namespace):
        found.update(_ids(page))
    return found


def is_loaded(index: Any, list_id: str, namespace: str = DEFAULT_NAMESPACE) -> bool:
    page = index.list_paginated(prefix=_prefix(list_id), limit=1, namespace=namespace)
    return bool(_ids(page))


@dataclass
class LoadResult:
    lists: int = 0
    records: int = 0
    list_ids: list[str] = field(default_factory=list)


def load(
    index: Any,
    api: SpecStreamAPI,
    embed: Embed,
    namespace: str = DEFAULT_NAMESPACE,
    list_ids: list[str] | None = None,
    full: bool = False,
    dimension: int | None = None,
) -> LoadResult:
    """Load lists into a Pinecone index (a `pinecone` Index object) with dense vectors from `embed`.

    With `list_ids`, those lists are (re)loaded. Otherwise lists are read newest first until one that is
    already in the namespace; `full` reads every list again. With `dimension`, a vector of another size
    is refused before anything is written.
    """
    if list_ids:
        wanted = list(dict.fromkeys(list_ids))
    else:
        wanted = []
        for summary in api.lists():
            if not full and is_loaded(index, summary["id"], namespace):
                break  # Newest first: the rest were loaded before.
            wanted.append(summary["id"])

    result = LoadResult()
    for list_id in wanted:
        items = records(api.list(list_id), datetime.now(timezone.utc))
        old = stored_ids(index, list_id, namespace)
        for start in range(0, len(items), BATCH):
            batch = items[start : start + BATCH]
            vectors = [list(map(float, v)) for v in embed([text for _, text, _ in batch])]
            if len(vectors) != len(batch):
                raise ValueError(f"The embedding returned {len(vectors)} vectors for {len(batch)} texts.")
            size = dimension or len(vectors[0])
            if any(len(v) != size for v in vectors):
                raise ValueError(
                    f"The index holds vectors of size {size}, the embedding gives {len(vectors[0])}. "
                    "Use another --index or the model the index was made with."
                )
            index.upsert(
                vectors=[{"id": vid, "values": v, "metadata": meta} for (vid, _, meta), v in zip(batch, vectors)],
                namespace=namespace,
            )
        gone = sorted(old - {vid for vid, _, _ in items})
        for start in range(0, len(gone), DELETE_BATCH):
            index.delete(ids=gone[start : start + DELETE_BATCH], namespace=namespace)
        result.lists += 1
        result.records += len(items)
        result.list_ids.append(list_id)
    return result


def pinecone_embed(pc: Any, model: str = DEFAULT_MODEL, input_type: str = "passage") -> Embed:
    """Embeds with a model Pinecone hosts (`pc.inference.embed`): nothing to install or run here.

    Records are embedded as `passage`; embed a question with `input_type="query"`.
    """

    def embed(texts: list[str]) -> list[list[float]]:
        found = pc.inference.embed(
            model=model, inputs=texts, parameters={"input_type": input_type, "truncate": "END"}
        )
        return [list(item.values) for item in found]

    return embed


def open_index(
    pc: Any,
    name: str = DEFAULT_INDEX,
    dimension: int = DEFAULT_DIMENSION,
    cloud: str = "aws",
    region: str = "us-east-1",
) -> Any:
    """The index `name`, made on first use as a serverless dense index with cosine distance."""
    if pc.has_index(name):
        found = pc.describe_index(name)
        if found.dimension is not None and found.dimension != dimension:
            raise ValueError(
                f"Index {name!r} holds vectors of size {found.dimension}, the embedding model gives "
                f"{dimension}. Use another --index or the model the index was made with."
            )
    else:
        from pinecone import ServerlessSpec

        found = pc.create_index(
            name=name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud=cloud, region=region),
        )
    return pc.Index(host=found.host)
