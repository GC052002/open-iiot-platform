"""`BaseDriver` — contrato abstracto que todo driver debe cumplir.

Patrón Adapter (§6): el core trata igual a drivers síncronos (snap7, pymodbus en
hilo) y async nativos (asyncua, aiomqtt). El driver es responsable de NO bloquear el
event loop: si su librería es síncrona, envuelve la I/O en `asyncio.to_thread` (§3.1).

Dos modos de ingesta unificados bajo `run(publish, stopping)` (F2.2):
- **Polling** (Modbus, S7, OPC UA read): usan la implementación por defecto de `run`,
  que hace `read_block(tags)` en bucle a `polling_rate`.
- **Push** (MQTT, OPC UA subscriptions): **sobrescriben `run`** para empujar muestras
  al llegar (no hay `read_block`).

El Runtime aporta el callback `publish` (que deposita en el TagCache) y envuelve
`run` con connect/backoff/disconnect. Así añadir una fuente nueva es una clase.
"""

from __future__ import annotations

import abc
import asyncio
from typing import Any, Awaitable, Callable

from app.models.node import DriverNode
from app.models.tag import Tag, TagValue

# Callback que el Runtime pasa al driver para publicar muestras al TagCache.
Publish = Callable[[list[TagValue]], Awaitable[None]]


async def sleep_or_stop(stopping: asyncio.Event, seconds: float) -> None:
    """Duerme `seconds` o retorna antes si se señaliza `stopping` (shutdown determinista)."""
    try:
        await asyncio.wait_for(stopping.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


class BaseDriver(abc.ABC):
    """Interfaz común a todos los drivers de comunicación."""

    #: Clave del registry (la fija el decorador @register_driver).
    driver_type: str = ""

    def __init__(self, node: DriverNode) -> None:
        self.node = node
        self.config = node.config
        #: Tags que pertenecen a este driver, indexados por id (los inyecta el Runtime).
        self._tags: dict[str, Tag] = {}

    def bind_tags(self, tags: list[Tag]) -> None:
        """El Runtime asigna al driver los tags de su nodo (§4)."""
        self._tags = {t.id: t for t in tags}

    # -- Ciclo de vida (no-op por defecto; los drivers de red los sobrescriben) --
    async def connect(self) -> None:
        """Abre la conexión. Idempotente y no bloqueante. Default: no-op."""

    async def disconnect(self) -> None:
        """Cierra la conexión y libera recursos. Default: no-op."""

    # -- Ingesta --------------------------------------------------------------
    async def run(self, publish: Publish, stopping: asyncio.Event) -> None:
        """Bucle de ingesta. Default = **polling**: lee por bloques y publica hasta
        que se señalice `stopping`. Los drivers **push** (MQTT) sobrescriben esto."""
        poll_rate = float(self.config.get("polling_rate", 1.0))
        tags = list(self._tags.values())
        while not stopping.is_set():
            samples = await self.read_block(tags)
            await publish(samples)
            await sleep_or_stop(stopping, poll_rate)

    async def read_block(self, tags: list[Tag]) -> list[TagValue]:
        """Lectura optimizada por bloques (§3.2). La implementan los drivers de
        polling; los push no la usan."""
        raise NotImplementedError(f"{type(self).__name__} no implementa read_block (¿driver push?)")

    @abc.abstractmethod
    async def write_tag(self, tag_id: str, value: Any) -> bool:
        """Escribe `value` en el tag `tag_id`. Devuelve True si tuvo éxito.

        Definido desde F1 (Rev 3) para que el patrón Command encaje. Las escrituras
        se auditan aguas arriba (§3.6)."""

    async def health(self) -> dict[str, Any]:
        """Estado del driver para /health/drivers/{name} (§10.5, ampliable en F2)."""
        return {"driver_type": self.driver_type, "node_id": self.node.id}
