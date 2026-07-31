"""Contrato de mensajes WebSocket entre backend y frontend.

R1 (ARCHITECTURE §3.10): este contrato es un **entregable de la Fase 1**, no de la
Fase 3. El frontend (F3) consume estos esquemas estables sin renegociarlos, de modo
que el `ws/manager.py` no haya que reescribirlo al construir el canvas.

Codificación en v1: **JSON** (no msgpack/protobuf — §9, matiz de la Rev 2). El
campo `type` discrimina el mensaje en ambas direcciones.

Direcciones:
- Cliente -> Servidor: SubscribeMsg, UnsubscribeMsg, WriteMsg.
- Servidor -> Cliente: TagUpdateMsg, AckMsg, OverflowMsg, ErrorMsg.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

from app.models.tag import TagValue

# ---------------------------------------------------------------------------
# Cliente -> Servidor
# ---------------------------------------------------------------------------


class SubscribeMsg(BaseModel):
    type: Literal["subscribe"] = "subscribe"
    project_id: str = "default"  # Rev 7: scoping multi-tenant
    tag_ids: list[str]


class UnsubscribeMsg(BaseModel):
    type: Literal["unsubscribe"] = "unsubscribe"
    project_id: str = "default"
    tag_ids: list[str]


class WriteMsg(BaseModel):
    """Solicitud de escritura a un tag. La autorización (RBAC/ABAC) y el audit log
    se aplican en el backend antes de encolar el Command (§3.6)."""

    type: Literal["write"] = "write"
    project_id: str = "default"
    tag_id: str
    value: Any
    request_id: str | None = None
    token: str | None = None  # F2.4b: token de sesión para autorizar la escritura


ClientMessage = Annotated[
    Union[SubscribeMsg, UnsubscribeMsg, WriteMsg],
    Field(discriminator="type"),
]
ClientMessageAdapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


# ---------------------------------------------------------------------------
# Servidor -> Cliente
# ---------------------------------------------------------------------------


class TagUpdateMsg(BaseModel):
    type: Literal["tag_update"] = "tag_update"
    values: list[TagValue]


class AckMsg(BaseModel):
    """Confirmación de una operación (p. ej. una escritura)."""

    type: Literal["ack"] = "ack"
    request_id: str | None = None
    ok: bool = True
    detail: str | None = None


class OverflowMsg(BaseModel):
    """Aviso de que la cola del cliente se saturó y se descartaron muestras
    (backpressure, §3.4). El cliente puede re-sincronizar si lo necesita."""

    type: Literal["overflow"] = "overflow"
    dropped: int


class ErrorMsg(BaseModel):
    type: Literal["error"] = "error"
    code: str
    detail: str


ServerMessage = Union[TagUpdateMsg, AckMsg, OverflowMsg, ErrorMsg]
