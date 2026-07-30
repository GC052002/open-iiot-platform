"""`TagBuffer` — suscriptor de persistencia del TagCache (§11.1, Rev 8).

Se suscribe al TagCache como **raw** (`subscribe(cb, raw=True)`), por lo que recibe
TODAS las muestras válidas (no solo los deltas del WebSocket) y así el historiador
no pierde valores intermedios. Acumula y hace *flush* en batch (cada N segundos o
cada M muestras) para no escribir una fila por lectura.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from app.models.tag import TagValue
from app.storage.repository import HistorianRepository

log = logging.getLogger("iiot.tagbuffer")


class TagBuffer:
    def __init__(
        self, repo: HistorianRepository, flush_interval: float = 5.0, max_batch: int = 1000
    ) -> None:
        self._repo = repo
        self._interval = flush_interval
        self._max_batch = max_batch
        self._pending: dict[str, list[TagValue]] = defaultdict(list)
        self._count = 0
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def on_samples(self, project_id: str, values: list[TagValue]) -> None:
        """Callback registrado como suscriptor raw del TagCache."""
        async with self._lock:
            self._pending[project_id].extend(values)
            self._count += len(values)
            over = self._count >= self._max_batch
        if over:
            await self.flush()

    async def flush(self) -> None:
        async with self._lock:
            if self._count == 0:
                return
            batch = self._pending
            self._pending = defaultdict(list)
            self._count = 0

        failed: dict[str, list[TagValue]] = {}
        for project_id, samples in batch.items():
            try:
                await self._repo.insert(project_id, samples)
            except Exception:  # noqa: BLE001 - un fallo de BD no debe tumbar el motor
                log.exception("Fallo al persistir batch de %s; se reintentará", project_id)
                failed[project_id] = samples

        # Rev 9: reencolar lo que falló (fallo transitorio de disco no debe perder
        # telemetría). Se reinserta al principio para conservar el orden temporal.
        if failed:
            async with self._lock:
                for project_id, samples in failed.items():
                    self._pending[project_id] = samples + self._pending[project_id]
                    self._count += len(samples)
                # TODO(F2.4): acotar el buffer de reintento (cap + drop-oldest) para no
                # crecer sin límite si la BD queda caída mucho tiempo.

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="tag_buffer")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass
            await self.flush()

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.flush()  # flush final para no perder lo pendiente
