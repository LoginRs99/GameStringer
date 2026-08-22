"""Translation memory. Persistent, SQLite-backed, one DB per project
by default (configurable — nothing stops two projects sharing one).

The whole point of this module is: never call the LLM twice for the
same (content_hash, category, context_key). See context_key.py for
why the key isn't just the source string.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .models import TMRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tm (
    tm_key TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    category TEXT NOT NULL,
    context_key TEXT,
    source TEXT NOT NULL,
    translation TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    quality_score REAL NOT NULL DEFAULT 0.0,
    origin TEXT NOT NULL,
    times_used INTEGER NOT NULL DEFAULT 0,
    last_used REAL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tm_content_hash ON tm(content_hash);
CREATE INDEX IF NOT EXISTS idx_tm_lang_pair ON tm(source_lang, target_lang);
"""


class TranslationMemory:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path) if isinstance(db_path, str) else db_path
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @classmethod
    def open_readonly(cls, db_path: Path) -> "TranslationMemory":
        """Return an in-memory TM pre-loaded from db_path, for plan().

        plan() needs to call commit_to_tm() on it (to seed TM hits from
        pre-existing translations in source files), but must not write to the
        real on-disk database. The solution: clone the real DB into an
        in-memory SQLite connection via sqlite3's backup() API, then close the
        on-disk connection immediately. plan() gets a writable TM with full
        TM contents, and the real database file is never opened for writing.

        Falls back to a fresh empty in-memory TM when db_path does not exist
        (first run of a new project), matching the previous plan() behaviour.
        """
        mem = cls(":memory:")
        if not db_path.exists():
            return mem
        disk_conn = sqlite3.connect(str(db_path))
        try:
            disk_conn.backup(mem._conn)
        finally:
            disk_conn.close()
        return mem

    @contextmanager
    def _cursor(self):
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        finally:
            cur.close()

    def get(self, tm_key: str) -> Optional[TMRecord]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM tm WHERE tm_key = ?", (tm_key,))
            row = cur.fetchone()
        if row is None:
            return None
        return TMRecord(
            tm_key=row["tm_key"],
            source=row["source"],
            translation=row["translation"],
            source_lang=row["source_lang"],
            target_lang=row["target_lang"],
            category=row["category"],
            context_key=row["context_key"],
            quality_score=row["quality_score"],
            origin=row["origin"],
            times_used=row["times_used"],
        )

    def get_many(self, tm_keys: Iterable[str]) -> dict[str, TMRecord]:
        keys = list(dict.fromkeys(tm_keys))
        if not keys:
            return {}
        out: dict[str, TMRecord] = {}
        # SQLite has a default limit around 999 host params — chunk defensively.
        for i in range(0, len(keys), 500):
            chunk = keys[i : i + 500]
            placeholders = ",".join("?" for _ in chunk)
            with self._cursor() as cur:
                cur.execute(f"SELECT * FROM tm WHERE tm_key IN ({placeholders})", chunk)
                rows = cur.fetchall()
            for row in rows:
                out[row["tm_key"]] = TMRecord(
                    tm_key=row["tm_key"],
                    source=row["source"],
                    translation=row["translation"],
                    source_lang=row["source_lang"],
                    target_lang=row["target_lang"],
                    category=row["category"],
                    context_key=row["context_key"],
                    quality_score=row["quality_score"],
                    origin=row["origin"],
                    times_used=row["times_used"],
                )
        return out

    def mark_used(self, tm_key: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE tm SET times_used = times_used + 1, last_used = ? WHERE tm_key = ?",
                (time.time(), tm_key),
            )

    def mark_used_many(self, tm_keys: Iterable[str]) -> None:
        """Same as calling mark_used() per key, but one transaction for the
        whole batch instead of one fsync-ed commit per key. A file with a
        high TM-hit ratio (the whole point of a TM) could otherwise mean
        thousands of individual commits just to record reuse counts.
        """
        keys = list(tm_keys)
        if not keys:
            return
        now = time.time()
        with self._cursor() as cur:
            cur.executemany(
                "UPDATE tm SET times_used = times_used + 1, last_used = ? WHERE tm_key = ?",
                [(now, k) for k in keys],
            )

    def upsert(self, content_hash: str, record: TMRecord) -> None:
        with self._cursor() as cur:
            self._upsert_one(cur, content_hash, record)

    def upsert_many(self, records: Iterable[tuple[str, TMRecord]]) -> None:
        """Batched upsert -- one transaction for potentially thousands of
        records instead of one commit (and one fsync) per record. This is
        what commit_to_tm() uses now; a large already-translated dump (a
        big Unity/UABEA export, say) used to mean one disk sync per string.
        """
        records = list(records)
        if not records:
            return
        with self._cursor() as cur:
            for content_hash, record in records:
                self._upsert_one(cur, content_hash, record)

    def _upsert_one(self, cur, content_hash: str, record: TMRecord) -> None:
        cur.execute(
            """
            INSERT INTO tm (tm_key, content_hash, category, context_key, source,
                             translation, source_lang, target_lang, quality_score,
                             origin, times_used, last_used, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tm_key) DO UPDATE SET
                translation = excluded.translation,
                quality_score = excluded.quality_score,
                origin = excluded.origin
            """,
            (
                record.tm_key,
                content_hash,
                record.category,
                record.context_key,
                record.source,
                record.translation,
                record.source_lang,
                record.target_lang,
                record.quality_score,
                record.origin,
                record.times_used,
                None,
                time.time(),
            ),
        )

    def iter_all(self) -> Iterator[tuple[str, TMRecord]]:
        """Yield all stored (content_hash, record) pairs from the translation memory."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM tm ORDER BY created_at ASC, tm_key ASC")
            rows = cur.fetchall()
        for row in rows:
            record = TMRecord(
                tm_key=row["tm_key"],
                source=row["source"],
                translation=row["translation"],
                source_lang=row["source_lang"],
                target_lang=row["target_lang"],
                category=row["category"],
                context_key=row["context_key"],
                quality_score=row["quality_score"],
                origin=row["origin"],
                times_used=row["times_used"],
            )
            yield row["content_hash"], record

    def invalidate(self, content_hash: str) -> bool:
        """Delete TM records matching content_hash or tm_key. Returns True if any record was deleted."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM tm WHERE content_hash = ? OR tm_key = ?", (content_hash, content_hash))
            deleted = cur.rowcount > 0
        return deleted

    def stats(self) -> dict:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*), COALESCE(SUM(times_used), 0) FROM tm")
            total, reuses = cur.fetchone()
        return {"tm_entries": total, "tm_reuses": reuses}

    def close(self) -> None:
        self._conn.close()
