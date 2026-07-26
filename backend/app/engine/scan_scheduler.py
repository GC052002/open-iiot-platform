"""`ScanScheduler` — agrupa tags para lectura optimizada (ARCHITECTURE §3.2).

Neutralidad de protocolo (Rev 3)
--------------------------------
El scheduler NO conoce la semántica de "contiguo" de ningún protocolo. Su única
responsabilidad es:
  1. repartir los tags por su `driver_id`, y
  2. entregar a cada driver la lista genérica de `Tag` que le corresponde en cada
     ciclo de scan (según su polling rate).

Es el `BaseDriver` (o subclase) quien, dentro de `read_block`, decide cómo
optimizar: rangos de Holding Registers en Modbus, `DB` en S7, subárbol en OPC UA.
Así, añadir un protocolo nuevo (F2) no toca este archivo.
"""

from __future__ import annotations

from collections import defaultdict

from app.models.tag import Tag


class ScanScheduler:
    def __init__(self, tags: list[Tag]) -> None:
        self._by_driver: dict[str, list[Tag]] = defaultdict(list)
        for tag in tags:
            self._by_driver[tag.driver_id].append(tag)

    def driver_ids(self) -> list[str]:
        return list(self._by_driver)

    def tags_for(self, driver_id: str) -> list[Tag]:
        """Tags que este driver debe leer en un ciclo. La agrupación por bloques
        contiguos la hace el driver (neutralidad de protocolo, §3.2)."""
        return self._by_driver.get(driver_id, [])
