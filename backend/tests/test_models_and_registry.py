"""Tests de contratos base: unión discriminada de Project (R5), registry, protocol."""

import pytest

from app.drivers.registry import create_driver, registered_drivers
from app.models.node import DriverNode
from app.models.project import load_project
from app.ws.protocol import ClientMessageAdapter, SubscribeMsg, WriteMsg


def test_project_discriminated_union_v1():
    raw = {
        "schema_version": "1",
        "name": "demo",
        "nodes": [{"id": "d1", "type": "driver", "driver_type": "modbus_tcp", "config": {}}],
        "edges": [],
        "tags": [{"id": "t1", "name": "temp", "driver_id": "d1", "address": "40001"}],
    }
    project = load_project(raw)
    assert project.schema_version == "1"
    assert project.tags[0].deadband == 0.0  # default R4
    assert project.tags[0].deadband_mode == "abs"


def test_modbus_driver_is_registered():
    assert "modbus_tcp" in registered_drivers()


def test_factory_creates_registered_driver():
    node = DriverNode(id="d1", driver_type="modbus_tcp", config={})
    driver = create_driver(node)
    assert driver.driver_type == "modbus_tcp"


def test_ws_client_message_discriminator():
    sub = ClientMessageAdapter.validate_json('{"type":"subscribe","tag_ids":["a"]}')
    assert isinstance(sub, SubscribeMsg)
    wr = ClientMessageAdapter.validate_json('{"type":"write","tag_id":"a","value":1}')
    assert isinstance(wr, WriteMsg)
