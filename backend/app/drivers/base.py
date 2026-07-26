"""`BaseDriver` — contrato abstracto que todo driver debe cumplir.

Patrón Adapter (§6): el core del motor trata igual a drivers síncronos (snap7,
pymodbus en hilo) y async nativos (asyncua, aiomqtt). El driver es responsable de
NO bloquear el event loop: si su librería es síncrona, debe envolver la I/O en
`asyncio.to_thread` (§3.1).

Contratos clave:
- `read_block(tags)`  -> lectura optimizada por bloques. El scheduler entrega una
  lista genérica de `Tag`; el driver decide qué significa "contiguo" en su
  protocolo (§3.2, neutralidad de protocolo).
- `write_tag(tag_id, value)` -> firma definida DESDE la Fase 1 (Rev 3), aunque la
  implementación del flujo Command llegue en F2.
"""

from __future__ import annotations

import abc
from typing import Any

from app.models.node import DriverNode
from app.models.tag import Tag, TagValue


class BaseDriver(abc.ABC):
    """Interfaz común a todos los drivers de comunicación."""

    #: Clave del registry (la fija el decorador @register_driver).
    driver_type: str = ""

    def __init__(self, node: DriverNode) -> None:
        self.node = node
        self.config = node.config
        #: Tags que pertenecen a este driver, indexados por id. Los inyecta el
        #: Runtime con `bind_tags` para que `write_tag` pueda resolver direcciones.
        self._tags: dict[str, Tag] = {}

    def bind_tags(self, tags: list[Tag]) -> None:
        """El Runtime asigna al driver los tags de su nodo (§4)."""
        self._tags = {t.id: t for t in tags}

    @abc.abstractmethod
    async def connect(self) -> None:
        """Abre la conexión. Debe ser idempotente y no bloquear el loop."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Cierra la conexión y libera recursos."""

    @abc.abstractmethod
    async def read_block(self, tags: list[Tag]) -> list[TagValue]:
        """Lee un conjunto de tags de forma optimizada (por bloques, §3.2).

        Recibe una lista genérica de `Tag`; la agrupación por contigüidad es
        responsabilidad del driver (rangos Modbus, DB de S7, subárbol OPC UA).
        """

    @abc.abstractmethod
    async def write_tag(self, tag_id: str, value: Any) -> bool:
        """Escribe `value` en el tag `tag_id`. Devuelve True si tuvo éxito.

        Definido desde F1 (Rev 3) para que el patrón Command de F2 encaje sin
        parches. Las escrituras se auditan aguas arriba (§3.6).
        """

    async def health(self) -> dict[str, Any]:
        """Estado del driver para /health/drivers/{name} (§10.5, ampliable en F2)."""
        return {"driver_type": self.driver_type, "node_id": self.node.id}
