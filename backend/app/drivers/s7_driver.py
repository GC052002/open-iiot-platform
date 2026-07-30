"""Driver Siemens S7 — polling (F2.3).

`python-snap7` es **síncrono** (wrapper C); toda su I/O se ejecuta en
`asyncio.to_thread` para NO bloquear el event loop (§3.1, riesgo crítico). Es un
driver de **polling**: implementa `read_block` y usa el `run` por defecto.

Direccionamiento: `tag.address = "DB{n}.{offset}"` (offset en bytes), p. ej.
`"DB1.0"`, `"DB1.4"`. El ancho y el tipo salen de `tag.data_type`:
  - bool  -> 1 byte (bit 0)      - int   -> 2 bytes (S7 INT, big-endian)
  - float -> 4 bytes (S7 REAL)   - (string diferido)

Lectura por bloques (D-M4): agrupa por `DB` y rangos de bytes contiguos reutilizando
`blockutil.group_contiguous_spans`, y decodifica cada tag desde el buffer del bloque.

Config del nodo: `host`, `rack` (def. 0), `slot` (def. 1).
"""

from __future__ import annotations

import asyncio
import logging
import re
import struct
from collections import defaultdict
from typing import Any

from app.drivers.base import BaseDriver
from app.drivers.blockutil import group_contiguous_spans
from app.drivers.registry import register_driver
from app.models.tag import Tag, TagValue

log = logging.getLogger("iiot.driver.s7")

_ADDR_RE = re.compile(r"^DB(\d+)\.(\d+)$")
_S7_PDU_BYTES = 222  # margen conservador del PDU S7


def _parse_addr(address: str) -> tuple[int, int] | None:
    """'DB1.4' -> (db=1, start_byte=4); None si el formato no es válido."""
    m = _ADDR_RE.match(address or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _s7_size(data_type: str) -> int:
    return {"bool": 1, "int": 2, "float": 4}.get(data_type, 2)


def _decode_s7(buf: bytes, data_type: str) -> Any:
    if data_type == "bool":
        return bool(buf[0] & 0x01)
    if data_type == "int":
        return struct.unpack(">h", buf[:2])[0]
    if data_type == "float":
        return struct.unpack(">f", buf[:4])[0]
    return struct.unpack(">h", buf[:2])[0]


def _encode_s7(value: Any, data_type: str) -> bytes:
    if data_type == "bool":
        return bytes([1 if value else 0])
    if data_type == "int":
        return struct.pack(">h", int(value))
    if data_type == "float":
        return struct.pack(">f", float(value))
    return struct.pack(">h", int(value))


@register_driver("s7")
class S7Driver(BaseDriver):
    def __init__(self, node) -> None:  # type: ignore[no-untyped-def]
        super().__init__(node)
        self._host: str = self.config.get("host", "127.0.0.1")
        self._rack: int = int(self.config.get("rack", 0))
        self._slot: int = int(self.config.get("slot", 1))
        self._client: Any = None

    async def connect(self) -> None:
        import snap7  # perezoso: solo si se usa el driver

        if self._client is None:
            self._client = snap7.client.Client()
        await asyncio.to_thread(self._client.connect, self._host, self._rack, self._slot)
        if not await asyncio.to_thread(self._client.get_connected):
            raise ConnectionError(f"No se pudo conectar a S7 {self._host} r{self._rack}/s{self._slot}")

    async def disconnect(self) -> None:
        if self._client is not None:
            await asyncio.to_thread(self._client.disconnect)

    async def read_block(self, tags: list[Tag]) -> list[TagValue]:
        if not tags or self._client is None:
            return []
        # Agrupar por DB; dentro de cada DB, por rangos de bytes contiguos.
        per_db: dict[int, list[tuple[Tag, int, int]]] = defaultdict(list)
        results: list[TagValue] = []
        for tag in tags:
            parsed = _parse_addr(tag.address)
            if parsed is None:
                log.warning("Tag %s con dirección S7 inválida %r", tag.id, tag.address)
                results.append(TagValue(tag_id=tag.id, value=None, quality="bad"))
                continue
            db, start = parsed
            per_db[db].append((tag, start, _s7_size(tag.data_type)))

        for db, spans in per_db.items():
            for gstart, gcount in group_contiguous_spans(spans, max_units=_S7_PDU_BYTES):
                try:
                    buf = await asyncio.to_thread(self._client.db_read, db, gstart, gcount)
                except Exception as exc:  # noqa: BLE001 - marca bad y sigue; el runtime hará backoff
                    log.warning("Fallo db_read DB%d @%d: %s", db, gstart, exc)
                    buf = None
                for tag, start, size in spans:
                    if not (gstart <= start and start + size <= gstart + gcount):
                        continue
                    if buf is None:
                        results.append(TagValue(tag_id=tag.id, value=None, quality="bad"))
                        continue
                    chunk = bytes(buf[start - gstart : start - gstart + size])
                    results.append(
                        TagValue(tag_id=tag.id, value=_decode_s7(chunk, tag.data_type), quality="good")
                    )
        return results

    async def write_tag(self, tag_id: str, value: Any) -> bool:
        if self._client is None:
            raise RuntimeError("driver S7 no conectado")
        tag = self._tags.get(tag_id)
        parsed = _parse_addr(tag.address) if tag is not None else None
        if parsed is None:
            raise KeyError(f"tag S7 con dirección inválida: {tag_id!r}")
        db, start = parsed
        await asyncio.to_thread(self._client.db_write, db, start, bytearray(_encode_s7(value, tag.data_type)))
        return True
