"""An in-memory stand-in for a Pinecone index and client: the calls the loader makes, with the
keyword-only signatures of the `pinecone` package (test_load checks them against it). No network."""

from __future__ import annotations

import math
from types import SimpleNamespace


class FakeIndex:
    def __init__(self, page_size: int = 2) -> None:
        self.spaces: dict[str, dict[str, dict]] = {}
        self.page_size = page_size  # Small, to exercise pagination.
        self.calls: list[tuple[str, dict]] = []

    def upsert(self, *, vectors, namespace=""):
        self.calls.append(("upsert", {"namespace": namespace, "count": len(vectors)}))
        space = self.spaces.setdefault(namespace, {})
        for v in vectors:
            meta = v["metadata"]
            for key, value in meta.items():
                ok = isinstance(value, (str, int, float, bool)) or (
                    isinstance(value, list) and all(isinstance(x, str) for x in value)
                )
                assert ok, f"Pinecone refuses metadata {key}={value!r}"
            space[v["id"]] = {"id": v["id"], "values": list(v["values"]), "metadata": dict(meta)}
        return SimpleNamespace(upserted_count=len(vectors))

    def list_paginated(self, *, prefix=None, limit=None, pagination_token=None, namespace=""):
        ids = sorted(i for i in self.spaces.get(namespace, {}) if i.startswith(prefix or ""))
        start = int(pagination_token or 0)
        size = limit or self.page_size
        page = ids[start : start + size]
        nxt = str(start + size) if start + size < len(ids) else None
        return SimpleNamespace(
            vectors=[SimpleNamespace(id=i) for i in page],
            pagination=SimpleNamespace(next=nxt) if nxt else None,
        )

    def list(self, *, prefix=None, limit=None, namespace=""):
        token = None
        while True:
            page = self.list_paginated(prefix=prefix, limit=limit, pagination_token=token, namespace=namespace)
            if page.vectors:
                yield page
            if page.pagination is None:
                return
            token = page.pagination.next

    def fetch(self, *, ids, namespace=""):
        space = self.spaces.get(namespace, {})
        return SimpleNamespace(vectors={i: SimpleNamespace(**space[i]) for i in ids if i in space})

    def delete(self, *, ids=None, delete_all=False, filter=None, namespace=""):
        self.calls.append(("delete", {"namespace": namespace, "ids": list(ids or [])}))
        for i in ids or []:
            self.spaces.get(namespace, {}).pop(i, None)

    def query(self, *, top_k, vector=None, namespace="", filter=None, include_metadata=False):
        def cos(a, b):
            return sum(x * y for x, y in zip(a, b)) / (math.hypot(*a) * math.hypot(*b))

        rows = [
            v for v in self.spaces.get(namespace, {}).values()
            if not filter or all(v["metadata"].get(k) == c["$eq"] for k, c in filter.items())
        ]
        rows.sort(key=lambda v: -cos(vector, v["values"]))
        return SimpleNamespace(matches=[
            SimpleNamespace(id=v["id"], metadata=v["metadata"] if include_metadata else None) for v in rows[:top_k]
        ])


class FakeClient:
    """has_index / describe_index / create_index / Index / inference.embed."""

    def __init__(self, dim: int = 8) -> None:
        self.indexes: dict[str, SimpleNamespace] = {}
        self.dim = dim
        self.created: list[dict] = []
        self.embedded: list[dict] = []
        self.inference = SimpleNamespace(embed=self._embed)

    def has_index(self, name):
        return name in self.indexes

    def describe_index(self, name):
        return self.indexes[name]

    def create_index(self, name, spec=None, dimension=None, metric=None):
        self.created.append({"name": name, "dimension": dimension, "metric": metric, "spec": spec})
        self.indexes[name] = SimpleNamespace(name=name, dimension=dimension, host=f"{name}.local", store=FakeIndex())
        return self.indexes[name]

    def Index(self, name="", host=""):
        return next(i.store for i in self.indexes.values() if i.host == host)

    def _embed(self, model, inputs, parameters=None):
        self.embedded.append({"model": model, "inputs": list(inputs), "parameters": parameters})
        return [SimpleNamespace(values=[float(len(t) % 7 + 1)] * self.dim) for t in inputs]
