"""Aplicación FastAPI + lifespan del motor (ARCHITECTURE §5).

Multi-tenant (Rev 7): carga N proyectos (POST /projects), cada uno con su Runtime;
el WebSocket hace streaming por `(project_id, tag_id)` con el contrato de
`ws/protocol.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import pathlib
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse

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


_DASHBOARD = pathlib.Path(__file__).parent / "static" / "dashboard.html"


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    """Monitor web en vivo (autocontenido, sin CDNs). Para el frontend completo, F3."""
    return _DASHBOARD.read_text(encoding="utf-8")


@app.get("/health")
async def health() -> dict[str, Any]:
    # R-M2 + multi-tenant: estado real por proyecto.
    per_project = state.health()
    ok = all(h["healthy"] for h in per_project.values())
    return {"status": "ok" if ok else "degraded", "projects": per_project}


@app.get("/health/drivers")
async def health_drivers() -> dict[str, Any]:
    """Health granular por proyecto/driver (§10.5, F2.4c)."""
    return await state.driver_health()


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint() -> str:
    """Métricas en formato Prometheus (F2.4c). Abierto para el scraper."""
    from app.observability.metrics import metrics

    return metrics.render()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    # Auth en el handshake (Rev 12): el rol se cachea en el cliente; los WriteMsg ya no
    # descifran el token en el hot path. Token vía query param `?token=...`.
    from app.security.auth import resolve_user

    user = resolve_user(ws.query_params.get("token"))
    if user is None:
        await ws.close(code=1008)  # policy violation
        return
    client = await state.manager.connect(ws)
    client.role, client.username = user.role, user.username
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
                ok, detail = await _handle_write(msg, client)
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


async def _handle_write(msg: WriteMsg, client) -> tuple[bool, str | None]:  # noqa: ANN001
    # RBAC contra el rol cacheado del handshake (Rev 12) + audit log (§3.6).
    from app.security.rbac import can

    if not can(client.role, "tag:write"):
        return False, "permiso denegado: tag:write"

    prev = state.tag_cache.get(msg.project_id, msg.tag_id)
    old_value = prev.value if prev else None
    try:
        ok = await state.write_tag(msg.project_id, msg.tag_id, msg.value)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    await state.audit("tag:write", username=client.username, project_id=msg.project_id,
                      detail=msg.tag_id, old_value=old_value, new_value=msg.value)
    return ok, None
