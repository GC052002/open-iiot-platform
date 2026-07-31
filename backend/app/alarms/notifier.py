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
    """Reenvía a varios notificadores (p. ej. log + Telegram + SMTP)."""

    def __init__(self, *notifiers: Notifier) -> None:
        self._notifiers = list(notifiers)

    async def notify(self, event: AlarmEvent) -> None:
        for n in self._notifiers:
            try:
                await n.notify(event)
            except Exception:  # noqa: BLE001 - un notificador no debe tumbar a los demás
                log.exception("Fallo en notificador %s", type(n).__name__)


def format_message(event: AlarmEvent) -> str:
    """Texto de la notificación (puro y testeable). Compartido por Telegram/SMTP."""
    verb = "ACTIVADA" if event.state == "active" else "DESPEJADA"
    return (
        f"[{event.severity.upper()}] ALARMA {verb}\n"
        f"Proyecto: {event.project_id}\n"
        f"Tag: {event.tag_id}\n"
        f"Valor: {event.value}\n"
        f"{event.message}"
    )


class QueuedNotifier(Notifier):
    """Envuelve un notificador con **cola acotada + rate-limit + reintentos** (Rev 12).

    `notify()` solo encola (no bloquea el motor de alarmas). Un worker consume a
    `rate_per_sec` como máximo, con reintentos y backoff exponencial. Evita perder
    notificaciones por timeouts y baneos por ráfaga (HTTP 429 de Telegram).
    """

    def __init__(self, inner: Notifier, rate_per_sec: float = 1.0,
                 max_retries: int = 3, maxsize: int = 1000) -> None:
        self._inner = inner
        self._min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._max_retries = max_retries
        self._queue: "asyncio.Queue[AlarmEvent]" = None  # type: ignore[assignment]
        self._maxsize = maxsize
        self._task = None

    async def notify(self, event: AlarmEvent) -> None:
        import asyncio

        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._maxsize)
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            log.warning("Cola de notificaciones llena; se descarta un evento de %s",
                        event.tag_id)

    def start(self) -> None:
        import asyncio

        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._maxsize)
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="notifier_worker")

    async def _run(self) -> None:
        import asyncio

        while True:
            event = await self._queue.get()
            await self._send_with_retry(event)
            if self._min_interval:
                await asyncio.sleep(self._min_interval)  # rate-limit

    async def _send_with_retry(self, event: AlarmEvent) -> None:
        import asyncio

        delay = 1.0
        for _ in range(self._max_retries):
            try:
                await self._inner.notify(event)
                return
            except Exception:  # noqa: BLE001
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)
        log.error("Notificación descartada tras %d reintentos (tag=%s)",
                  self._max_retries, event.tag_id)

    async def stop(self) -> None:
        import asyncio

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


def build_notifier_from_env() -> "Notifier":
    """Construye el notificador según el entorno: siempre log; Telegram/SMTP si están
    configurados (IIOT_TELEGRAM_TOKEN/CHAT_ID, IIOT_SMTP_HOST/...)."""
    import os

    notifiers: list[Notifier] = [LogNotifier()]
    tok, chat = os.environ.get("IIOT_TELEGRAM_TOKEN"), os.environ.get("IIOT_TELEGRAM_CHAT_ID")
    if tok and chat:
        notifiers.append(TelegramNotifier(tok, chat))
    host = os.environ.get("IIOT_SMTP_HOST")
    if host:
        notifiers.append(SMTPNotifier(
            host=host,
            port=int(os.environ.get("IIOT_SMTP_PORT", "587")),
            sender=os.environ.get("IIOT_SMTP_FROM", "iiot@localhost"),
            recipients=[r for r in os.environ.get("IIOT_SMTP_TO", "").split(",") if r],
            username=os.environ.get("IIOT_SMTP_USER"),
            password=os.environ.get("IIOT_SMTP_PASSWORD"),
        ))
    if len(notifiers) == 1:
        return notifiers[0]  # solo log: envío directo, sin cola
    # Con notificadores de red (Telegram/SMTP): cola + rate-limit + reintentos (Rev 12).
    return QueuedNotifier(CompositeNotifier(*notifiers))


class TelegramNotifier(Notifier):
    """Envía por la Bot API de Telegram. I/O de red en `to_thread` (urllib, stdlib)."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._token = bot_token
        self._chat_id = chat_id

    async def notify(self, event: AlarmEvent) -> None:
        import asyncio
        import json
        import urllib.request

        payload = json.dumps({"chat_id": self._chat_id, "text": format_message(event)}).encode()
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"

        def _send() -> None:
            req = urllib.request.Request(url, data=payload,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()

        await asyncio.to_thread(_send)


class SMTPNotifier(Notifier):
    """Envía por SMTP (smtplib, stdlib). I/O en `to_thread`."""

    def __init__(self, host: str, port: int, sender: str, recipients: list[str],
                 username: str | None = None, password: str | None = None,
                 use_tls: bool = True) -> None:
        self._host, self._port = host, port
        self._sender, self._recipients = sender, recipients
        self._username, self._password, self._use_tls = username, password, use_tls

    async def notify(self, event: AlarmEvent) -> None:
        import asyncio
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["Subject"] = f"[{event.severity.upper()}] Alarma {event.project_id}/{event.tag_id}"
        msg["From"] = self._sender
        msg["To"] = ", ".join(self._recipients)
        msg.set_content(format_message(event))

        def _send() -> None:
            with smtplib.SMTP(self._host, self._port, timeout=15) as s:
                if self._use_tls:
                    s.starttls()
                if self._username:
                    s.login(self._username, self._password or "")
                s.send_message(msg)

        await asyncio.to_thread(_send)
