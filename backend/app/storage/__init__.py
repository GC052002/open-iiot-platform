"""Persistencia del historiador (F2.1).

Patrón Repository (§6): el motor no conoce el backend de BD concreto. SQLite para
air-gapped/edge; PostgreSQL + TimescaleDB en despliegues con recursos (F2.1+).
"""

from app.storage.config_repository import ConfigRepository
from app.storage.repository import HistorianRepository
from app.storage.sqlite_config_repository import SQLiteConfigRepository
from app.storage.sqlite_repository import SQLiteHistorian
from app.storage.tag_buffer import TagBuffer

__all__ = [
    "HistorianRepository",
    "SQLiteHistorian",
    "TagBuffer",
    "ConfigRepository",
    "SQLiteConfigRepository",
]
