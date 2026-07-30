"""Estado compartido de la aplicación (evita import circular entre main y api).

Multi-tenant (Rev 7): un único proceso con un `TagCache` **compartido** y un
`Runtime` (por tanto un `asyncio.TaskGroup`) **por `project_id`**, de modo que un
driver descontrolado de un proyecto no afecte al event loop de otro. El
`ConnectionManager` es global y enruta por `(project_id, tag_id)`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.engine.runtime import Runtime
from app.engine.tag_cache import TagCache
from app.models.project import ProjectV1
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
        # El manager es suscriptor único del TagCache (Observer).
        self.tag_cache.subscribe(self.manager.on_tag_update)

    async def start_project(self, project: ProjectV1) -> None:
        """Arranca (o reinicia) un proyecto con su propio Runtime/TaskGroup."""
        await self.stop_project(project.project_id)
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

    def health(self) -> dict[str, Any]:
        return {pid: rp.runtime.health() for pid, rp in self._projects.items()}


state = AppState()
