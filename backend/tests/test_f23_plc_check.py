"""F2.3: preflight de conectividad — construcción de driver desde args (sin conectar)."""

import argparse

import pytest

from app.drivers.modbus_driver import ModbusDriver
from app.drivers.s7_driver import S7Driver
from app.tools.plc_check import build_driver


def _args(**kw) -> argparse.Namespace:
    base = dict(type=None, address="0", data_type="int", host=None, port=None, unit=None,
                rack=None, slot=None, url=None, topic=None, lwt_topic=None,
                device_topic_index=None, seconds=5.0)
    base.update(kw)
    return argparse.Namespace(**base)


def test_build_modbus_driver_from_args():
    d, tag = build_driver(_args(type="modbus_tcp", host="10.0.0.1", port=502, address="5"))
    assert isinstance(d, ModbusDriver)
    assert d._host == "10.0.0.1" and d._port == 502
    assert tag.address == "5" and tag.id == "probe"


def test_build_s7_driver_from_args():
    d, tag = build_driver(_args(type="s7", host="10.0.0.2", rack=0, slot=1,
                                address="DB1.0", data_type="float"))
    assert isinstance(d, S7Driver)
    assert d._host == "10.0.0.2" and d._rack == 0 and d._slot == 1
    assert tag.data_type == "float"
