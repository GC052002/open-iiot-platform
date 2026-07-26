"""`Runtime` — supervisor del motor con concurrencia estructurada (§4, R2).

R2 (ARCHITECTURE §3.10): usamos **`asyncio.TaskGroup`** (Python 3.11+) en lugar de
`create_task` sueltos. Beneficios:
- Un fallo no capturado cancela el grupo de forma ordenada (cancelación en cascada).
- El `async with` garantiza *cleanup* de todas las tareas al parar (shutdown limpio).
- No hay fugas de tareas en reconexiones reales.

Cada driver corre en su propio *scan loop*; si un PLC cae, el loop de ESE driver
reintenta con backoff sin afectar a los demás. El runtime orquesta:

    Driver.read_block(tags)  ──►  TagCache.update(samples)  ──►  (suscriptores)

Los suscriptores (Broadcaster en F1) se conectan desde fuera vía `tag_cache.subscribe`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.drivers.base import BaseDriver
from app.drivers.registry import create_driver
from app.engine.scan_scheduler import ScanScheduler
from app.engine.tag_cache import TagCache
from app.models.node import DriverNode
from app.models.project import ProjectV1

log = logging.getLogger("iiot.runtime")

# Parámetros de backoff de reconexión (segundos).
_BACKOFF_START = 1.0
_BACKOFF_MAX = 30.0


class Runtime:
    def __init__(self, project: ProjectV1) -> None:
        self.project = project
        self.tag_cache = TagCache({t.id: t for t in project.tags})
        self.scheduler = ScanScheduler(project.tags)
        self._drivers: dict[str, BaseDriver] = {}
        self._stopping = asyncio.Event()

    # -- Ciclo de vida --------------------------------------------------------
    async def run(self) -> None:
        """Arranca un scan loop por cada nodo driver, bajo un TaskGroup (R2)."""
        driver_nodes = [n for n in self.project.nodes if isinstance(n, DriverNode)]
        try:
            async with asyncio.TaskGroup() as tg:
                for node in driver_nodes:
                    tg.create_task(self._driver_scan_loop(node), name=f"scan:{node.id}")
        except* Exception as eg:  # noqa: E999 - except* requiere py3.11
            # El TaskGroup agrega las excepciones; se registran y se propaga el shutdown.
            for exc in eg.exceptions:
                log.exception("Fallo en un scan loop", exc_info=exc)

    def stop(self) -> None:
        self._stopping.set()

    # -- Scan loop por driver -------------------------------------------------
    async def _driver_scan_loop(self, node: DriverNode) -> None:
        poll_rate = float(node.config.get("polling_rate", 1.0))
        backoff = _BACKOFF_START
        driver = create_driver(node)
        self._drivers[node.id] = driver

        while not self._stopping.is_set():
            try:
                await driver.connect()
                backoff = _BACKOFF_START  # conexión OK: resetea el backoff
                while not self._stopping.is_set():
                    tags = self.scheduler.tags_for(node.id)
                    samples = await driver.read_block(tags)
                    await self.tag_cache.update(samples)
                    await asyncio.sleep(poll_rate)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # reconexión con backoff, sin tumbar el resto
                log.warning("Driver %s error: %s; reintento en %.1fs", node.id, exc, backoff)
                await self._sleep_or_stop(backoff)
                backoff = min(backoff * 2, _BACKOFF_MAX)
            finally:
                await _safe_disconnect(driver)

    async def _sleep_or_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    # -- Escrituras (patrón Command; implementación de flujo completo en F2) ---
    async def write_tag(self, tag_id: str, value: Any) -> bool:
        tag = next((t for t in self.project.tags if t.id == tag_id), None)
        if tag is None:
            raise KeyError(f"tag desconocido: {tag_id!r}")
        driver = self._drivers.get(tag.driver_id)
        if driver is None:
            raise RuntimeError(f"driver no activo para tag {tag_id!r}")
        return await driver.write_tag(tag_id, value)


async def _safe_disconnect(driver: BaseDriver) -> None:
    try:
        await driver.disconnect()
    except Exception:  # noqa: BLE001 - disconnect nunca debe propagar en cleanup
        log.debug("Error ignorado en disconnect de %s", driver.driver_type)
