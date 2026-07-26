"""Driver Modbus TCP — driver de REFERENCIA de la Fase 1.

===============================================================================
STUB PARA REVISIÓN / RELLENO POR MODELO ECONÓMICO (Gemini Flash / GLM / Sonnet).
===============================================================================
La INTERFAZ y las decisiones de diseño están fijadas por Opus (ver docstrings y
ARCHITECTURE.md). La implementación concreta de pymodbus es "patrón conocido" y
se delega según la matriz de modelos del ROADMAP §0.

TODO(econ) — implementar contra `pymodbus>=3.6,<4` (R6):
  1. connect(): abrir AsyncModbusTcpClient(host, port) desde node.config.
     - Como pymodbus 3.x ya es async nativo, NO hace falta to_thread aquí.
       (Se deja `read_block` async directo; si se usara una lib síncrona,
        envolver en asyncio.to_thread — ver §3.1.)
  2. read_block(tags): agrupar tags por rango CONTIGUO de registros y hacer una
     lectura por bloque (§3.2). Parsear `tag.address` (p. ej. "40001") -> registro.
     Devolver list[TagValue] con quality="good"/"bad" según el resultado.
  3. write_tag(tag_id, value): resolver el tag -> dirección y escribir un registro.
  4. Manejo de errores/reconexión: dejar que el runtime (TaskGroup) gestione el
     backoff; aquí propagar excepciones claras.

Tests esperados (ROADMAP F1): contra el simulador `modbus_sim` vía fixture pytest.
"""

from __future__ import annotations

from typing import Any

from app.drivers.base import BaseDriver
from app.drivers.registry import register_driver
from app.models.tag import Tag, TagValue


@register_driver("modbus_tcp")
class ModbusDriver(BaseDriver):
    async def connect(self) -> None:
        # TODO(econ): abrir AsyncModbusTcpClient(host=self.config["host"], ...).
        raise NotImplementedError("ModbusDriver.connect — pendiente (ver TODO en el módulo)")

    async def disconnect(self) -> None:
        # TODO(econ): cerrar el cliente si está abierto.
        raise NotImplementedError("ModbusDriver.disconnect — pendiente")

    async def read_block(self, tags: list[Tag]) -> list[TagValue]:
        # TODO(econ): agrupar por rango contiguo y leer por bloque (§3.2).
        raise NotImplementedError("ModbusDriver.read_block — pendiente")

    async def write_tag(self, tag_id: str, value: Any) -> bool:
        # TODO(econ): resolver dirección y escribir registro.
        raise NotImplementedError("ModbusDriver.write_tag — pendiente")
