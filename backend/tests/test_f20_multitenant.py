"""F2.0: aislamiento multi-tenant a nivel de AppState (Runtime/TaskGroup por proyecto).

Dos proyectos concurrentes comparten el TagCache pero corren en Runtimes
independientes: uno lee del simulador (sano) y otro apunta a un puerto muerto
(falla + backoff). El fallo de uno no debe impedir que el otro entregue datos.
"""

import asyncio

import pytest

from app.models.node import DriverNode
from app.models.project import ProjectV1
from app.models.tag import Tag
from app.state import AppState


def _project(pid: str, host: str, port: int) -> ProjectV1:
    return ProjectV1(
        project_id=pid,
        name=pid,
        nodes=[DriverNode(id="d1", driver_type="modbus_tcp",
                          config={"host": host, "port": port, "polling_rate": 0.1})],
        tags=[Tag(id="t0", name="r0", driver_id="d1", address="0", data_type="int")],
    )


async def test_two_projects_isolated(modbus_sim_server):
    host, port = modbus_sim_server
    st = AppState()
    try:
        await st.start_project(_project("A", host, port))   # sano
        await st.start_project(_project("B", host, 1))       # puerto muerto
        await asyncio.sleep(0.5)

        # A entrega datos pese a que B está fallando/reconectando.
        assert st.tag_cache.snapshot("A"), "el proyecto sano debe tener valores"
        assert st.tag_cache.snapshot("B") == []  # B no logra leer
        assert set(st.project_ids()) == {"A", "B"}
    finally:
        await st.stop_all()
        assert st.project_ids() == []  # limpieza correcta
