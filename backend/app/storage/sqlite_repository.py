"""Historiador SQLite (F2.1).

Usa `sqlite3` de la stdlib (sin dependencias nuevas → apto air-gapped). Las
operaciones bloqueantes corren en `asyncio.to_thread` (§3.1) y se serializan con un
`asyncio.Lock`, así el event loop nunca se bloquea.

Esquema: una tabla `samples` segmentada por `project_id` (Rev 7), con índice por
`(project_id, tag_id, ts)` para consultas por tag y rango temporal. En despliegues
con recursos se sustituye por TimescaleDB (mismo Repository, otra implementación).
"""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any

from app.models.tag import TagValue
from app.storage.repository import HistorianRepository

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    project_id TEXT NOT NULL,
    tag_id     TEXT NOT NULL,
    ts         TEXT NOT NULL,
    value_num  REAL,
    value_text TEXT,
    quality    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_samples_ptt ON samples (project_id, tag_id, ts);
"""


def _split_value(value: Any) -> tuple[float | None, str | None]:
    """Numéricos (incl. bool) van a `value_num`; el resto a `value_text`."""
    if value is None:
        return (None, None)
    if isinstance(value, (int, float)):  # bool es subclase de int
        return (float(value), None)
    return (None, str(value))


class SQLiteHistorian(HistorianRepository):
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        def _open() -> sqlite3.Connection:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            # WAL (Rev 9): lecturas de /history no bloquean ni son bloqueadas por las
            # escrituras batch del TagBuffer (evita 'database is locked' bajo carga).
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript(_SCHEMA)
            conn.commit()
            return conn

        self._conn = await asyncio.to_thread(_open)

    async def insert(self, project_id: str, samples: list[TagValue]) -> None:
        if not samples or self._conn is None:
            return
        rows = [
            (project_id, s.tag_id, s.ts.isoformat(), *_split_value(s.value), s.quality)
            for s in samples
        ]
        async with self._lock:
            await asyncio.to_thread(self._insert_sync, rows)

    def _insert_sync(self, rows: list[tuple]) -> None:
        assert self._conn is not None
        self._conn.executemany(
            "INSERT INTO samples (project_id, tag_id, ts, value_num, value_text, quality) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()

    async def query(
        self, project_id: str, tag_id: str, limit: int = 1000
    ) -> list[dict[str, Any]]:
        if self._conn is None:
            return []
        async with self._lock:
            return await asyncio.to_thread(self._query_sync, project_id, tag_id, limit)

    def _query_sync(self, project_id: str, tag_id: str, limit: int) -> list[dict[str, Any]]:
        assert self._conn is not None
        cur = self._conn.execute(
            "SELECT ts, value_num, value_text, quality FROM samples "
            "WHERE project_id = ? AND tag_id = ? ORDER BY ts DESC LIMIT ?",
            (project_id, tag_id, limit),
        )
        out: list[dict[str, Any]] = []
        for ts, vnum, vtext, quality in cur.fetchall():
            out.append({"ts": ts, "value": vtext if vtext is not None else vnum, "quality": quality})
        return out

    async def close(self) -> None:
        if self._conn is not None:
            conn = self._conn
            self._conn = None
            await asyncio.to_thread(conn.close)
