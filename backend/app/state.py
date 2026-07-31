"""Estado compartido de la aplicación (evita import circular entre main y api).

Multi-tenant (Rev 7): un único proceso con un `TagCache` **compartido** y un
`Runtime` (por tanto un `asyncio.TaskGroup`) **por `project_id`**, de modo que un
driver descontrolado de un proyecto no afecte al event loop de otro. El
`ConnectionManager` es global y enruta por `(project_id, tag_id)`.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

from app.alarms import AlarmEngine, build_notifier_from_env
from app.engine.runtime import Runtime
from app.engine.tag_cache import TagCache
from app.models.project import ProjectV1
from app.storage import HistorianRepository, SQLiteHistorian, TagBuffer
from app.ws.manager import ConnectionManager


@dataclass
class _RunningProject:
    runtime: Runtime
    task: asyncio.Task


class AppState:
    def __init__(self) -> None:
        self.tag_cache = TagCache()            # compartido entre proyectos
        self.manager = ConnectionManager()
        self._projects: dict[str, _RunningProject] = {}
        self.repo: HistorianRepository | None = None
        self.tag_buffer: TagBuffer | None = None
        self.alarms = AlarmEngine(build_notifier_from_env())
        # Suscriptores delta del TagCache (solo cambios): WebSocket y alarmas.
        self.tag_cache.subscribe(self.manager.on_tag_update)
        self.tag_cache.subscribe(self.alarms.on_tag_update)

    # -- Persistencia (F2.1) --------------------------------------------------
    async def startup(self, repo: HistorianRepository | None = None) -> None:
        """Arranca el historiador y el TagBuffer (suscriptor raw). Idempotente."""
        if self.repo is not None:
            return
        self.repo = repo or SQLiteHistorian(os.environ.get("IIOT_DB_PATH", "iiot_history.db"))
        await self.repo.init()
        self.tag_buffer = TagBuffer(self.repo)
        # raw=True: el historiador recibe todas las muestras válidas (Rev 8).
        self.tag_cache.subscribe(self.tag_buffer.on_samples, raw=True)
        self.tag_buffer.start()

    async def shutdown(self) -> None:
        await self.stop_all()
        if self.tag_buffer is not None:
            await self.tag_buffer.stop()
            self.tag_buffer = None
        if self.repo is not None:
            await self.repo.close()
            self.repo = None

    async def start_project(self, project: ProjectV1) -> None:
        """Arranca (o reinicia) un proyecto con su propio Runtime/TaskGroup."""
        await self.stop_project(project.project_id)
        self.alarms.register_project(project.project_id, project.alarms)
        runtime = Runtime(project, tag_cache=self.tag_cache)
        task = asyncio.create_task(runtime.run(), name=f"runtime:{project.project_id}")
        self._projects[project.project_id] = _RunningProject(runtime=runtime, task=task)

    async def stop_project(self, project_id: str) -> None:
        running = self._projects.pop(project_id, None)
        if running is None:
            return
        running.runtime.stop()
        running.task.cancel()
        try:
            await running.task
        except (asyncio.CancelledError, Exception):
            pass
        self.alarms.unregister_project(project_id)
        self.tag_cache.drop_project(project_id)

    async def stop_all(self) -> None:
        for project_id in list(self._projects):
            await self.stop_project(project_id)

    # -- Accesores ------------------------------------------------------------
    def runtime(self, project_id: str) -> Runtime | None:
        rp = self._projects.get(project_id)
        return rp.runtime if rp else None

    def project_ids(self) -> list[str]:
        return sorted(self._projects)

    async def write_tag(self, project_id: str, tag_id: str, value: Any) -> bool:
        runtime = self.runtime(project_id)
        if runtime is None:
            raise RuntimeError(f"proyecto no iniciado: {project_id!r}")
        return await runtime.write_tag(tag_id, value)

    async def audit(self, action: str, **fields: Any) -> None:
        """Registra una acción crítica en el audit log (no falla si no hay repo)."""
        if self.repo is not None:
            await self.repo.record_audit({"action": action, **fields})

    def health(self) -> dict[str, Any]:
        return {pid: rp.runtime.health() for pid, rp in self._projects.items()}


state = AppState()
