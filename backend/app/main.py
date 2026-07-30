"""Aplicación FastAPI + lifespan del motor (ARCHITECTURE §5).

Multi-tenant (Rev 7): carga N proyectos (POST /projects), cada uno con su Runtime;
el WebSocket hace streaming por `(project_id, tag_id)` con el contrato de
`ws/protocol.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from typing import Any

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
    await state.startup()   # historiador + TagBuffer (F2.1)
    yield
    await state.shutdown()


app = FastAPI(title="IIoT Platform Backend", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, Any]:
    # R-M2 + multi-tenant: estado real por proyecto.
    per_project = state.health()
    ok = all(h["healthy"] for h in per_project.values())
    return {"status": "ok" if ok else "degraded", "projects": per_project}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    client = await state.manager.connect(ws)
    sender = asyncio.create_task(state.manager.sender_loop(client))
    try:
        async for raw in ws.iter_text():
            msg = ClientMessageAdapter.validate_json(raw)
            if isinstance(msg, SubscribeMsg):
                state.manager.subscribe(client, msg.project_id, msg.tag_ids)
                snap = state.tag_cache.snapshot(msg.project_id, msg.tag_ids)
                if snap:
                    await ws.send_text(TagUpdateMsg(values=snap).model_dump_json())
            elif isinstance(msg, UnsubscribeMsg):
                state.manager.unsubscribe(client, msg.project_id, msg.tag_ids)
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
    # TODO(F2.4): aplicar RBAC/ABAC + audit log antes de ejecutar el Command (§3.6).
    try:
        ok = await state.write_tag(msg.project_id, msg.tag_id, msg.value)
        return ok, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
