"""`TagCache` — última-lectura-conocida por (proyecto, tag) + deadband (§4).

Multi-tenant (Rev 7)
--------------------
El cache está **segmentado por `project_id`** (equivalente a la clave namespaced
`project_id:tag_id`, implementado aquí como dict anidado por claridad). Así varios
proyectos comparten una sola instancia sin colisiones.

Orden temporal (Rev 7 / Rev 8)
------------------------------
`update` **descarta muestras estrictamente más viejas**: si `sample.ts < última.ts`
para ese tag, se ignora. Se usa `<` (no `<=`, Rev 8) para no descartar lecturas
legítimas de polling de alta frecuencia que caen en el mismo timestamp por
resolución del reloj; con `ts` igual se permite la actualización y el deadband
filtra si el valor no cambió. Esto evita que un MQTT retrasado (Rama 2) sobrescriba
un valor más reciente, siendo tolerante a ráfagas MQTT (QoS 1) con el mismo `ts`.

Política de concurrencia (R3)
-----------------------------
Reemplazo atómico de la entrada bajo `_write_lock` de grano fino. `get()`/`snapshot()`
son seguros sin lock (single-loop, sin `await`). La notificación a suscriptores se
hace FUERA del lock (T-M1) para que un suscriptor lento no bloquee a los writers.

Es un **sujeto Observer** con dos tipos de suscriptor (Rev 8):
- **delta**: recibe solo cambios significativos (superan deadband) — p. ej. el
  Broadcaster WebSocket, que no debe saturar la red.
- **raw**: recibe TODAS las muestras válidas post-orden-temporal — p. ej. el
  `TagBuffer` historiador (F2.1), que persiste el dato crudo sin perder intermedios.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from app.models.tag import Tag, TagValue

# Un suscriptor recibe (project_id, muestras).
Subscriber = Callable[[str, list[TagValue]], Awaitable[None]]


class TagCache:
    def __init__(self) -> None:
        self._tags: dict[str, dict[str, Tag]] = {}      # project_id -> tag_id -> Tag
        self._values: dict[str, dict[str, TagValue]] = {}  # project_id -> tag_id -> TagValue
        self._delta_subs: list[Subscriber] = []  # solo cambios significativos
        self._raw_subs: list[Subscriber] = []    # todas las muestras válidas
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
    def subscribe(self, subscriber: Subscriber, raw: bool = False) -> None:
        """Registra un suscriptor. `raw=True` recibe todas las muestras válidas
        (para persistencia); por defecto recibe solo cambios significativos (delta)."""
        (self._raw_subs if raw else self._delta_subs).append(subscriber)

    async def _notify(
        self, subs: list[Subscriber], project_id: str, values: list[TagValue]
    ) -> None:
        if not values or not subs:
            return
        await asyncio.gather(
            *(sub(project_id, values) for sub in subs),
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
        changed: list[TagValue] = []   # significativos (delta)
        valid: list[TagValue] = []     # todos los que pasan el orden temporal (raw)
        async with self._write_lock:
            proj_tags = self._tags.get(project_id, {})
            proj_vals = self._values.setdefault(project_id, {})
            for sample in samples:
                previous = proj_vals.get(sample.tag_id)

                # Orden temporal: ignorar solo muestras ESTRICTAMENTE más viejas (Rev 8).
                if previous is not None and sample.ts < previous.ts:
                    continue

                prev_value = previous.value if previous else None
                tag = proj_tags.get(sample.tag_id)
                significant = True
                if tag is not None:
                    significant = tag.is_significant_change(prev_value, sample.value)

                proj_vals[sample.tag_id] = sample
                valid.append(sample)
                if significant:
                    changed.append(sample)

        # delta -> solo cambios; raw -> todas las válidas (para el historiador, F2.1).
        await self._notify(self._delta_subs, project_id, changed)
        await self._notify(self._raw_subs, project_id, valid)
        return changed
