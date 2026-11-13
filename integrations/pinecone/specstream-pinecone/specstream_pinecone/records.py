"""Keeps a Pinecone index in step with SpecStream's public-records files, one vector per record.

Two sources:

- A licence link (https://specstream.ai/data/licence): each family's whole file, a file of new records
  for each day and a removal list for each day. The first run loads the whole file. Every later run
  applies only the days after the last one it applied: the removal list first, then the new records.
  The day a family was last applied is kept in the index itself (one marker vector per family in the
  namespace `specstream-state`), so the feed runs from any machine or scheduler with no file of its own.
- A public feed in JSON Feed form (https://specstream.ai/feeds/us-funding-rounds.json), which needs no
  licence and no key: each run writes only the items the namespace does not hold yet.

The licence link carries a secret, so it never appears in an error or in a vector.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, BinaryIO

from specstream_pinecone import __version__
from specstream_pinecone.api import SpecStreamError
from specstream_pinecone.load import BATCH, DEFAULT_NAMESPACE, DELETE_BATCH, TEXT_KEPT, Embed, _ids

SITE = "https://specstream.ai"
DEFAULT_FEED = f"{SITE}/feeds/us-funding-rounds.json"
STATE_NAMESPACE = "specstream-state"
# The delivery keeps the newest 35 days of new-record files. A feed that last ran longer ago than this
# (less a margin) cannot tell which days it missed, so it loads the whole file again.
DAYS_KEPT = 30
# Pinecone keeps at most 40 KB of metadata a vector; the JSON copy of a row is left out above this size.
FIELDS_KEPT = 20_000

_LINK = re.compile(r"^(https?://[^/]+)/data/files/([A-Za-z0-9_-]{43})(?:/(?:index\.json)?)?$")
_FAMILY = re.compile(r"^[a-z_]+$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# (url, headers) -> the body as a binary stream. Tests pass a scripted one.
Open = Callable[[str, dict[str, str]], BinaryIO]


def _urllib_open(url: str, headers: dict[str, str]) -> BinaryIO:
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=300)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _prefix(kind: str, name: str) -> str:
    return f"{kind}:{name}#"


def record_id(family: str, key_cell: str) -> str:
    """The vector id of a family's record: the family, then a digest of the cell that names the record."""
    return _prefix("records", family) + _digest(key_cell)


def feed_slug(feed_url: str) -> str:
    name = feed_url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9-]+", "-", re.sub(r"\.json$", "", name.lower())).strip("-") or "feed"


def item_id(slug: str, item_key: str) -> str:
    return _prefix("feed", slug) + _digest(item_key)


class RecordFiles:
    """Reads a licence's delivery: the index, the whole files, the day files and the public dictionaries."""

    def __init__(self, link: str, open_url: Open | None = None) -> None:
        found = _LINK.match((link or "").strip())
        if not found:
            raise SpecStreamError(
                "A licence link is required (SPECSTREAM_RECORDS_LINK): the address SpecStream sent with the "
                f"licence, {SITE}/data/files/<43 characters>. The licence is at {SITE}/data/licence. "
                "A public feed needs none: use --feed."
            )
        self._site, self._token = found.group(1), found.group(2)
        self._base = f"{self._site}/data/files/{self._token}"
        self._open = open_url or _urllib_open
        self._headers = {"User-Agent": f"specstream-pinecone/{__version__}"}

    def _stream(self, url: str) -> BinaryIO:
        shown = url.replace(self._token, "<licence>")
        try:
            return self._open(url, self._headers)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise SpecStreamError(
                    f"SpecStream has no file at {shown} for this licence (404). Check the link and the "
                    f"licence's end date: {SITE}/data/licence."
                ) from None
            raise SpecStreamError(f"SpecStream answered {exc.code} for {shown}.") from None
        except urllib.error.URLError as exc:
            raise SpecStreamError(f"Could not reach SpecStream: {exc.reason}") from None

    def _json(self, url: str) -> dict[str, Any]:
        with self._stream(url) as body:
            return json.loads(body.read().decode("utf-8"))

    def index(self) -> dict[str, Any]:
        return self._json(f"{self._base}/index.json")

    def key_column(self, family: str) -> str | None:
        """The column that names a record, from the family's public data dictionary; None when every
        cell together names it."""
        key = self._json(f"{self._site}/data/licence/{family}/dictionary.json").get("key")
        return key if isinstance(key, str) and key else None

    def rows(self, family: str, kind: str = "", day: str = "") -> Iterator[dict[str, str]]:
        """The rows of a gzipped CSV, streamed: the whole file, or the `new` or `removed` file of a day."""
        if not _FAMILY.match(family) or (kind and (kind not in ("new", "removed") or not _DAY.match(day))):
            raise SpecStreamError(f"The licence index names a file this loader does not read: {family} {kind} {day}")
        url = f"{self._base}/{family}/{kind}/{day}.csv.gz" if kind else f"{self._base}/{family}.csv.gz"
        with self._stream(url) as body, gzip.GzipFile(fileobj=body) as plain:
            reader = csv.reader(io.TextIOWrapper(plain, encoding="utf-8", newline=""))
            header = next(reader, None)
            if not header:
                return
            for row in reader:
                yield {label: (row[i] if i < len(row) else "") for i, label in enumerate(header)}


class _Keys:
    """The id of each row of one file. A row with a blank key cell is named by all its cells; a key met
    again in one file gets its occurrence number, so two rows never share a vector."""

    def __init__(self, family: str, key_column: str | None) -> None:
        self.family, self.key_column = family, key_column
        self.seen: dict[str, int] = {}

    def __call__(self, row: dict[str, str]) -> str:
        cell = (row.get(self.key_column) or "").strip() if self.key_column else ""
        cell = cell or "\x1f".join(row.values())
        n = self.seen.get(cell, 0)
        self.seen[cell] = n + 1
        return record_id(self.family, cell if n == 0 else f"{cell}\x1e{n}")


def row_text(title: str, row: dict[str, str]) -> str:
    """The text that is embedded: the family's title, then one `Column: value` line per filled cell."""
    lines = [f"Records: {title}"] if title else []
    lines += [f"{label}: {value}" for label, value in row.items() if value.strip() and label != "Source"]
    return "\n".join(lines)


Item = tuple[str, str, dict[str, Any]]  # vector id, text to embed, metadata


def _row_vector(entry: dict[str, Any], keys: _Keys, row: dict[str, str], loaded_at: str) -> Item:
    title = entry.get("title") or entry["family"]
    text = row_text(title, row)
    source = (row.get("Source") or "").strip()
    fields = json.dumps({k: v for k, v in row.items() if v.strip()}, ensure_ascii=False)
    metadata: dict[str, Any] = {
        "kind": "record",
        "family": entry["family"],
        "family_title": title,
        "link": entry.get("hub") or "",
        "name": next(iter(row.values()), ""),
        "key": (row.get(keys.key_column) or "").strip() if keys.key_column else "",
        "fields": fields if len(fields) <= FIELDS_KEPT else "{}",
        "source_urls": [source] if source else [],
        "text": text[:TEXT_KEPT],
        "loaded_at": loaded_at,
    }
    return keys(row), text, metadata


@dataclass
class _Writer:
    """Embeds and upserts in batches of 96."""

    index: Any
    embed: Embed
    namespace: str
    dimension: int
    pending: list[Item] = field(default_factory=list)
    written: int = 0

    def add(self, item: Item) -> None:
        self.pending.append(item)
        if len(self.pending) >= BATCH:
            self.flush()

    def flush(self) -> None:
        batch, self.pending = self.pending, []
        if not batch:
            return
        vectors = [list(map(float, v)) for v in self.embed([text for _, text, _ in batch])]
        if len(vectors) != len(batch):
            raise ValueError(f"The embedding returned {len(vectors)} vectors for {len(batch)} texts.")
        if any(len(v) != self.dimension for v in vectors):
            raise ValueError(
                f"The index holds vectors of size {self.dimension}, the embedding gives {len(vectors[0])}. "
                "Use another --index or the model the index was made with."
            )
        self.index.upsert(
            vectors=[{"id": vid, "values": v, "metadata": meta} for (vid, _, meta), v in zip(batch, vectors)],
            namespace=self.namespace,
        )
        self.written += len(batch)


def _stored(index: Any, prefix: str, namespace: str) -> set[str]:
    found: set[str] = set()
    for page in index.list(prefix=prefix, namespace=namespace):
        found.update(_ids(page))
    return found


def _delete(index: Any, ids: Iterable[str], namespace: str) -> int:
    gone = sorted(set(ids))
    for start in range(0, len(gone), DELETE_BATCH):
        index.delete(ids=gone[start : start + DELETE_BATCH], namespace=namespace)
    return len(gone)


def _marker_id(family: str, namespace: str) -> str:
    return f"records:{family}@{namespace}"


def read_state(index: Any, family: str, namespace: str = DEFAULT_NAMESPACE) -> dict[str, Any] | None:
    """What the last run left for a family: the day applied through, the key column, the file's build."""
    marker = _marker_id(family, namespace)
    found = (index.fetch(ids=[marker], namespace=STATE_NAMESPACE).vectors or {}).get(marker)
    if found is None:
        return None
    meta = found["metadata"] if isinstance(found, dict) else found.metadata
    return dict(meta) if meta and meta.get("through") else None


def _write_state(index: Any, family: str, namespace: str, dimension: int, through: str, key: str | None, built: str) -> None:
    index.upsert(
        vectors=[{
            "id": _marker_id(family, namespace),
            "values": [1.0] + [0.0] * (dimension - 1),
            "metadata": {"kind": "state", "family": family, "namespace": namespace, "through": through,
                         "key_column": key or "", "built": built,
                         "updated_at": datetime.now(timezone.utc).isoformat()},
        }],
        namespace=STATE_NAMESPACE,
    )


@dataclass
class FamilyResult:
    family: str
    mode: str  # "whole", "days" or "current"
    written: int = 0
    deleted: int = 0
    days: list[str] = field(default_factory=list)
    through: str = ""


def _days(entry: dict[str, Any], kind: str) -> set[str]:
    return {d["date"] for d in entry.get(kind) or [] if isinstance(d, dict) and _DAY.match(str(d.get("date")))}


def sync_records(
    index: Any,
    files: RecordFiles,
    embed: Embed,
    dimension: int,
    namespace: str = DEFAULT_NAMESPACE,
    families: list[str] | None = None,
    full: bool = False,
    today: date | None = None,
) -> list[FamilyResult]:
    """Bring the index up to the licence's files. Run it once a day; a run with nothing new writes nothing.

    A family gets its whole file (every row written, then the vectors of rows that are gone deleted) when
    it has no marker yet, with `full`, when its key column is not last time's, or when it was last applied
    more than DAYS_KEPT days ago. A family with no key column gets its whole file each time the file was
    built again. Any other family gets the days after its marker, oldest first: the ids on the day's
    removal list are deleted, then the day's new records are written.

    A removal list also names a record that stays in the file with one value withdrawn. Its vector is
    deleted too, because the withdrawn value is in it; the next whole load brings the record back
    without that value.
    """
    today = today or datetime.now(timezone.utc).date()
    entries = {e["family"]: e for e in files.index().get("families") or [] if _FAMILY.match(str(e.get("family")))}
    wanted = list(dict.fromkeys(families)) if families else list(entries)
    missing = [f for f in wanted if f not in entries]
    if missing:
        raise SpecStreamError(
            f"The licence does not hold {', '.join(missing)}. It holds: {', '.join(sorted(entries)) or 'no family'}."
        )
    results = []
    for family in wanted:
        entry = entries[family]
        key = files.key_column(family)
        state = None if full else read_state(index, family, namespace)
        built = str(entry.get("built") or "")
        loaded_at = datetime.now(timezone.utc).isoformat()
        writer = _Writer(index, embed, namespace, dimension)
        if state and key is None and state.get("built") == built:
            results.append(FamilyResult(family, "current", through=state["through"]))
            continue
        stale = bool(state) and state["through"] < (today - timedelta(days=DAYS_KEPT)).isoformat()
        if not state or stale or key is None or (state.get("key_column") or None) != key:
            result = FamilyResult(family, "whole")
            old = _stored(index, _prefix("records", family), namespace)
            keys, kept = _Keys(family, key), set()
            for row in files.rows(family):
                item = _row_vector(entry, keys, row, loaded_at)
                kept.add(item[0])
                writer.add(item)
            writer.flush()
            result.deleted = _delete(index, old - kept, namespace)
            # The whole file holds every day up to its build; later days are applied by the next run.
            result.through = built[:10] if _DAY.match(built[:10]) else today.isoformat()
            _write_state(index, family, namespace, dimension, result.through, key, built)
        else:
            result = FamilyResult(family, "days", through=state["through"])
            new, removed = _days(entry, "new"), _days(entry, "removed")
            for day in sorted(d for d in new | removed if d > state["through"]):
                if day in removed:
                    gone = [record_id(family, cell) for row in files.rows(family, "removed", day)
                            if (cell := (row.get(key) or "").strip())]
                    result.deleted += _delete(index, gone, namespace)
                if day in new:
                    keys = _Keys(family, key)
                    for row in files.rows(family, "new", day):
                        writer.add(_row_vector(entry, keys, row, loaded_at))
                    writer.flush()
                result.days.append(day)
                result.through = day
                # The marker moves day by day: a run that stops half way goes on from the last whole day.
                _write_state(index, family, namespace, dimension, day, key, built)
            if not result.days:
                result.mode = "current"
        result.written = writer.written
        results.append(result)
    return results


@dataclass
class FeedResult:
    feed: str
    items: int = 0
    written: int = 0


def sync_feed(
    index: Any,
    embed: Embed,
    dimension: int,
    feed_url: str = DEFAULT_FEED,
    namespace: str = DEFAULT_NAMESPACE,
    open_url: Open | None = None,
) -> FeedResult:
    """Write the items of a public SpecStream feed (JSON Feed) that the namespace does not hold yet."""
    if not re.match(r"^https?://", feed_url):
        raise SpecStreamError(f"A feed is an http(s) address, such as {DEFAULT_FEED}.")
    try:
        with (open_url or _urllib_open)(feed_url, {"User-Agent": f"specstream-pinecone/{__version__}"}) as body:
            feed = json.loads(body.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SpecStreamError(f"The feed {feed_url} answered {exc.code}.") from None
    except urllib.error.URLError as exc:
        raise SpecStreamError(f"Could not reach the feed {feed_url}: {exc.reason}") from None
    except ValueError:
        raise SpecStreamError(f"{feed_url} is not a JSON Feed.") from None
    items = feed.get("items") if isinstance(feed, dict) else None
    if not isinstance(items, list):
        raise SpecStreamError(f"{feed_url} is not a JSON Feed: it has no items.")
    slug = feed_slug(feed_url)
    held = _stored(index, _prefix("feed", slug), namespace)
    writer = _Writer(index, embed, namespace, dimension)
    loaded_at = datetime.now(timezone.utc).isoformat()
    result = FeedResult(feed_url)
    for item in items:
        key = str(item.get("id") or item.get("url") or "") if isinstance(item, dict) else ""
        if not key:
            continue
        result.items += 1
        vid = item_id(slug, key)
        if vid in held:
            continue
        held.add(vid)
        title, body_text = str(item.get("title") or ""), str(item.get("content_text") or "")
        text = "\n".join(part for part in (title, body_text) if part)
        url = str(item.get("url") or "")
        metadata = {
            "kind": "feed_item",
            "feed": slug,
            "feed_title": str(feed.get("title") or ""),
            "link": url,
            "name": title,
            "published": str(item.get("date_published") or ""),
            "tags": [str(t) for t in item.get("tags") or []],
            "source_urls": [url] if url else [],
            "text": text[:TEXT_KEPT],
            "loaded_at": loaded_at,
        }
        writer.add((vid, text, metadata))
    writer.flush()
    result.written = writer.written
    return result
