"""Fixtures compartidas de tests.

`modbus_sim` (R6): arranca el simulador Modbus TCP en un puerto efímero dentro del
mismo event loop y lo detiene al terminar. Reutilizable por cualquier test de
integración del driver.
"""

from __future__ import annotations

import asyncio
import socket

import pytest

from app.drivers import modbus_sim


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def modbus_sim_server():
    """Devuelve (host, port) de un simulador Modbus en marcha."""
    host, port = "127.0.0.1", _free_port()
    server_task = asyncio.create_task(modbus_sim.run(host=host, port=port))
    # Esperar a que el servidor acepte conexiones.
    for _ in range(50):
        await asyncio.sleep(0.05)
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            break
        except OSError:
            continue
    try:
        yield host, port
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
