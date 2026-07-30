"""Driver Modbus TCP — driver de referencia de la Fase 1.

Implementa `BaseDriver` con `pymodbus` (async nativo en 3.x, por lo que NO requiere
`to_thread`; el patrón Adapter cubre igualmente los drivers síncronos de F2, §3.1).

Lectura por bloques (§3.2): agrupa los tags por rangos de registros contiguos y
hace una lectura Modbus por bloque, luego rebana el resultado. El scheduler entrega
una lista genérica de `Tag`; aquí es donde se traduce qué significa "contiguo".

Convención de direcciones: `tag.address` = offset entero del Holding Register.
Config del nodo (`DriverNode.config`): `host`, `port` (def. 502), `unit` (def. 1),
`timeout` (def. 3.0), `retries` (def. 1).

Decodificación (D-M3): `read_block` interpreta los registros según `tag.data_type`
(bool/int en 1 registro; float en 2, big-endian). Un `float` ocupa 2 registros
consecutivos a partir de su dirección base.
"""

from __future__ import annotations

import logging
import struct
from typing import Any

from pymodbus.client import AsyncModbusTcpClient

from app.drivers.base import BaseDriver
from app.drivers.registry import register_driver
from app.models.tag import Tag, TagValue

log = logging.getLogger("iiot.driver.modbus")


def _register_count(data_type: str) -> int:
    """Nº de registros de 16 bits que ocupa un tipo. float32 = 2; resto = 1."""
    return 2 if data_type == "float" else 1


def _decode(registers: list[int], tag: Tag) -> Any:
    """Interpreta registros crudos según `tag.data_type` (D-M3)."""
    if tag.data_type == "bool":
        return bool(registers[0] & 1)
    if tag.data_type == "float":
        raw = (registers[0] << 16) | registers[1]
        return struct.unpack(">f", struct.pack(">I", raw))[0]
    if tag.data_type == "string":
        # TODO(F2): longitud configurable; por ahora 1 registro = 2 chars.
        return "".join(chr(r >> 8) + chr(r & 0xFF) for r in registers).rstrip("\x00")
    return registers[0]  # int (y por defecto)


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


# D-M4: la agrupación por bloques (límite PDU, sin partir spans) es compartida por
# los drivers de polling. Se reexporta con el nombre previo para no romper tests.
from app.drivers.blockutil import group_contiguous_spans as _group_contiguous_spans  # noqa: E402


@register_driver("modbus_tcp")
class ModbusDriver(BaseDriver):
    def __init__(self, node) -> None:  # type: ignore[no-untyped-def]
        super().__init__(node)
        self._host: str = self.config.get("host", "127.0.0.1")
        self._port: int = int(self.config.get("port", 502))
        self._unit: int = int(self.config.get("unit", 1))
        self._timeout: float = float(self.config.get("timeout", 3.0))
        self._retries: int = int(self.config.get("retries", 1))
        self._client: AsyncModbusTcpClient | None = None

    async def connect(self) -> None:
        if self._client is None:
            # D-H2: timeout/retries acotados para que un PLC en black-hole levante
            # ConnectionException en ~timeout s (y el runtime aplique backoff), en vez
            # de congelar el scan loop hasta el timeout TCP del SO.
            self._client = AsyncModbusTcpClient(
                self._host,
                port=self._port,
                timeout=self._timeout,
                retries=self._retries,
                reconnect_delay=0.5,
                reconnect_delay_max=5.0,
            )
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

        # 1) Resolver dirección base y ancho (registros) de cada tag; reunir todas
        #    las direcciones necesarias. Un float ocupa 2 registros (D-M3).
        spans: list[tuple[Tag, int, int]] = []  # (tag, start, width)
        results: list[TagValue] = []
        for tag in tags:
            try:
                start = int(tag.address)  # D-m2: dirección no numérica -> bad, no crash
            except (ValueError, TypeError):
                log.warning("Tag %s con dirección no numérica %r en Modbus", tag.id, tag.address)
                results.append(TagValue(tag_id=tag.id, value=None, quality="bad"))
                continue
            spans.append((tag, start, _register_count(tag.data_type)))

        # 2) Leer por bloques que respetan el límite de PDU y no parten spans (BLOCKER 1).
        registers: dict[int, int] = {}
        for gstart, gcount in _group_contiguous_spans(spans):
            rr = await self._client.read_holding_registers(gstart, count=gcount, slave=self._unit)
            if rr.isError():
                continue  # las direcciones ausentes se marcan bad abajo
            for offset, reg in enumerate(rr.registers):
                registers[gstart + offset] = reg

        # 3) Decodificar cada tag desde sus registros.
        for tag, start, width in spans:
            regs = [registers.get(a) for a in range(start, start + width)]
            if any(r is None for r in regs):
                results.append(TagValue(tag_id=tag.id, value=None, quality="bad"))
            else:
                results.append(TagValue(tag_id=tag.id, value=_decode(regs, tag), quality="good"))
        return results

    async def write_tag(self, tag_id: str, value: Any) -> bool:
        if self._client is None:
            raise RuntimeError("driver no conectado")
        tag = self._tags.get(tag_id)
        if tag is None:
            raise KeyError(f"tag no vinculado a este driver: {tag_id!r}")
        wr = await self._client.write_register(int(tag.address), int(value), slave=self._unit)
        return not wr.isError()
