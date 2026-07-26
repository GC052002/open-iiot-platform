"""Tests de integración del driver Modbus contra el simulador (R6)."""

import pytest

from app.drivers.modbus_driver import ModbusDriver, _group_contiguous
from app.models.node import DriverNode
from app.models.tag import Tag


def test_group_contiguous_merges_runs():
    assert _group_contiguous([0, 1, 2, 5, 6, 9]) == [(0, 3), (5, 2), (9, 1)]
    assert _group_contiguous([]) == []
    assert _group_contiguous([3]) == [(3, 1)]


def _driver(host: str, port: int, tags: list[Tag]) -> ModbusDriver:
    node = DriverNode(id="d1", driver_type="modbus_tcp", config={"host": host, "port": port})
    drv = ModbusDriver(node)
    drv.bind_tags(tags)
    return drv


async def test_connect_and_read_block(modbus_sim_server):
    host, port = modbus_sim_server
    tags = [
        Tag(id="t0", name="r0", driver_id="d1", address="0"),
        Tag(id="t1", name="r1", driver_id="d1", address="1"),
        Tag(id="t5", name="r5", driver_id="d1", address="5"),
    ]
    drv = _driver(host, port, tags)
    await drv.connect()
    try:
        values = await drv.read_block(tags)
        by_id = {v.tag_id: v for v in values}
        assert set(by_id) == {"t0", "t1", "t5"}
        assert all(v.quality == "good" for v in values)
        assert all(isinstance(v.value, int) for v in values)
    finally:
        await drv.disconnect()


async def test_write_then_read_roundtrip(modbus_sim_server):
    host, port = modbus_sim_server
    # Dirección en la región estática del simulador (>=16) para evitar el updater.
    tag = Tag(id="tw", name="rw", driver_id="d1", address="20")
    drv = _driver(host, port, [tag])
    await drv.connect()
    try:
        assert await drv.write_tag("tw", 4242) is True
        values = await drv.read_block([tag])
        assert values[0].value == 4242
    finally:
        await drv.disconnect()
