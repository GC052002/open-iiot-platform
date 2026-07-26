"""`ConnectionManager` — broadcaster con backpressure (ARCHITECTURE §3.4, §4).

Cada cliente tiene una `asyncio.Queue(maxsize=N)` acotada. Si la cola se llena
(cliente lento por VPN, §3.4), se descarta la muestra **más vieja** y se avisa con
un `OverflowMsg` — en telemetría, el último valor es el que importa.

Este manager es un **suscriptor del TagCache** (Observer): `on_tag_update` se
registra vía `tag_cache.subscribe(...)`.

F1: manager local por proceso (single-worker). F3/F4 (§10.1): un `RedisBridge`
reenviará entre workers; este manager no cambia, solo gana una fuente de eventos.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.models.tag import TagValue
from app.ws.protocol import OverflowMsg, TagUpdateMsg

log = logging.getLogger("iiot.ws")

_QUEUE_MAXSIZE = 100


@dataclass
class _Client:
    ws: WebSocket
    queue: asyncio.Queue[TagUpdateMsg] = field(
        default_factory=lambda: asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    )
    tag_ids: set[str] = field(default_factory=set)
    dropped: int = 0


class ConnectionManager:
    def __init__(self) -> None:
        # tag_id -> clientes suscritos (routing selectivo).
        self._subs: dict[str, set[_Client]] = {}
        self._clients: set[_Client] = set()

    # -- Ciclo de vida de la conexión ----------------------------------------
    async def connect(self, ws: WebSocket) -> _Client:
        await ws.accept()
        client = _Client(ws=ws)
        self._clients.add(client)
        return client

    def disconnect(self, client: _Client) -> None:
        self._clients.discard(client)
        for tag_id in client.tag_ids:
            self._subs.get(tag_id, set()).discard(client)

    def subscribe(self, client: _Client, tag_ids: list[str]) -> None:
        for tag_id in tag_ids:
            self._subs.setdefault(tag_id, set()).add(client)
            client.tag_ids.add(tag_id)

    def unsubscribe(self, client: _Client, tag_ids: list[str]) -> None:
        for tag_id in tag_ids:
            self._subs.get(tag_id, set()).discard(client)
            client.tag_ids.discard(tag_id)

    # -- Suscriptor del TagCache (Observer) ----------------------------------
    async def on_tag_update(self, changed: list[TagValue]) -> None:
        """Enruta cada cambio a los clientes suscritos, con backpressure."""
        # Agrupar por cliente para mandar un solo mensaje con sus tags.
        per_client: dict[_Client, list[TagValue]] = {}
        for value in changed:
            for client in self._subs.get(value.tag_id, ()):  # type: ignore[arg-type]
                per_client.setdefault(client, []).append(value)

        for client, values in per_client.items():
            self._enqueue(client, TagUpdateMsg(values=values))

    def _enqueue(self, client: _Client, msg: TagUpdateMsg) -> None:
        try:
            client.queue.put_nowait(msg)
        except asyncio.QueueFull:
            # Descartar la más vieja y meter la nueva (drop-oldest, §3.4).
            try:
                client.queue.get_nowait()
                client.dropped += 1
            except asyncio.QueueEmpty:
                pass
            try:
                client.queue.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    # -- Bucle de envío por cliente ------------------------------------------
    async def sender_loop(self, client: _Client) -> None:
        """Vacía la cola del cliente hacia su WebSocket. Un cliente lento solo se
        afecta a sí mismo."""
        while True:
            msg = await client.queue.get()
            if client.dropped:
                await client.ws.send_text(OverflowMsg(dropped=client.dropped).model_dump_json())
                client.dropped = 0
            await client.ws.send_text(msg.model_dump_json())
