"""Driver OPC UA — push vía subscriptions (F2.3).

`asyncua` es async nativo. Es un driver **push**: sobrescribe `run`, crea una
*subscription* en el servidor OPC UA y empuja cada cambio al TagCache (no hay
polling, §3.9).

Direccionamiento: `tag.address = NodeId` en formato asyncua, p. ej. `"ns=2;i=3"` o
`"ns=2;s=Temperature"`.

Config del nodo: `url` (p. ej. "opc.tcp://127.0.0.1:4840"), `period_ms` (def. 500).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.drivers.base import BaseDriver, Publish
from app.drivers.registry import register_driver
from app.models.tag import TagValue

log = logging.getLogger("iiot.driver.opcua")


class _SubHandler:
    """Handler de asyncua: traduce cada cambio a una muestra y la publica."""

    def __init__(self, driver: "OpcUaDriver", publish: Publish) -> None:
        self._driver = driver
        self._publish = publish

    def datachange_notification(self, node, val, data) -> None:  # noqa: ANN001 - API asyncua
        import time

        from app.observability.metrics import metrics

        labels = {"driver": self._driver.driver_type, "node": self._driver.node.id}
        metrics.inc("iiot_driver_messages_received_total", labels)   # Rev 13
        metrics.observe("iiot_driver_last_message_ts", labels, time.time())
        sample = self._driver.to_sample(node.nodeid.to_string(), val)
        if sample is not None:
            # El handler es síncrono; programamos la publicación en el loop.
            asyncio.create_task(self._publish([sample]))


@register_driver("opcua")
class OpcUaDriver(BaseDriver):
    def __init__(self, node) -> None:  # type: ignore[no-untyped-def]
        super().__init__(node)
        self._url: str = self.config.get("url", "opc.tcp://127.0.0.1:4840")
        self._period_ms: int = int(self.config.get("period_ms", 500))
        #: NodeId (string) -> tag_id. Se inicializa con la dirección configurada y se
        #: completa en run() con el `to_string()` canónico de asyncua (Rev 11).
        self._handle_map: dict[str, str] = {}

    def bind_tags(self, tags: list) -> None:  # type: ignore[override]
        super().bind_tags(tags)
        self._handle_map = {t.address: t.id for t in tags}

    def to_sample(self, node_id: str, value: Any) -> TagValue | None:
        """Traduce (NodeId, valor) a TagValue. Función pura y testeable (sin servidor)."""
        tag_id = self._handle_map.get(node_id)
        if tag_id is None:
            return None
        return TagValue(tag_id=tag_id, value=value, quality="good")

    async def run(self, publish: Publish, stopping: asyncio.Event) -> None:
        from asyncua import Client  # perezoso: solo si se usa el driver

        async with Client(url=self._url) as client:
            handler = _SubHandler(self, publish)
            sub = await client.create_subscription(self._period_ms, handler)
            for tag in self._tags.values():
                node = client.get_node(tag.address)
                # Clave canónica que asyncua entregará en el callback (Rev 11): evita
                # que un NodeId string/guid normalizado no coincida y se pierdan datos.
                self._handle_map[node.nodeid.to_string()] = tag.id
                await sub.subscribe_data_change(node)
            await stopping.wait()  # mantener viva la suscripción hasta el shutdown
            await sub.delete()

    async def write_tag(self, tag_id: str, value: Any) -> bool:
        from asyncua import Client

        tag = self._tags.get(tag_id)
        if tag is None:
            raise KeyError(f"tag OPC UA no vinculado: {tag_id!r}")
        async with Client(url=self._url) as client:
            await client.get_node(tag.address).write_value(value)
        return True
