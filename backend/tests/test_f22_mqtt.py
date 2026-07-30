"""F2.2: driver MQTT (rama 2, ingesta híbrida). Tests del parsing (puro, sin broker)."""

from datetime import datetime, timezone

import pytest

from app.drivers.mqtt_driver import MqttDriver, _parse_ts
from app.drivers.registry import registered_drivers
from app.models.node import DriverNode
from app.models.tag import Tag


def _driver(lwt: str | None = None) -> MqttDriver:
    node = DriverNode(id="m1", driver_type="mqtt",
                      config={"topic": "plantA/data", "lwt_topic": lwt})
    d = MqttDriver(node)
    d.bind_tags([
        Tag(id="t0", name="temp", driver_id="m1", address="temperature"),
        Tag(id="t1", name="pres", driver_id="m1", address="pressure"),
    ])
    return d


def test_mqtt_is_registered():
    assert "mqtt" in registered_drivers()


def test_parse_maps_values_by_address():
    d = _driver()
    samples = d.parse("plantA/data", b'{"values": {"temperature": 25.3, "pressure": 1.2, "x": 9}}')
    by_id = {s.tag_id: s for s in samples}
    assert set(by_id) == {"t0", "t1"}          # "x" no está mapeado -> ignorado
    assert by_id["t0"].value == 25.3
    assert all(s.quality == "good" for s in samples)


def test_parse_flat_payload_without_values_key():
    d = _driver()
    samples = d.parse("plantA/data", b'{"temperature": 20.0}')
    assert len(samples) == 1 and samples[0].tag_id == "t0"


def test_parse_respects_edge_timestamp():
    d = _driver()
    samples = d.parse("plantA/data", b'{"ts": "2026-07-30T12:00:00Z", "values": {"temperature": 1.0}}')
    assert samples[0].ts == datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def test_parse_without_ts_uses_now():
    d = _driver()
    samples = d.parse("plantA/data", b'{"temperature": 1.0}')
    assert samples[0].ts is not None  # default_factory = utcnow


def test_lwt_marks_all_tags_bad():
    d = _driver(lwt="plantA/status")
    samples = d.parse("plantA/status", b"offline")
    assert len(samples) == 2
    assert all(s.quality == "bad" and s.value is None for s in samples)


def test_non_json_payload_is_ignored():
    d = _driver()
    assert d.parse("plantA/data", b"not-json") == []


def test_parse_ts_helper():
    assert _parse_ts("2026-07-30T12:00:00Z") == datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    assert _parse_ts(None) is None
    assert _parse_ts("garbage") is None
