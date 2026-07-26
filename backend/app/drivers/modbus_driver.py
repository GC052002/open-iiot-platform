"""Driver Modbus TCP — driver de referencia de la Fase 1.

Implementa `BaseDriver` con `pymodbus` (async nativo en 3.x, por lo que NO requiere
`to_thread`; el patrón Adapter cubre igualmente los drivers síncronos de F2, §3.1).

Lectura por bloques (§3.2): agrupa los tags por rangos de registros contiguos y
hace una lectura Modbus por bloque, luego rebana el resultado. El scheduler entrega
una lista genérica de `Tag`; aquí es donde se traduce qué significa "contiguo".

Convención de direcciones: `tag.address` = offset entero del Holding Register.
Config del nodo (`DriverNode.config`): `host`, `port` (def. 502), `unit` (def. 1).
"""

from __future__ import annotations

import logging
from typing import Any

from pymodbus.client import AsyncModbusTcpClient

from app.drivers.base import BaseDriver
from app.drivers.registry import register_driver
from app.models.tag import Tag, TagValue

log = logging.getLogger("iiot.driver.modbus")


def _group_contiguous(addresses: list[int]) -> list[tuple[int, int]]:
    """Devuelve rangos (start, count) que cubren direcciones contiguas ordenadas."""
    if not addresses:
        return []
    ordered = sorted(set(addresses))
    ranges: list[tuple[int, int]] = []
    start = prev = ordered[0]
    for addr in ordered[1:]:
        if addr == prev + 1:
            prev = addr
            continue
        ranges.append((start, prev - start + 1))
        start = prev = addr
    ranges.append((start, prev - start + 1))
    return ranges


@register_driver("modbus_tcp")
class ModbusDriver(BaseDriver):
    def __init__(self, node) -> None:  # type: ignore[no-untyped-def]
        super().__init__(node)
        self._host: str = self.config.get("host", "127.0.0.1")
        self._port: int = int(self.config.get("port", 502))
        self._unit: int = int(self.config.get("unit", 1))
        self._client: AsyncModbusTcpClient | None = None

    async def connect(self) -> None:
        if self._client is None:
            self._client = AsyncModbusTcpClient(self._host, port=self._port)
        await self._client.connect()
        if not self._client.connected:
            raise ConnectionError(f"No se pudo conectar a Modbus {self._host}:{self._port}")

    async def disconnect(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    async def read_block(self, tags: list[Tag]) -> list[TagValue]:
        if not tags or self._client is None:
            return []

        # Mapear dirección -> tags (varios tags pueden compartir dirección).
        by_addr: dict[int, list[Tag]] = {}
        for tag in tags:
            by_addr.setdefault(int(tag.address), []).append(tag)

        results: list[TagValue] = []
        for start, count in _group_contiguous(list(by_addr)):
            rr = await self._client.read_holding_registers(start, count=count, slave=self._unit)
            if rr.isError():
                for addr in range(start, start + count):
                    for tag in by_addr.get(addr, []):
                        results.append(TagValue(tag_id=tag.id, value=None, quality="bad"))
                continue
            for offset, reg in enumerate(rr.registers):
                for tag in by_addr.get(start + offset, []):
                    results.append(TagValue(tag_id=tag.id, value=reg, quality="good"))
        return results

    async def write_tag(self, tag_id: str, value: Any) -> bool:
        if self._client is None:
            raise RuntimeError("driver no conectado")
        tag = self._tags.get(tag_id)
        if tag is None:
            raise KeyError(f"tag no vinculado a este driver: {tag_id!r}")
        wr = await self._client.write_register(int(tag.address), int(value), slave=self._unit)
        return not wr.isError()
