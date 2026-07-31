"""Rev 12: endurecimiento de F2.4 (fail-closed, histéresis, cola de notificaciones)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.alarms.engine import AlarmEngine, _resolve_active
from app.alarms.notifier import Notifier, QueuedNotifier
from app.models.alarm import AlarmEvent, AlarmRule
from app.models.tag import TagValue
from app.security.crypto import CredentialCipher

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _tv(v, secs):
    return TagValue(tag_id="t", value=v, ts=_BASE + timedelta(seconds=secs))


# --- Fix #2: crypto fail-closed ---------------------------------------------

def test_crypto_fail_closed_without_key(monkeypatch):
    monkeypatch.delenv("IIOT_FERNET_KEY", raising=False)
    monkeypatch.setenv("IIOT_ALLOW_ANONYMOUS", "false")
    with pytest.raises(RuntimeError):
        CredentialCipher()
    # En modo dev sí se permite (clave efímera).
    monkeypatch.setenv("IIOT_ALLOW_ANONYMOUS", "true")
    assert CredentialCipher() is not None


# --- Fix #4: histéresis anti-rebote -----------------------------------------

def test_hysteresis_prevents_flapping():
    rule = AlarmRule(id="hi", tag_id="t", condition="gt", threshold=10, hysteresis=1.0)
    # Activa al superar 10.
    assert _resolve_active(10.5, rule, was_active=False) is True
    # Oscila justo por debajo del umbral pero dentro de la banda: sigue activa.
    assert _resolve_active(9.5, rule, was_active=True) is True   # > 10-1
    # Cae claramente por debajo de la banda: despeja.
    assert _resolve_active(8.5, rule, was_active=True) is False  # < 10-1


async def test_engine_no_flapping_within_band():
    eng = AlarmEngine(notifier=_Rec())
    eng.register_project("P", [AlarmRule(id="hi", tag_id="t", condition="gt",
                                         threshold=10, hysteresis=1.0)])
    await eng.on_tag_update("P", [_tv(11, 0)])   # activa
    await eng.on_tag_update("P", [_tv(9.5, 1)])  # dentro de banda -> sigue activa
    assert len(eng.active_alarms("P")) == 1
    await eng.on_tag_update("P", [_tv(8, 2)])    # fuera de banda -> despeja
    assert eng.active_alarms("P") == []


# --- Fix #5: cola de notificaciones con reintentos --------------------------

class _Rec(Notifier):
    def __init__(self):
        self.events = []

    async def notify(self, event):
        self.events.append(event)


class _FlakyOnce(Notifier):
    def __init__(self):
        self.fail = True
        self.events = []

    async def notify(self, event):
        if self.fail:
            self.fail = False
            raise RuntimeError("timeout")
        self.events.append(event)


def _ev():
    return AlarmEvent(project_id="P", rule_id="r", tag_id="t", severity="warning",
                      message="", state="active", value=1)


async def test_queued_notifier_delivers():
    inner = _Rec()
    q = QueuedNotifier(inner, rate_per_sec=1000)
    q.start()
    try:
        await q.notify(_ev())
        await asyncio.sleep(0.1)
        assert len(inner.events) == 1
    finally:
        await q.stop()


async def test_queued_notifier_retries_on_failure():
    inner = _FlakyOnce()
    q = QueuedNotifier(inner, rate_per_sec=1000, max_retries=3)
    # Backoff empieza en 1s; monkeypatch no necesario: el worker reintenta.
    q.start()
    try:
        await q.notify(_ev())
        await asyncio.sleep(1.2)   # deja pasar el primer backoff (1s)
        assert len(inner.events) == 1  # entregado tras reintento
    finally:
        await q.stop()
