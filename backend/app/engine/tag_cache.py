"""`TagCache` — última-lectura-conocida por (proyecto, tag) + deadband (§4).

Multi-tenant (Rev 7)
--------------------
El cache está **segmentado por `project_id`** (equivalente a la clave namespaced
`project_id:tag_id`, implementado aquí como dict anidado por claridad). Así varios
proyectos comparten una sola instancia sin colisiones.

Orden temporal (Rev 7)
----------------------
`update` **descarta muestras out-of-order**: si `sample.ts <= última.ts` para ese
tag, se ignora. Esto evita que un mensaje MQTT retrasado por la red (Rama 2)
sobrescriba un valor más reciente. La Rama 1 (polling) asigna `ts` creciente; la
Rama 2 debe respetar el `ts` inyectado por el Edge.

Política de concurrencia (R3)
-----------------------------
Reemplazo atómico de la entrada bajo `_write_lock` de grano fino. `get()`/`snapshot()`
son seguros sin lock (single-loop, sin `await`). La notificación a suscriptores se
hace FUERA del lock (T-M1) para que un suscriptor lento no bloquee a los writers.

Es un **sujeto Observer**: notifica `(project_id, changed)` a sus suscriptores
(Broadcaster en F1; Alarmas y TagBuffer en F2) solo ante cambios significativos.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from app.models.tag import Tag, TagValue

# Un suscriptor recibe (project_id, muestras que cambiaron significativamente).
Subscriber = Callable[[str, list[TagValue]], Awaitable[None]]


class TagCache:
    def __init__(self) -> None:
        self._tags: dict[str, dict[str, Tag]] = {}      # project_id -> tag_id -> Tag
        self._values: dict[str, dict[str, TagValue]] = {}  # project_id -> tag_id -> TagValue
        self._subscribers: list[Subscriber] = []
        self._write_lock = asyncio.Lock()

    # -- Configuración de tags ------------------------------------------------
    def set_tags(self, project_id: str, tags: dict[str, Tag]) -> None:
        self._tags[project_id] = dict(tags)
        # Limpiar valores de tags que ya no existen (T-M2).
        if project_id in self._values:
            self._values[project_id] = {
                k: v for k, v in self._values[project_id].items() if k in self._tags[project_id]
            }

    def drop_project(self, project_id: str) -> None:
        self._tags.pop(project_id, None)
        self._values.pop(project_id, None)

    # -- Observer -------------------------------------------------------------
    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    async def _notify(self, project_id: str, changed: list[TagValue]) -> None:
        if not changed:
            return
        await asyncio.gather(
            *(sub(project_id, changed) for sub in self._subscribers),
            return_exceptions=True,
        )

    # -- Lectura --------------------------------------------------------------
    def get(self, project_id: str, tag_id: str) -> TagValue | None:
        return self._values.get(project_id, {}).get(tag_id)

    def snapshot(self, project_id: str, tag_ids: list[str] | None = None) -> list[TagValue]:
        vals = self._values.get(project_id, {})
        if tag_ids is None:
            return list(vals.values())
        return [vals[t] for t in tag_ids if t in vals]

    # -- Escritura (solo desde el event loop) ---------------------------------
    async def update(self, project_id: str, samples: list[TagValue]) -> list[TagValue]:
        """Aplica muestras nuevas de un proyecto. Devuelve las significativas.

        Descarta out-of-order (Rev 7); reemplazo atómico bajo lock; notifica fuera
        del lock solo con cambios que superan el deadband.
        """
        changed: list[TagValue] = []
        async with self._write_lock:
            proj_tags = self._tags.get(project_id, {})
            proj_vals = self._values.setdefault(project_id, {})
            for sample in samples:
                previous = proj_vals.get(sample.tag_id)

                # Orden temporal: ignorar muestras más viejas o iguales (Rev 7).
                if previous is not None and sample.ts <= previous.ts:
                    continue

                prev_value = previous.value if previous else None
                tag = proj_tags.get(sample.tag_id)
                significant = True
                if tag is not None:
                    significant = tag.is_significant_change(prev_value, sample.value)

                proj_vals[sample.tag_id] = sample
                if significant:
                    changed.append(sample)

        await self._notify(project_id, changed)
        return changed
