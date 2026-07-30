"""Driver MQTT — rama 2 de la ingesta híbrida (Edge Push, §PROJECT_CONTEXT).

Es un driver **push**: sobrescribe `run` para suscribirse a un broker MQTT local
(al que publica el Edge Gateway IOT2050 vía Node-RED) y empujar cada mensaje al
TagCache — igual que Modbus, pero sin polling.

Decisiones (Rev 7):
- **Respeta el `ts` inyectado por el Edge** si viene en el payload; no lo re-sella.
- **LWT (Last Will and Testament):** al recibir el mensaje LWT de un Edge Node caído,
  inyecta `quality="bad"` para todos los tags de este driver.
- Flag `sparkplug` **diseñado** desde el inicio; la implementación Protobuf se difiere
  (F4). Con `sparkplug=false` se usa MQTT plano con payload JSON.

Contrato de payload (JSON) que publica el Edge:
    {"ts": "2026-07-30T12:00:00Z", "values": {"<address>": <valor>, ...}}
  o bien un objeto plano {"<address>": <valor>, ...} (sin ts => ts = ahora).
El `address` de cada tag es su clave en el payload (como en Modbus, §3.2).

Múltiples Edge por un driver (Rev 10): con tópicos wildcard (p. ej.
`iiot/edge/+/data`), dos Edge distintos pueden enviar la misma clave y cruzarse. Se
resuelve con `device_topic_index`: el índice del segmento `device_id` en el tópico;
entonces el `tag.address` se compara como `"{device_id}/{clave}"`. Si no se
configura, se asume **1 Edge = 1 DriverNode** (comparación por clave plana).

Config del nodo: `host`, `port` (def. 1883), `topic` (def. "#"), `lwt_topic` (opc.),
`device_topic_index` (opc., int).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from app.drivers.base import BaseDriver, Publish
from app.drivers.registry import register_driver
from app.models.tag import TagValue

log = logging.getLogger("iiot.driver.mqtt")


def _parse_ts(raw: Any) -> datetime | None:
    """Convierte un `ts` ISO8601 del Edge a datetime; None si no es válido/ausente."""
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


@register_driver("mqtt")
class MqttDriver(BaseDriver):
    def __init__(self, node) -> None:  # type: ignore[no-untyped-def]
        super().__init__(node)
        self._host: str = self.config.get("host", "127.0.0.1")
        self._port: int = int(self.config.get("port", 1883))
        self._topic: str = self.config.get("topic", "#")
        self._lwt_topic: str | None = self.config.get("lwt_topic")
        self._device_topic_index: int | None = self.config.get("device_topic_index")
        self._sparkplug: bool = bool(self.config.get("sparkplug", False))  # impl. diferida (F4)

    def _address_map(self) -> dict[str, Any]:
        """address (clave del payload, posiblemente compuesta) -> Tag."""
        return {t.address: t for t in self._tags.values()}

    def _device_id(self, topic: str) -> str | None:
        """Extrae el device_id del tópico según `device_topic_index` (Rev 10)."""
        if self._device_topic_index is None:
            return None
        parts = topic.split("/")
        idx = self._device_topic_index
        return parts[idx] if 0 <= idx < len(parts) else None

    def parse(self, topic: str, payload: bytes | str) -> list[TagValue]:
        """Traduce un mensaje MQTT a muestras. Función pura y testeable (sin red)."""
        # LWT: el Edge cayó -> todos sus tags a calidad 'bad'.
        if self._lwt_topic is not None and topic == self._lwt_topic:
            return [TagValue(tag_id=t.id, value=None, quality="bad") for t in self._tags.values()]

        try:
            data = json.loads(payload)
        except (ValueError, TypeError):
            log.warning("Payload MQTT no-JSON en %s", topic)
            return []
        if not isinstance(data, dict):
            return []

        ts = _parse_ts(data.get("ts"))
        values = data.get("values", data)  # 'values' anidado o payload plano
        if not isinstance(values, dict):
            return []

        device_id = self._device_id(topic)
        amap = self._address_map()
        out: list[TagValue] = []
        for key, val in values.items():
            # Preferir la clave compuesta '{device_id}/{key}' para aislar el origen
            # (Rev 10); si no, la clave plana (1 Edge = 1 driver).
            tag = amap.get(f"{device_id}/{key}") if device_id is not None else None
            if tag is None:
                tag = amap.get(key)
            if tag is None:
                continue
            kwargs = {"ts": ts} if ts is not None else {}
            out.append(TagValue(tag_id=tag.id, value=val, quality="good", **kwargs))
        return out

    async def run(self, publish: Publish, stopping: asyncio.Event) -> None:
        # Import perezoso: aiomqtt solo se necesita si se usa este driver.
        import aiomqtt

        async with aiomqtt.Client(hostname=self._host, port=self._port) as client:
            # QoS 1 (Rev 10): entrega garantizada para telemetría industrial.
            # TODO(F2.4): política de mensajes retained (evitar datos obsoletos al
            # arrancar) y QoS configurable por nodo.
            await client.subscribe(self._topic, qos=1)
            if self._lwt_topic is not None:
                await client.subscribe(self._lwt_topic, qos=1)
            async for message in client.messages:
                if stopping.is_set():
                    break
                samples = self.parse(str(message.topic), message.payload)
                if samples:
                    await publish(samples)

    async def write_tag(self, tag_id: str, value: Any) -> bool:
        # TODO(F2.4): patrón Comando/Respuesta (RPC over MQTT), contrato acordado (Rev 10):
        #   topic:   iiot/edge/{device_id}/command/{tag_id}
        #   payload: {"request_id": "<uuid>", "value": <v>, "ts": "<ISO8601>"}
        #   + suscripción a un topic de acknowledgment con timeout para validar en campo.
        raise NotImplementedError("Escritura vía MQTT pendiente (F2.4)")
