"""Test end-to-end de F1: POST /projects contra el simulador -> GET /tags con valores.

Valida el camino completo: API -> Runtime -> ScanScheduler -> ModbusDriver ->
TagCache. Es el hito demostrable de la Fase 1 (ROADMAP).
"""

import asyncio

import httpx
import pytest

from app.main import app
from app.state import state


async def test_load_project_and_read_tags(modbus_sim_server):
    host, port = modbus_sim_server
    project = {
        "schema_version": "1",
        "name": "demo",
        "nodes": [
            {
                "id": "d1",
                "type": "driver",
                "driver_type": "modbus_tcp",
                "config": {"host": host, "port": port, "polling_rate": 0.1},
            }
        ],
        "edges": [],
        "tags": [
            {"id": "t0", "name": "reg0", "driver_id": "d1", "address": "0"},
            {"id": "t1", "name": "reg1", "driver_id": "d1", "address": "1"},
        ],
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            resp = await client.post("/projects", json=project)
            assert resp.status_code == 200
            assert resp.json()["tags"] == 2

            # Dar tiempo a un par de ciclos de scan.
            await asyncio.sleep(0.4)

            tags = (await client.get("/tags")).json()
            by_id = {t["id"]: t for t in tags}
            assert set(by_id) == {"t0", "t1"}
            assert by_id["t0"]["quality"] == "good"
            assert by_id["t0"]["value"] is not None
        finally:
            await state.stop_project()
