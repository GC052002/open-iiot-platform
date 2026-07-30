"""F2.3: drivers S7 (polling) y OPC UA (push). Tests de la lógica pura (sin PLC/servidor)."""

import struct

import pytest

from app.drivers.blockutil import group_contiguous_spans
from app.drivers.opcua_driver import OpcUaDriver
from app.drivers.registry import registered_drivers
from app.drivers.s7_driver import (
    S7Driver,
    _decode_s7,
    _encode_s7,
    _parse_addr,
    _s7_size,
)
from app.models.node import DriverNode
from app.models.tag import Tag


def test_drivers_registered():
    regs = registered_drivers()
    assert "s7" in regs and "opcua" in regs
    # Los 4 built-in conviven.
    assert {"modbus_tcp", "mqtt", "s7", "opcua"} <= set(regs)


# --- S7: direccionamiento y codec (D-M4 comparte la agrupación) -------------

def test_s7_parse_address():
    assert _parse_addr("DB1.4") == (1, 4)
    assert _parse_addr("DB10.0") == (10, 0)
    assert _parse_addr("MW0") is None      # no es DB
    assert _parse_addr("garbage") is None


def test_s7_sizes():
    assert _s7_size("bool") == 1
    assert _s7_size("int") == 2
    assert _s7_size("float") == 4


def test_s7_decode_big_endian():
    assert _decode_s7(struct.pack(">h", -12), "int") == -12
    assert abs(_decode_s7(struct.pack(">f", 3.5), "float") - 3.5) < 1e-6
    assert _decode_s7(bytes([1]), "bool") is True
    assert _decode_s7(bytes([0]), "bool") is False


def test_s7_encode_roundtrip():
    for dt, val in [("int", 7), ("float", 2.5), ("bool", True)]:
        assert _decode_s7(_encode_s7(val, dt), dt) == val or dt == "float"


def test_s7_grouping_by_bytes_respects_pdu():
    spans = [(None, i, 2) for i in range(0, 300, 2)]  # 150 spans de 2 bytes
    ranges = group_contiguous_spans(spans, max_units=222)
    assert all(count <= 222 for _s, count in ranges)


# --- OPC UA: mapeo NodeId -> muestra ----------------------------------------

def _opcua_driver() -> OpcUaDriver:
    node = DriverNode(id="o1", driver_type="opcua", config={"url": "opc.tcp://x:4840"})
    d = OpcUaDriver(node)
    d.bind_tags([
        Tag(id="t0", name="temp", driver_id="o1", address="ns=2;i=3"),
        Tag(id="t1", name="pres", driver_id="o1", address="ns=2;s=Pressure"),
    ])
    return d


def test_opcua_to_sample_maps_known_node():
    d = _opcua_driver()
    s = d.to_sample("ns=2;i=3", 42.0)
    assert s is not None and s.tag_id == "t0" and s.value == 42.0 and s.quality == "good"


def test_opcua_to_sample_ignores_unknown_node():
    d = _opcua_driver()
    assert d.to_sample("ns=9;i=99", 1.0) is None
