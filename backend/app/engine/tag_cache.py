"""`TagCache` — última-lectura-conocida por tag + deadband (ARCHITECTURE §4).

Política de concurrencia (R3, §3.10)
------------------------------------
El TagCache **vive y se muta únicamente dentro del event loop**. Los drivers que
corren en hilos (§3.1) NO tocan el cache directamente: entregan sus muestras al
loop (el runtime las aplica con `await update(...)`), de modo que las
modificaciones quedan serializadas por el propio loop.

Elegimos **copy-on-write de la entrada** en lugar de un lock global: cada `update`
reemplaza el objeto `TagValue` completo (inmutable desde el punto de vista del
lector), así un suscriptor que lea `get()` nunca observa una entrada a medio
escribir. Para invariantes que abarcan varias claves se usa un `asyncio.Lock`
de grano fino (`_write_lock`), no un lock por lectura.

El TagCache es un **sujeto Observer**: notifica a sus suscriptores (Broadcaster en
F1; Alarmas y TagBuffer en F2) solo ante cambios significativos según el deadband.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from app.models.tag import Tag, TagValue

# Un suscriptor recibe la lista de TagValues que cambiaron significativamente.
Subscriber = Callable[[list[TagValue]], Awaitable[None]]


class TagCache:
    def __init__(self, tags: dict[str, Tag] | None = None) -> None:
        self._tags: dict[str, Tag] = tags or {}
        self._values: dict[str, TagValue] = {}
        self._subscribers: list[Subscriber] = []
        self._write_lock = asyncio.Lock()

    # -- Configuración de tags ------------------------------------------------
    def set_tags(self, tags: dict[str, Tag]) -> None:
        self._tags = dict(tags)

    # -- Observer -------------------------------------------------------------
    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    async def _notify(self, changed: list[TagValue]) -> None:
        if not changed:
            return
        # Notificación concurrente a todos los suscriptores; un fallo en uno no
        # tumba a los demás.
        await asyncio.gather(
            *(sub(changed) for sub in self._subscribers),
            return_exceptions=True,
        )

    # -- Lectura --------------------------------------------------------------
    def get(self, tag_id: str) -> TagValue | None:
        return self._values.get(tag_id)

    def snapshot(self, tag_ids: list[str] | None = None) -> list[TagValue]:
        """Estado actual (para enviar el valor inicial a un cliente que se suscribe)."""
        if tag_ids is None:
            return list(self._values.values())
        return [self._values[t] for t in tag_ids if t in self._values]

    # -- Escritura (solo desde el event loop) ---------------------------------
    async def update(self, samples: list[TagValue]) -> list[TagValue]:
        """Aplica muestras nuevas. Devuelve las que superaron el deadband.

        Copy-on-write: se reemplaza la entrada completa. La notificación a
        suscriptores ocurre solo con los cambios significativos.
        """
        changed: list[TagValue] = []
        async with self._write_lock:
            for sample in samples:
                tag = self._tags.get(sample.tag_id)
                previous = self._values.get(sample.tag_id)
                prev_value = previous.value if previous else None

                significant = True
                if tag is not None:
                    significant = tag.is_significant_change(prev_value, sample.value)

                # El último valor siempre se guarda (para snapshot), pero solo se
                # reporta si el cambio es significativo.
                self._values[sample.tag_id] = sample
                if significant:
                    changed.append(sample)

        await self._notify(changed)
        return changed
