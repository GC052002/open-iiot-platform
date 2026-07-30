"""`ConnectionManager` — broadcaster con backpressure (ARCHITECTURE §3.4, §4).

Multi-tenant (Rev 7): el manager es **global** y enruta por la clave compuesta
`(project_id, tag_id)`, de modo que un cliente solo recibe los tags del proyecto al
que está suscrito. El aislamiento de fallos vive en el `Runtime`/`TaskGroup` por
proyecto, no aquí.

Cada cliente tiene una `asyncio.Queue(maxsize=N)` acotada. Si se llena (cliente
lento, §3.4), se descarta la muestra más vieja y se avisa con `OverflowMsg`.

Es un **suscriptor del TagCache** (Observer): `on_tag_update` se registra vía
`tag_cache.subscribe(...)`.
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

# Clave de enrutado: (project_id, tag_id).
SubKey = tuple[str, str]


@dataclass
class _Client:
    ws: WebSocket
    queue: asyncio.Queue[TagUpdateMsg] = field(
        default_factory=lambda: asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    )
    keys: set[SubKey] = field(default_factory=set)
    dropped: int = 0


class ConnectionManager:
    def __init__(self) -> None:
        self._subs: dict[SubKey, set[_Client]] = {}
        self._clients: set[_Client] = set()

    # -- Ciclo de vida de la conexión ----------------------------------------
    async def connect(self, ws: WebSocket) -> _Client:
        await ws.accept()
        client = _Client(ws=ws)
        self._clients.add(client)
        return client

    def disconnect(self, client: _Client) -> None:
        self._clients.discard(client)
        for key in list(client.keys):
            subs = self._subs.get(key)
            if subs:
                subs.discard(client)
                if not subs:
                    del self._subs[key]
        client.keys.clear()  # evita que _enqueue siga enrutando aquí (W-m1)
        while not client.queue.empty():
            client.queue.get_nowait()

    def subscribe(self, client: _Client, project_id: str, tag_ids: list[str]) -> None:
        for tag_id in tag_ids:
            key = (project_id, tag_id)
            self._subs.setdefault(key, set()).add(client)
            client.keys.add(key)

    def unsubscribe(self, client: _Client, project_id: str, tag_ids: list[str]) -> None:
        for tag_id in tag_ids:
            key = (project_id, tag_id)
            self._subs.get(key, set()).discard(client)
            client.keys.discard(key)

    # -- Suscriptor del TagCache (Observer) ----------------------------------
    async def on_tag_update(self, project_id: str, changed: list[TagValue]) -> None:
        """Enruta cada cambio a los clientes suscritos a (project_id, tag_id)."""
        per_client: dict[_Client, list[TagValue]] = {}
        for value in changed:
            for client in self._subs.get((project_id, value.tag_id), ()):  # type: ignore[arg-type]
                per_client.setdefault(client, []).append(value)

        for client, values in per_client.items():
            self._enqueue(client, TagUpdateMsg(values=values))

    def _enqueue(self, client: _Client, msg: TagUpdateMsg) -> None:
        # TODO(F2, W-M2): coalescing — fusionar valores con el último TagUpdateMsg en
        # cola para no mandar N mensajes ante N cambios escalonados (overhead a 1000 tags).
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
        while True:
            msg = await client.queue.get()
            # Overflow ANTES del dato: cronológicamente el hueco ocurrió antes del
            # siguiente punto; una tendencia HMI no interpola sobre el gap (Rev 6).
            if client.dropped:
                await client.ws.send_text(OverflowMsg(dropped=client.dropped).model_dump_json())
                client.dropped = 0
            await client.ws.send_text(msg.model_dump_json())
