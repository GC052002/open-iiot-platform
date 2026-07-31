"""Notificadores de alarmas (F2.4a).

Interfaz `Notifier` + `LogNotifier` por defecto. Telegram/SMTP se implementan como
otros `Notifier` en F2.4 (misma interfaz, sin tocar el motor).
"""

from __future__ import annotations

import abc
import logging

from app.models.alarm import AlarmEvent

log = logging.getLogger("iiot.alarms")


class Notifier(abc.ABC):
    @abc.abstractmethod
    async def notify(self, event: AlarmEvent) -> None: ...


class LogNotifier(Notifier):
    async def notify(self, event: AlarmEvent) -> None:
        level = logging.CRITICAL if event.severity == "critical" else logging.WARNING
        verb = "ACTIVADA" if event.state == "active" else "despejada"
        log.log(
            level,
            "ALARMA %s [%s] proyecto=%s tag=%s valor=%r — %s",
            verb, event.severity, event.project_id, event.tag_id, event.value, event.message,
        )


class CompositeNotifier(Notifier):
    """Reenvía a varios notificadores (p. ej. log + Telegram + SMTP en F2.4)."""

    def __init__(self, *notifiers: Notifier) -> None:
        self._notifiers = list(notifiers)

    async def notify(self, event: AlarmEvent) -> None:
        for n in self._notifiers:
            try:
                await n.notify(event)
            except Exception:  # noqa: BLE001 - un notificador no debe tumbar a los demás
                log.exception("Fallo en notificador %s", type(n).__name__)
