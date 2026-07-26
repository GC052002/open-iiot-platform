"""Aplicación FastAPI + lifespan del motor (ARCHITECTURE §5).

F1 mínimo demostrable: cargar un proyecto JSON (POST /projects), arrancar el
Runtime, y exponer un endpoint WebSocket que hace streaming de tags con el
contrato de `ws/protocol.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

import app.drivers  # noqa: F401 - efecto: registra los drivers built-in
from app.api import router as api_router
from app.state import state
from app.ws.protocol import (
    AckMsg,
    ClientMessageAdapter,
    SubscribeMsg,
    TagUpdateMsg,
    UnsubscribeMsg,
    WriteMsg,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("iiot.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # F1: sin proyecto al arranque; se carga vía POST /projects.
    yield
    await state.stop_project()


app = FastAPI(title="IIoT Platform Backend", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    client = await state.manager.connect(ws)
    sender = asyncio.create_task(state.manager.sender_loop(client))
    try:
        async for raw in ws.iter_text():
            msg = ClientMessageAdapter.validate_json(raw)
            if isinstance(msg, SubscribeMsg):
                state.manager.subscribe(client, msg.tag_ids)
                if state.runtime is not None:
                    snap = state.runtime.tag_cache.snapshot(msg.tag_ids)
                    if snap:
                        await ws.send_text(TagUpdateMsg(values=snap).model_dump_json())
            elif isinstance(msg, UnsubscribeMsg):
                state.manager.unsubscribe(client, msg.tag_ids)
            elif isinstance(msg, WriteMsg):
                ok, detail = await _handle_write(msg)
                await ws.send_text(
                    AckMsg(request_id=msg.request_id, ok=ok, detail=detail).model_dump_json()
                )
    except WebSocketDisconnect:
        pass
    finally:
        state.manager.disconnect(client)
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender


async def _handle_write(msg: WriteMsg) -> tuple[bool, str | None]:
    # TODO(F2): aplicar RBAC/ABAC + audit log antes de ejecutar el Command (§3.6).
    if state.runtime is None:
        return False, "runtime no iniciado"
    try:
        ok = await state.runtime.write_tag(msg.tag_id, msg.value)
        return ok, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
