"""Fixtures compartidas de tests.

`modbus_sim` (R6): arranca el simulador Modbus TCP en un puerto efímero dentro del
mismo event loop y lo detiene al terminar. Reutilizable por cualquier test de
integración del driver.
"""

from __future__ import annotations

import asyncio
import os
import socket

# Los tests corren en modo dev: permite acceso anónimo y clave Fernet efímera
# (fail-closed en producción, Rev 12). Debe fijarse antes de importar la app.
os.environ.setdefault("IIOT_ALLOW_ANONYMOUS", "true")

import pytest

from app.drivers import modbus_sim


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def config_env():
    """Entorno F4 aislado: cablea el `state` global con un `ConfigRepository` en memoria
    + `SecretStore` + `DbUserStore`, y lo restaura al terminar.

    Devuelve el `SQLiteConfigRepository` para sembrar datos directamente en los tests.
    """
    from app.security import context
    from app.security.crypto import CredentialCipher
    from app.security.rbac import UserStore
    from app.security.secrets import SecretStore
    from app.security.user_store import DbUserStore
    from app.state import state
    from app.storage import SQLiteConfigRepository

    context.configure(key=CredentialCipher.generate_key())
    cfg = SQLiteConfigRepository(":memory:")
    await cfg.init()
    state.config_repo = cfg
    state.secret_store = SecretStore(cfg, context.cipher)
    store = DbUserStore(cfg)
    await store.load(bootstrap=False)
    context.set_user_store(store)
    try:
        yield cfg
    finally:
        await state.stop_all()
        state.config_repo = None
        state.secret_store = None
        context.set_user_store(UserStore.from_env(""))
        context.set_secret_store(None)
        await cfg.close()


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
