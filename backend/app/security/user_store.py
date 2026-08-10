"""Almacén de usuarios respaldado en BD (F4.0).

Sustituye al `UserStore` por-env (in-memory) de la Fase 2. Los usuarios se persisten
en el `ConfigRepository`; para no descifrar/consultar la BD en el hot-path de login,
se mantiene una **caché en memoria** que se refresca en cada mutación y al arrancar.

`authenticate`/`enabled` siguen siendo **síncronos** (los consume `security/auth.py`
igual que antes); las mutaciones (crear/desactivar/borrar) son asíncronas porque
escriben en la BD.

**Bootstrap:** si la tabla `users` está vacía, se siembra un admin una sola vez desde
`IIOT_USERS` (formato Fase 2) o `IIOT_BOOTSTRAP_ADMIN` (`usuario:contraseña`).
"""

from __future__ import annotations

import json
import logging
import os

from app.security.rbac import Role, User, hash_password, verify_password
from app.storage.config_repository import ConfigRepository

log = logging.getLogger("iiot.security")


class DbUserStore:
    def __init__(self, repo: ConfigRepository) -> None:
        self._repo = repo
        self._cache: dict[str, User] = {}

    # -- Carga / bootstrap ----------------------------------------------------
    async def load(self, *, bootstrap: bool = True) -> None:
        """Carga la caché desde la BD; siembra un admin si está vacía (una sola vez)."""
        rows = await self._repo.list_users()
        if not rows and bootstrap:
            await self._bootstrap()
            rows = await self._repo.list_users()
        self._cache = {r["username"]: self._row_to_user(r) for r in rows}

    async def _bootstrap(self) -> None:
        seeds = self._bootstrap_seeds()
        for username, password, role in seeds:
            salt, phash = hash_password(password)
            await self._repo.upsert_user({
                "username": username, "password_hash": phash, "salt": salt,
                "role_global": role, "active": 1,
            })
            log.info("Bootstrap: usuario admin '%s' sembrado.", username)

    @staticmethod
    def _bootstrap_seeds() -> list[tuple[str, str, Role]]:
        raw = os.environ.get("IIOT_USERS", "").strip()
        if raw:
            out: list[tuple[str, str, Role]] = []
            for entry in json.loads(raw):
                out.append((entry["username"], entry["password"], entry.get("role", "admin")))
            return out
        admin = os.environ.get("IIOT_BOOTSTRAP_ADMIN", "").strip()
        if admin and ":" in admin:
            username, password = admin.split(":", 1)
            return [(username, password, "admin")]
        return []

    @staticmethod
    def _row_to_user(row: dict) -> User:
        return User(username=row["username"], role=row["role_global"],
                    salt=row["salt"], password_hash=row["password_hash"],
                    active=bool(row["active"]))

    # -- Interfaz síncrona (compatible con UserStore) -------------------------
    @property
    def enabled(self) -> bool:
        """Si hay usuarios, la auth es obligatoria (fail-closed)."""
        return bool(self._cache)

    def authenticate(self, username: str, password: str) -> User | None:
        user = self._cache.get(username)
        if user is None or not user.active:
            return None
        if not verify_password(password, user.salt, user.password_hash):
            return None
        return user

    def get(self, username: str) -> User | None:
        return self._cache.get(username)

    # -- Mutaciones (BD + caché) ----------------------------------------------
    async def create_user(self, username: str, password: str, role: Role) -> User:
        salt, phash = hash_password(password)
        await self._repo.upsert_user({
            "username": username, "password_hash": phash, "salt": salt,
            "role_global": role, "active": 1,
        })
        user = User(username=username, role=role, salt=salt, password_hash=phash, active=True)
        self._cache[username] = user
        return user

    async def set_password(self, username: str, password: str) -> None:
        user = self._cache.get(username)
        if user is None:
            return
        salt, phash = hash_password(password)
        await self._repo.upsert_user({
            "username": username, "password_hash": phash, "salt": salt,
            "role_global": user.role, "active": int(user.active),
        })
        self._cache[username] = user.model_copy(update={"salt": salt, "password_hash": phash})

    async def set_active(self, username: str, active: bool) -> None:
        user = self._cache.get(username)
        if user is None:
            return
        await self._repo.set_user_active(username, active)
        self._cache[username] = user.model_copy(update={"active": active})

    async def delete_user(self, username: str) -> None:
        await self._repo.delete_user(username)
        self._cache.pop(username, None)

    def list_users(self) -> list[dict[str, object]]:
        """Lista sin material sensible (sin hash/salt)."""
        return [{"username": u.username, "role": u.role, "active": u.active}
                for u in sorted(self._cache.values(), key=lambda x: x.username)]
