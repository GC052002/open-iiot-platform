"""Tests de las correcciones de la Rev 5 (revisión externa Gemini de F1)."""

import asyncio
import struct

import pytest

from app.drivers.modbus_driver import (
    ModbusDriver,
    _decode,
    _group_contiguous_spans,
    _register_count,
)
from app.engine.runtime import Runtime
from app.models.node import DriverNode
from app.models.project import ProjectV1
from app.models.tag import Tag


# --- D-M3: decodificación por data_type ------------------------------------

def test_register_count_float_is_two():
    assert _register_count("float") == 2
    assert _register_count("int") == 1
    assert _register_count("bool") == 1


def test_decode_float_big_endian():
    packed = struct.unpack(">HH", struct.pack(">f", 3.14))
    tag = Tag(id="f", name="f", driver_id="d1", address="0", data_type="float")
    assert abs(_decode(list(packed), tag) - 3.14) < 1e-4


def test_decode_bool_and_int():
    assert _decode([1], Tag(id="b", name="b", driver_id="d1", address="0", data_type="bool")) is True
    assert _decode([0], Tag(id="b", name="b", driver_id="d1", address="0", data_type="bool")) is False
    assert _decode([42], Tag(id="i", name="i", driver_id="d1", address="0", data_type="int")) == 42


# --- BLOCKER 1 (Rev 6): agrupación por spans, límite PDU, no partir floats --

def _span(addr: int, width: int) -> tuple:
    t = Tag(id=f"t{addr}", name="x", driver_id="d1", address=str(addr))
    return (t, addr, width)


def test_span_grouping_merges_and_respects_gap():
    spans = [_span(0, 1), _span(1, 1), _span(5, 1)]
    assert _group_contiguous_spans(spans) == [(0, 2), (5, 1)]


def test_span_grouping_does_not_split_float():
    # float en dirección 3 ocupa 3,4. No debe partirse aunque el límite sea pequeño.
    spans = [_span(0, 1), _span(3, 2)]
    ranges = _group_contiguous_spans(spans, max_registers=3)
    # (0..0) cabe; (3..4) es un bloque entero, nunca (3,1)+(4,1).
    assert (3, 2) in ranges


def test_span_grouping_respects_pdu_limit():
    spans = [_span(i, 1) for i in range(0, 200)]
    ranges = _group_contiguous_spans(spans, max_registers=120)
    assert all(count <= 120 for _start, count in ranges)
    assert sum(count for _s, count in ranges) == 200  # cobertura completa


# --- D-m2: dirección no numérica no rompe la lectura -----------------------

async def test_read_block_bad_address_is_marked_bad(modbus_sim_server):
    host, port = modbus_sim_server
    node = DriverNode(id="d1", driver_type="modbus_tcp", config={"host": host, "port": port})
    drv = ModbusDriver(node)
    good = Tag(id="ok", name="ok", driver_id="d1", address="0")
    bad = Tag(id="bad", name="bad", driver_id="d1", address="DB1.DBD0")  # no numérica
    drv.bind_tags([good, bad])
    await drv.connect()
    try:
        by_id = {v.tag_id: v for v in await drv.read_block([good, bad])}
        assert by_id["ok"].quality == "good"
        assert by_id["bad"].quality == "bad" and by_id["bad"].value is None
    finally:
        await drv.disconnect()


# --- R-H1 / R-M1: shutdown determinista con stop() -------------------------

async def test_runtime_stop_is_deterministic():
    """stop() cancela los scan loops; run() retorna sin colgarse aunque el poll
    sea largo (R-H1 + R-M1)."""
    project = ProjectV1(
        name="x",
        nodes=[DriverNode(id="d1", driver_type="modbus_tcp",
                          config={"host": "127.0.0.1", "port": 1, "polling_rate": 100})],
        tags=[Tag(id="t", name="t", driver_id="d1", address="0")],
    )
    runtime = Runtime(project)
    task = asyncio.create_task(runtime.run())
    await asyncio.sleep(0.2)  # dejar que entre en el loop (fallará al conectar al puerto 1)
    runtime.stop()
    # Debe terminar rápido, muy por debajo del polling_rate de 100s.
    await asyncio.wait_for(task, timeout=5.0)
