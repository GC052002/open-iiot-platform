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
from app.models.tag import TagValue

log = logging.getLogger("iiot.runtime")

# Parámetros de backoff de reconexión (segundos).
_BACKOFF_START = 1.0
_BACKOFF_MAX = 30.0


class Runtime:
    def __init__(self, project: ProjectV1, tag_cache: TagCache | None = None) -> None:
        self.project = project
        # Multi-tenant (Rev 7): el TagCache puede ser compartido entre proyectos;
        # si no se inyecta, se crea uno propio. Cada proyecto tiene su Runtime (y por
        # tanto su TaskGroup) para aislamiento de fallos (noisy-neighbor).
        self.tag_cache = tag_cache if tag_cache is not None else TagCache()
        self.tag_cache.set_tags(project.project_id, {t.id: t for t in project.tags})
        self.scheduler = ScanScheduler(project.tags)
        self._drivers: dict[str, BaseDriver] = {}
        self._stopping = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._healthy = True

    # -- Ciclo de vida --------------------------------------------------------
    async def run(self) -> None:
        """Arranca un scan loop por cada nodo driver, bajo un TaskGroup (R2)."""
        driver_nodes = [n for n in self.project.nodes if isinstance(n, DriverNode)]
        try:
            async with asyncio.TaskGroup() as tg:
                for node in driver_nodes:
                    task = tg.create_task(self._driver_scan_loop(node), name=f"scan:{node.id}")
                    self._tasks.append(task)
        except* Exception as eg:  # noqa: E999 - except* requiere py3.11
            # Si el grupo termina por excepción (no por cancelación), el runtime queda
            # degradado: se marca no-sano para que /health no siga diciendo "ok" (R-M2).
            self._healthy = False
            for exc in eg.exceptions:
                log.exception("Fallo en un scan loop", exc_info=exc)

    def stop(self) -> None:
        """Señaliza parada y **cancela** los scan loops (R-H1).

        `asyncio.TaskGroup` no expone `cancel()` hasta Python 3.13; cancelamos las
        tareas guardadas para que un driver bloqueado en I/O no cuelgue el shutdown.
        TODO(py3.13): reemplazar por `self._tg.cancel()`.
        """
        self._stopping.set()
        for task in self._tasks:
            task.cancel()

    def health(self) -> dict[str, Any]:
        return {"healthy": self._healthy, "drivers": sorted(self._drivers)}

    # -- Loop por driver (polling o push, unificado por driver.run) -----------
    async def _driver_scan_loop(self, node: DriverNode) -> None:
        backoff = _BACKOFF_START
        driver = create_driver(node)
        driver.bind_tags(self.scheduler.tags_for(node.id))
        self._drivers[node.id] = driver

        async def publish(samples: list[TagValue]) -> None:
            await self.tag_cache.update(self.project.project_id, samples)

        while not self._stopping.is_set():
            try:
                await driver.connect()
                backoff = _BACKOFF_START  # conexión OK: resetea el backoff
                # run() bloquea hasta stop (polling) o hasta error/desconexión (push).
                await driver.run(publish, self._stopping)
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
    # BLOCKER 2 (Rev 6): al cancelar la tarea, un `await` normal en el finally
    # lanzaría CancelledError de inmediato y el socket TCP no se cerraría (conexiones
    # zombie en el PLC). `asyncio.shield` deja completar el cierre pese a la cancelación.
    try:
        await asyncio.shield(driver.disconnect())
    except asyncio.CancelledError:
        pass  # cancelación esperada durante el cleanup; el socket ya se cerró
    except Exception:  # noqa: BLE001 - disconnect nunca debe propagar en cleanup
        log.debug("Error ignorado en disconnect de %s", driver.driver_type)
