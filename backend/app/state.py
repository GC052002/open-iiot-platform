"""Estado compartido de la aplicación (evita import circular entre main y api)."""

from __future__ import annotations

import asyncio

from app.engine.runtime import Runtime
from app.ws.manager import ConnectionManager


class AppState:
    runtime: Runtime | None = None
    manager: ConnectionManager = ConnectionManager()
    runtime_task: asyncio.Task | None = None

    async def start_project(self, runtime: Runtime) -> None:
        """Detiene el runtime anterior (si hay) y arranca uno nuevo, conectando el
        ConnectionManager como suscriptor del TagCache (Observer, §4)."""
        await self.stop_project()
        self.runtime = runtime
        runtime.tag_cache.subscribe(self.manager.on_tag_update)
        self.runtime_task = asyncio.create_task(runtime.run(), name="runtime")

    async def stop_project(self) -> None:
        if self.runtime is not None:
            self.runtime.stop()
        if self.runtime_task is not None:
            self.runtime_task.cancel()
            try:
                await self.runtime_task
            except (asyncio.CancelledError, Exception):
                pass
        self.runtime = None
        self.runtime_task = None


state = AppState()
