"""Estado compartido de la aplicación (evita import circular entre main y api).

Multi-tenant (Rev 7): un único proceso con un `TagCache` **compartido** y un
`Runtime` (por tanto un `asyncio.TaskGroup`) **por `project_id`**, de modo que un
driver descontrolado de un proyecto no afecte al event loop de otro. El
`ConnectionManager` es global y enruta por `(project_id, tag_id)`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from app.alarms import AlarmEngine, build_notifier_from_env
from app.engine.runtime import Runtime
from app.engine.tag_cache import TagCache
from app.logic import LogicEngine
from app.models.node import DriverNode, LogicNode
from app.models.project import ProjectV1, load_project
from app.storage import (
    ConfigRepository,
    HistorianRepository,
    SQLiteConfigRepository,
    SQLiteHistorian,
    TagBuffer,
)
from app.ws.manager import ConnectionManager

log = logging.getLogger("iiot.state")


@dataclass
class _RunningProject:
    runtime: Runtime
    task: asyncio.Task


def _has_secret_ref(config: Any) -> bool:
    """¿La config contiene alguna referencia `{"$secret": ...}` (recursivo)?"""
    if isinstance(config, dict):
        if "$secret" in config:
            return True
        return any(_has_secret_ref(v) for v in config.values())
    if isinstance(config, list):
        return any(_has_secret_ref(v) for v in config)
    return False


class AppState:
    def __init__(self) -> None:
        self.tag_cache = TagCache()            # compartido entre proyectos
        self.manager = ConnectionManager()
        self._projects: dict[str, _RunningProject] = {}
        self.repo: HistorianRepository | None = None
        self.config_repo: ConfigRepository | None = None  # F4: usuarios/proyectos/secretos
        self.secret_store = None  # F4.1c: SecretStore (asignado en startup)
        self.tag_buffer: TagBuffer | None = None
        self.alarms = AlarmEngine(build_notifier_from_env())
        self.logic = LogicEngine(publish=self.tag_cache.update)  # F3: LogicNode
        # Suscriptores delta del TagCache (solo cambios): WebSocket, alarmas y lógica.
        self.tag_cache.subscribe(self.manager.on_tag_update)
        self.tag_cache.subscribe(self.alarms.on_tag_update)
        self.tag_cache.subscribe(self.logic.on_tag_update)

    # -- Persistencia (F2.1) --------------------------------------------------
    async def startup(
        self,
        repo: HistorianRepository | None = None,
        config_repo: ConfigRepository | None = None,
    ) -> None:
        """Arranca historiador, TagBuffer y la persistencia de configuración (F4).

        Idempotente. Carga usuarios (con bootstrap) y arranca los proyectos persistidos.
        """
        if self.repo is not None:
            return
        self.repo = repo or SQLiteHistorian(os.environ.get("IIOT_DB_PATH", "iiot_history.db"))
        await self.repo.init()
        self.tag_buffer = TagBuffer(self.repo)
        # raw=True: el historiador recibe todas las muestras válidas (Rev 8).
        self.tag_cache.subscribe(self.tag_buffer.on_samples, raw=True)
        self.tag_buffer.start()
        self.alarms.start()  # worker de notificaciones (Rev 12) si aplica
        from app.observability.metrics import metrics
        metrics.register_source(self.metrics_sources)
        await self._startup_config(config_repo)

    async def _startup_config(self, config_repo: ConfigRepository | None) -> None:
        """Inicializa la persistencia de configuración (F4.0/F4.1/F4.1c) y recarga."""
        from app.security import context
        from app.security.secrets import SecretStore
        from app.security.user_store import DbUserStore

        self.config_repo = config_repo or SQLiteConfigRepository(
            os.environ.get("IIOT_CONFIG_DB", "iiot_config.db"))
        await self.config_repo.init()
        # Usuarios respaldados en BD (sustituye al store por-env, con bootstrap).
        db_store = DbUserStore(self.config_repo)
        await db_store.load()
        context.set_user_store(db_store)
        # Almacén de secretos (KEK de instancia = IIOT_FERNET_KEY).
        self.secret_store = SecretStore(self.config_repo, context.cipher)
        context.set_secret_store(self.secret_store)
        # Arranca los proyectos persistidos (F4.1).
        await self._load_persisted_projects()

    async def _load_persisted_projects(self) -> None:
        if self.config_repo is None:
            return
        for row in await self.config_repo.list_projects():
            record = await self.config_repo.get_project(row["project_id"])
            if record is None:
                continue
            try:
                project = load_project(record["schema_json"])
            except Exception:  # noqa: BLE001 - un proyecto corrupto no debe tumbar el arranque
                log.warning("proyecto persistido inválido: %s", row["project_id"])
                continue
            await self.start_project(project)

    async def shutdown(self) -> None:
        await self.stop_all()
        await self.alarms.stop()
        if self.tag_buffer is not None:
            await self.tag_buffer.stop()
            self.tag_buffer = None
        if self.repo is not None:
            await self.repo.close()
            self.repo = None
        if self.config_repo is not None:
            await self.config_repo.close()
            self.config_repo = None
            self.secret_store = None

    async def start_project(self, project: ProjectV1) -> None:
        """Arranca (o reinicia) un proyecto con su propio Runtime/TaskGroup.

        Las credenciales referenciadas como `{"$secret": "<id>"}` en la config de los
        drivers se resuelven aquí (F4.1c) sobre una **copia** para el runtime; el modelo
        persistido conserva la referencia, nunca el secreto en claro.
        """
        await self.stop_project(project.project_id)
        self.alarms.register_project(project.project_id, project.alarms)
        logic_nodes = [n for n in project.nodes if isinstance(n, LogicNode)]
        self.logic.register_project(project.project_id, logic_nodes)
        runtime_project = await self._resolve_project_secrets(project)
        runtime = Runtime(runtime_project, tag_cache=self.tag_cache)
        task = asyncio.create_task(runtime.run(), name=f"runtime:{project.project_id}")
        self._projects[project.project_id] = _RunningProject(runtime=runtime, task=task)

    async def _resolve_project_secrets(self, project: ProjectV1) -> ProjectV1:
        """Devuelve una copia con los `$secret` de las configs de driver resueltos."""
        if self.secret_store is None:
            return project
        needs = any(isinstance(n, DriverNode) and _has_secret_ref(n.config)
                    for n in project.nodes)
        if not needs:
            return project
        resolved = project.model_copy(deep=True)
        for node in resolved.nodes:
            if isinstance(node, DriverNode):
                node.config = await self.secret_store.resolve_config(node.config)
        return resolved

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
        self.logic.unregister_project(project_id)
        self.tag_cache.drop_project(project_id)

    async def stop_all(self) -> None:
        for project_id in list(self._projects):
            await self.stop_project(project_id)

    # -- Persistencia de proyectos (F4.1 / F4.1b) -----------------------------
    async def persist_project(self, project: ProjectV1, owner: str) -> None:
        """Guarda la topología del proyecto (schema_json) conservando su versión."""
        if self.config_repo is None:
            return
        await self.config_repo.upsert_project(
            project.project_id, project.name, owner, project.model_dump_json())

    async def publish_project(self, project_id: str) -> int:
        """Publica una instantánea INMUTABLE de la plantilla (F4.1b — Rev D1 §8.1.2).

        Devuelve la nueva `delivery_version`. Sin hot-reload de topología: la entrega es
        una copia versionada del `schema_json` actual.
        """
        if self.config_repo is None:
            raise RuntimeError("persistencia de configuración no inicializada")
        record = await self.config_repo.get_project(project_id)
        if record is None:
            raise KeyError(project_id)
        version = int(record["delivery_version"]) + 1
        await self.config_repo.add_version(project_id, version, record["schema_json"])
        return version

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

    async def driver_health(self) -> dict[str, Any]:
        """Health granular por proyecto y driver (§10.5, F2.4c)."""
        out: dict[str, Any] = {}
        for pid, rp in self._projects.items():
            out[pid] = {did: await d.health() for did, d in rp.runtime.drivers().items()}
        return out

    def metrics_sources(self):
        """Gauges dinámicos para /metrics (evaluados al hacer scrape)."""
        yield ("iiot_ws_connected_clients", {}, self.manager.client_count())
        yield ("iiot_running_projects", {}, len(self._projects))
        active = sum(len(self.alarms.active_alarms(pid)) for pid in self._projects)
        yield ("iiot_active_alarms", {}, active)


state = AppState()
