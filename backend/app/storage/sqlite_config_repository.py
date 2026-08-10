"""Implementación SQLite del `ConfigRepository` (F4.0/F4.1/F4.1b/F4.1c).

Mismo estilo que `SQLiteHistorian`: conexión única con `check_same_thread=False`,
WAL, y todo el I/O bloqueante en `asyncio.to_thread` serializado por un `asyncio.Lock`
para no bloquear el event loop. `row_factory = sqlite3.Row` para devolver dicts.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.storage.config_repository import ConfigRepository

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    role_global   TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    project_id       TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    owner            TEXT NOT NULL,
    schema_json      TEXT NOT NULL,
    delivery_version INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_members (
    project_id TEXT NOT NULL,
    username   TEXT NOT NULL,
    role_proj  TEXT NOT NULL,
    PRIMARY KEY (project_id, username)
);
CREATE INDEX IF NOT EXISTS ix_members_user ON project_members (username);

CREATE TABLE IF NOT EXISTS project_versions (
    project_id   TEXT NOT NULL,
    version      INTEGER NOT NULL,
    schema_json  TEXT NOT NULL,
    published_at TEXT NOT NULL,
    PRIMARY KEY (project_id, version)
);

CREATE TABLE IF NOT EXISTS secrets (
    credential_id TEXT PRIMARY KEY,
    ciphertext    TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteConfigRepository(ConfigRepository):
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        def _open() -> sqlite3.Connection:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.executescript(_SCHEMA)
            conn.commit()
            return conn

        self._conn = await asyncio.to_thread(_open)

    async def close(self) -> None:
        if self._conn is not None:
            conn = self._conn
            self._conn = None
            await asyncio.to_thread(conn.close)

    async def _run(self, fn, *args: Any) -> Any:
        """Ejecuta `fn(conn, *args)` en un hilo, serializado por el lock."""
        assert self._conn is not None, "repositorio no inicializado (llama a init())"
        async with self._lock:
            return await asyncio.to_thread(fn, self._conn, *args)

    # -- Usuarios -------------------------------------------------------------
    async def upsert_user(self, row: dict[str, Any]) -> None:
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, role_global, active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(username) DO UPDATE SET "
                "password_hash=excluded.password_hash, salt=excluded.salt, "
                "role_global=excluded.role_global, active=excluded.active",
                (row["username"], row["password_hash"], row["salt"],
                 row["role_global"], int(row.get("active", 1)),
                 row.get("created_at") or _now()),
            )
            conn.commit()

        await self._run(_do)

    async def get_user(self, username: str) -> dict[str, Any] | None:
        def _do(conn: sqlite3.Connection) -> dict[str, Any] | None:
            cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cur.fetchone()
            return dict(row) if row else None

        return await self._run(_do)

    async def list_users(self) -> list[dict[str, Any]]:
        def _do(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            cur = conn.execute("SELECT * FROM users ORDER BY username")
            return [dict(r) for r in cur.fetchall()]

        return await self._run(_do)

    async def set_user_active(self, username: str, active: bool) -> None:
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute("UPDATE users SET active = ? WHERE username = ?",
                         (int(active), username))
            conn.commit()

        await self._run(_do)

    async def delete_user(self, username: str) -> None:
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()

        await self._run(_do)

    # -- Proyectos ------------------------------------------------------------
    async def upsert_project(
        self, project_id: str, name: str, owner: str, schema_json: str
    ) -> None:
        def _do(conn: sqlite3.Connection) -> None:
            # Conserva delivery_version en updates; solo cambia en publish (add_version).
            conn.execute(
                "INSERT INTO projects (project_id, name, owner, schema_json, delivery_version, updated_at) "
                "VALUES (?, ?, ?, ?, 0, ?) "
                "ON CONFLICT(project_id) DO UPDATE SET "
                "name=excluded.name, schema_json=excluded.schema_json, updated_at=excluded.updated_at",
                (project_id, name, owner, schema_json, _now()),
            )
            conn.commit()

        await self._run(_do)

    async def get_project(self, project_id: str) -> dict[str, Any] | None:
        def _do(conn: sqlite3.Connection) -> dict[str, Any] | None:
            cur = conn.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,))
            row = cur.fetchone()
            return dict(row) if row else None

        return await self._run(_do)

    async def list_projects(self) -> list[dict[str, Any]]:
        def _do(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            cur = conn.execute(
                "SELECT project_id, name, owner, delivery_version, updated_at "
                "FROM projects ORDER BY name")
            return [dict(r) for r in cur.fetchall()]

        return await self._run(_do)

    async def list_projects_for_user(self, username: str) -> list[dict[str, Any]]:
        def _do(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            cur = conn.execute(
                "SELECT DISTINCT p.project_id, p.name, p.owner, p.delivery_version, p.updated_at "
                "FROM projects p LEFT JOIN project_members m ON p.project_id = m.project_id "
                "WHERE p.owner = ? OR m.username = ? ORDER BY p.name",
                (username, username),
            )
            return [dict(r) for r in cur.fetchall()]

        return await self._run(_do)

    async def delete_project(self, project_id: str) -> None:
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM project_members WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM project_versions WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
            conn.commit()

        await self._run(_do)

    # -- Miembros -------------------------------------------------------------
    async def add_member(self, project_id: str, username: str, role_proj: str) -> None:
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO project_members (project_id, username, role_proj) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(project_id, username) DO UPDATE SET role_proj=excluded.role_proj",
                (project_id, username, role_proj),
            )
            conn.commit()

        await self._run(_do)

    async def remove_member(self, project_id: str, username: str) -> None:
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute(
                "DELETE FROM project_members WHERE project_id = ? AND username = ?",
                (project_id, username),
            )
            conn.commit()

        await self._run(_do)

    async def list_members(self, project_id: str) -> list[dict[str, Any]]:
        def _do(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            cur = conn.execute(
                "SELECT username, role_proj FROM project_members "
                "WHERE project_id = ? ORDER BY username", (project_id,))
            return [dict(r) for r in cur.fetchall()]

        return await self._run(_do)

    async def get_member_role(self, project_id: str, username: str) -> str | None:
        def _do(conn: sqlite3.Connection) -> str | None:
            cur = conn.execute(
                "SELECT role_proj FROM project_members WHERE project_id = ? AND username = ?",
                (project_id, username),
            )
            row = cur.fetchone()
            return row["role_proj"] if row else None

        return await self._run(_do)

    # -- Versiones de entrega -------------------------------------------------
    async def add_version(self, project_id: str, version: int, schema_json: str) -> None:
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO project_versions (project_id, version, schema_json, published_at) "
                "VALUES (?, ?, ?, ?)",
                (project_id, version, schema_json, _now()),
            )
            conn.execute(
                "UPDATE projects SET delivery_version = ? WHERE project_id = ?",
                (version, project_id),
            )
            conn.commit()

        await self._run(_do)

    async def get_version(self, project_id: str, version: int) -> dict[str, Any] | None:
        def _do(conn: sqlite3.Connection) -> dict[str, Any] | None:
            cur = conn.execute(
                "SELECT * FROM project_versions WHERE project_id = ? AND version = ?",
                (project_id, version),
            )
            row = cur.fetchone()
            return dict(row) if row else None

        return await self._run(_do)

    async def list_versions(self, project_id: str) -> list[dict[str, Any]]:
        def _do(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            cur = conn.execute(
                "SELECT project_id, version, published_at FROM project_versions "
                "WHERE project_id = ? ORDER BY version DESC", (project_id,))
            return [dict(r) for r in cur.fetchall()]

        return await self._run(_do)

    # -- Secretos -------------------------------------------------------------
    async def put_secret(self, credential_id: str, ciphertext: str) -> None:
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO secrets (credential_id, ciphertext, created_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(credential_id) DO UPDATE SET ciphertext=excluded.ciphertext",
                (credential_id, ciphertext, _now()),
            )
            conn.commit()

        await self._run(_do)

    async def get_secret(self, credential_id: str) -> str | None:
        def _do(conn: sqlite3.Connection) -> str | None:
            cur = conn.execute(
                "SELECT ciphertext FROM secrets WHERE credential_id = ?", (credential_id,))
            row = cur.fetchone()
            return row["ciphertext"] if row else None

        return await self._run(_do)
