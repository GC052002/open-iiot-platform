"""Interfaz abstracta del historiador (patrón Repository, §6).

Desacopla el motor del backend de BD concreto. Todas las operaciones están
segmentadas por `project_id` (Rev 7).
"""

from __future__ import annotations

import abc
from typing import Any

from app.models.tag import TagValue


class HistorianRepository(abc.ABC):
    @abc.abstractmethod
    async def init(self) -> None:
        """Crea el esquema/índices si no existen."""

    @abc.abstractmethod
    async def insert(self, project_id: str, samples: list[TagValue]) -> None:
        """Persiste un lote de muestras de un proyecto."""

    @abc.abstractmethod
    async def query(
        self, project_id: str, tag_id: str, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Devuelve las muestras más recientes de un tag (ts desc)."""

    # -- Audit log (F2.4b) ----------------------------------------------------
    @abc.abstractmethod
    async def record_audit(self, entry: dict[str, Any]) -> None:
        """Registra una acción crítica (login, escritura, cambio de proyecto)."""

    @abc.abstractmethod
    async def query_audit(self, project_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        """Devuelve las entradas de auditoría más recientes (ts desc)."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Libera recursos."""
