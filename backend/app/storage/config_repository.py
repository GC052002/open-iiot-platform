"""Persistencia de configuración de la plataforma (F4.0/F4.1/F4.1b/F4.1c).

Patrón Repository (§6), separado del historiador: mientras el historiador guarda
**series temporales** (`iiot_history.db`), este repositorio guarda la **configuración
multiusuario** (usuarios, proyectos, miembros, versiones publicadas y secretos) en su
propia BD (`iiot_config.db`, env `IIOT_CONFIG_DB`).

Se usa `sqlite3` de la stdlib (apto air-gapped). Igual que `SQLiteHistorian`, las
operaciones bloqueantes corren en `asyncio.to_thread` y se serializan con un
`asyncio.Lock`; con WAL, las lecturas no bloquean a las escrituras. La misma interfaz
abstracta permite una implementación PostgreSQL cuando se active el modo central (§3).
"""

from __future__ import annotations

import abc
from typing import Any


class ConfigRepository(abc.ABC):
    """Interfaz de persistencia de configuración (usuarios, proyectos, secretos)."""

    @abc.abstractmethod
    async def init(self) -> None:
        """Crea el esquema/índices si no existen."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Libera recursos."""

    # -- Usuarios (F4.0) ------------------------------------------------------
    @abc.abstractmethod
    async def upsert_user(self, row: dict[str, Any]) -> None:
        """Crea o reemplaza un usuario (`username`, `password_hash`, `salt`,
        `role_global`, `active`)."""

    @abc.abstractmethod
    async def get_user(self, username: str) -> dict[str, Any] | None: ...

    @abc.abstractmethod
    async def list_users(self) -> list[dict[str, Any]]: ...

    @abc.abstractmethod
    async def set_user_active(self, username: str, active: bool) -> None: ...

    @abc.abstractmethod
    async def delete_user(self, username: str) -> None: ...

    # -- Proyectos (F4.1) -----------------------------------------------------
    @abc.abstractmethod
    async def upsert_project(
        self, project_id: str, name: str, owner: str, schema_json: str
    ) -> None:
        """Crea/actualiza un proyecto conservando su `delivery_version`."""

    @abc.abstractmethod
    async def get_project(self, project_id: str) -> dict[str, Any] | None: ...

    @abc.abstractmethod
    async def list_projects(self) -> list[dict[str, Any]]: ...

    @abc.abstractmethod
    async def list_projects_for_user(self, username: str) -> list[dict[str, Any]]:
        """Proyectos donde el usuario es owner o miembro."""

    @abc.abstractmethod
    async def delete_project(self, project_id: str) -> None: ...

    # -- Miembros por proyecto (F4.1) -----------------------------------------
    @abc.abstractmethod
    async def add_member(self, project_id: str, username: str, role_proj: str) -> None: ...

    @abc.abstractmethod
    async def remove_member(self, project_id: str, username: str) -> None: ...

    @abc.abstractmethod
    async def list_members(self, project_id: str) -> list[dict[str, Any]]: ...

    @abc.abstractmethod
    async def get_member_role(self, project_id: str, username: str) -> str | None: ...

    # -- Versiones de entrega (F4.1b) -----------------------------------------
    @abc.abstractmethod
    async def add_version(self, project_id: str, version: int, schema_json: str) -> None: ...

    @abc.abstractmethod
    async def get_version(self, project_id: str, version: int) -> dict[str, Any] | None: ...

    @abc.abstractmethod
    async def list_versions(self, project_id: str) -> list[dict[str, Any]]: ...

    # -- Secretos (F4.1c) -----------------------------------------------------
    @abc.abstractmethod
    async def put_secret(self, credential_id: str, ciphertext: str) -> None: ...

    @abc.abstractmethod
    async def get_secret(self, credential_id: str) -> str | None: ...
