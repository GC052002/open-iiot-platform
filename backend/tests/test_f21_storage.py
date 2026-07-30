"""F2.1: persistencia — SQLiteHistorian (Repository) + TagBuffer (suscriptor raw)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.engine.tag_cache import TagCache
from app.models.tag import Tag, TagValue
from app.storage import SQLiteHistorian, TagBuffer

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _tv(tag_id: str, value, secs: float) -> TagValue:
    return TagValue(tag_id=tag_id, value=value, ts=_BASE + timedelta(seconds=secs))


# --- Repository (SQLite) ----------------------------------------------------

async def test_sqlite_insert_and_query(tmp_path):
    repo = SQLiteHistorian(str(tmp_path / "h.db"))
    await repo.init()
    try:
        await repo.insert("A", [_tv("t", 10.0, 0), _tv("t", 11.0, 1)])
        rows = await repo.query("A", "t")
        assert [r["value"] for r in rows] == [11.0, 10.0]  # ts desc
        assert rows[0]["quality"] == "good"
    finally:
        await repo.close()


async def test_sqlite_segments_by_project(tmp_path):
    repo = SQLiteHistorian(str(tmp_path / "h.db"))
    await repo.init()
    try:
        await repo.insert("A", [_tv("t", 1.0, 0)])
        await repo.insert("B", [_tv("t", 2.0, 0)])
        assert [r["value"] for r in await repo.query("A", "t")] == [1.0]
        assert [r["value"] for r in await repo.query("B", "t")] == [2.0]
    finally:
        await repo.close()


async def test_sqlite_stores_text_values(tmp_path):
    repo = SQLiteHistorian(str(tmp_path / "h.db"))
    await repo.init()
    try:
        await repo.insert("A", [_tv("s", "RUN", 0)])
        assert (await repo.query("A", "s"))[0]["value"] == "RUN"
    finally:
        await repo.close()


async def test_sqlite_wal_mode_enabled(tmp_path):
    # Rev 9: WAL activo para lecturas concurrentes no bloqueantes.
    import sqlite3

    repo = SQLiteHistorian(str(tmp_path / "h.db"))
    await repo.init()
    try:
        mode = repo._conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        await repo.close()


# --- TagBuffer --------------------------------------------------------------

class _FakeRepo:
    def __init__(self):
        self.inserts: list[tuple[str, list]] = []

    async def insert(self, project_id, samples):
        self.inserts.append((project_id, list(samples)))


class _FlakyRepo:
    """Falla las primeras `fail_times` inserciones, luego persiste."""

    def __init__(self, fail_times: int):
        self._fail = fail_times
        self.saved: list = []

    async def insert(self, project_id, samples):
        if self._fail > 0:
            self._fail -= 1
            raise RuntimeError("disco temporalmente caído")
        self.saved.extend(samples)


async def test_tag_buffer_flushes_on_max_batch():
    repo = _FakeRepo()
    buf = TagBuffer(repo, flush_interval=999, max_batch=3)
    await buf.on_samples("A", [_tv("t", 1, 0), _tv("t", 2, 1)])  # 2 < 3, no flush
    assert repo.inserts == []
    await buf.on_samples("A", [_tv("t", 3, 2)])                  # 3 >= 3, flush
    assert len(repo.inserts) == 1
    assert len(repo.inserts[0][1]) == 3


async def test_tag_buffer_retries_failed_batch_without_loss():
    # Rev 9: un fallo transitorio de disco no debe perder telemetría.
    repo = _FlakyRepo(fail_times=1)
    buf = TagBuffer(repo, flush_interval=999, max_batch=1000)
    await buf.on_samples("A", [_tv("t", 1, 0), _tv("t", 2, 1)])
    await buf.flush()                 # falla -> reencola
    assert repo.saved == []
    await buf.flush()                 # reintento -> persiste
    assert len(repo.saved) == 2       # ninguna muestra perdida


async def test_tag_buffer_final_flush_on_stop():
    repo = _FakeRepo()
    buf = TagBuffer(repo, flush_interval=999, max_batch=1000)
    buf.start()
    await buf.on_samples("A", [_tv("t", 1, 0)])
    await buf.stop()  # flush final
    assert len(repo.inserts) == 1


# --- Integración: TagCache raw -> historiador conserva intermedios ----------

async def test_historian_keeps_deadband_filtered_intermediates(tmp_path):
    repo = SQLiteHistorian(str(tmp_path / "h.db"))
    await repo.init()
    buf = TagBuffer(repo, flush_interval=999, max_batch=1000)
    cache = TagCache()
    cache.set_tags("A", {"t": Tag(id="t", name="t", driver_id="d1", address="0", deadband=1.0)})
    cache.subscribe(buf.on_samples, raw=True)  # historiador = raw
    try:
        await cache.update("A", [_tv("t", 5.0, 0)])   # significativo
        await cache.update("A", [_tv("t", 5.1, 1)])   # < deadband: NO va al WS, pero SÍ al historiador
        await buf.flush()
        rows = await repo.query("A", "t")
        # El historiador conserva ambas muestras (no solo el delta).
        assert [r["value"] for r in rows] == [5.1, 5.0]
    finally:
        await buf.stop()
        await repo.close()
