"""F2.4c: métricas Prometheus y health granular."""

import httpx
import pytest

from app.observability.metrics import Metrics


def test_counter_and_gauge_render():
    m = Metrics()
    m.inc("iiot_driver_reads_total", {"driver": "modbus_tcp", "node": "d1"})
    m.inc("iiot_driver_reads_total", {"driver": "modbus_tcp", "node": "d1"})
    m.set_gauge("iiot_ws_connected_clients", value=3)
    out = m.render()
    assert "# TYPE iiot_driver_reads_total counter" in out
    assert 'iiot_driver_reads_total{driver="modbus_tcp",node="d1"} 2.0' in out
    assert "# TYPE iiot_ws_connected_clients gauge" in out
    assert "iiot_ws_connected_clients 3.0" in out


def test_observe_is_last_value():
    m = Metrics()
    m.observe("iiot_driver_read_latency_ms", {"node": "d1"}, 10)
    m.observe("iiot_driver_read_latency_ms", {"node": "d1"}, 25)
    assert "iiot_driver_read_latency_ms{node=\"d1\"} 25.0" in m.render()


def test_dynamic_gauge_source():
    m = Metrics()
    m.register_source(lambda: [("iiot_active_alarms", {}, 4)])
    assert "iiot_active_alarms 4.0" in m.render()


def test_source_failure_does_not_break_scrape():
    m = Metrics()
    m.inc("ok_total")

    def _bad():
        raise RuntimeError("boom")

    m.register_source(_bad)
    assert "ok_total" in m.render()  # una fuente rota no rompe el render


async def test_metrics_endpoint_served():
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/metrics")
        assert r.status_code == 200
        assert "text/plain" in r.headers["content-type"]
