"""Driver Siemens S7 — polling (F2.3).

`python-snap7` es **síncrono** (wrapper C); toda su I/O se ejecuta en
`asyncio.to_thread` para NO bloquear el event loop (§3.1, riesgo crítico). Es un
driver de **polling**: implementa `read_block` y usa el `run` por defecto.

Direccionamiento S7 absoluto (Rev 11):
  - Bit:    `DB{n}.DBX{byte}.{bit}`   (bool, p. ej. `DB1.DBX0.5`)
  - Byte:   `DB{n}.DBB{byte}`         (1 byte)
  - Word:   `DB{n}.DBW{byte}`         (2 bytes, int)
  - DWord:  `DB{n}.DBD{byte}`         (4 bytes, float/real)
  - Simple: `DB{n}.{byte}`            (ancho según `tag.data_type`)
El `tag.data_type` decide el decode (bool/int/float); la dirección aporta byte y bit.

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

_ADDR_BIT = re.compile(r"^DB(\d+)\.DBX(\d+)\.([0-7])$")
_ADDR_TYPED = re.compile(r"^DB(\d+)\.DB([BWD])(\d+)$")
_ADDR_PLAIN = re.compile(r"^DB(\d+)\.(\d+)$")
_TYPED_SIZE = {"B": 1, "W": 2, "D": 4}
_S7_PDU_BYTES = 222  # margen conservador del PDU S7


def _import_snap7_client():
    """Importa la clase Client de python-snap7 de forma robusta entre versiones
    (1.x expone `snap7.client.Client`; 2.x además `snap7.Client`)."""
    try:
        from snap7.client import Client  # 1.x y 2.x
        return Client
    except ImportError:  # pragma: no cover - depende de la versión instalada
        from snap7 import Client  # type: ignore
        return Client


def _s7_size(data_type: str) -> int:
    return {"bool": 1, "int": 2, "float": 4}.get(data_type, 2)


def _parse_s7(address: str, data_type: str) -> tuple[int, int, int, int] | None:
    """Devuelve `(db, offset_byte, size_bytes, bit)`; None si el formato no es válido."""
    m = _ADDR_BIT.match(address or "")
    if m:
        return int(m.group(1)), int(m.group(2)), 1, int(m.group(3))
    m = _ADDR_TYPED.match(address or "")
    if m:
        return int(m.group(1)), int(m.group(3)), _TYPED_SIZE[m.group(2)], 0
    m = _ADDR_PLAIN.match(address or "")
    if m:
        return int(m.group(1)), int(m.group(2)), _s7_size(data_type), 0
    return None


def _decode_s7(buf: bytes, data_type: str, bit: int = 0) -> Any:
    if data_type == "bool":
        return bool(buf[0] & (1 << bit))
    if data_type == "int":
        return struct.unpack(">h", buf[:2])[0]
    if data_type == "float":
        return struct.unpack(">f", buf[:4])[0]
    return struct.unpack(">h", buf[:2])[0]


def _encode_s7(value: Any, data_type: str) -> bytes:
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
        client_cls = _import_snap7_client()  # perezoso + robusto entre versiones
        if self._client is None:
            self._client = client_cls()
        # connect() lanza excepción si falla (snap7); el Runtime aplicará backoff.
        await asyncio.to_thread(self._client.connect, self._host, self._rack, self._slot)

    async def disconnect(self) -> None:
        if self._client is not None:
            await asyncio.to_thread(self._client.disconnect)

    async def read_block(self, tags: list[Tag]) -> list[TagValue]:
        if not tags or self._client is None:
            return []
        # Parsear cada tag una vez; agrupar por DB.
        per_db: dict[int, list[tuple[Tag, int, int, int]]] = defaultdict(list)
        results: list[TagValue] = []
        for tag in tags:
            parsed = _parse_s7(tag.address, tag.data_type)
            if parsed is None:
                log.warning("Tag %s con dirección S7 inválida %r", tag.id, tag.address)
                results.append(TagValue(tag_id=tag.id, value=None, quality="bad"))
                continue
            db, off, size, bit = parsed
            per_db[db].append((tag, off, size, bit))

        for db, recs in per_db.items():
            spans = [(tag, off, size) for (tag, off, size, _bit) in recs]
            for gstart, gcount in group_contiguous_spans(spans, max_units=_S7_PDU_BYTES):
                try:
                    buf = await asyncio.to_thread(self._client.db_read, db, gstart, gcount)
                except Exception as exc:  # noqa: BLE001 - marca bad; el runtime hará backoff
                    log.warning("Fallo db_read DB%d @%d: %s", db, gstart, exc)
                    buf = None
                for tag, off, size, bit in recs:
                    if not (gstart <= off and off + size <= gstart + gcount):
                        continue
                    if buf is None:
                        results.append(TagValue(tag_id=tag.id, value=None, quality="bad"))
                        continue
                    chunk = bytes(buf[off - gstart : off - gstart + size])
                    results.append(
                        TagValue(tag_id=tag.id, value=_decode_s7(chunk, tag.data_type, bit),
                                 quality="good")
                    )
        return results

    async def write_tag(self, tag_id: str, value: Any) -> bool:
        if self._client is None:
            raise RuntimeError("driver S7 no conectado")
        tag = self._tags.get(tag_id)
        parsed = _parse_s7(tag.address, tag.data_type) if tag is not None else None
        if parsed is None:
            raise KeyError(f"tag S7 con dirección inválida: {tag_id!r}")
        db, off, size, bit = parsed
        if tag.data_type == "bool":
            # Read-modify-write del byte para no pisar los otros bits.
            cur = await asyncio.to_thread(self._client.db_read, db, off, 1)
            b = cur[0]
            b = (b | (1 << bit)) if value else (b & ~(1 << bit))
            await asyncio.to_thread(self._client.db_write, db, off, bytearray([b]))
        else:
            await asyncio.to_thread(
                self._client.db_write, db, off, bytearray(_encode_s7(value, tag.data_type))
            )
        return True
