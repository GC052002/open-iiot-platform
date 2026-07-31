"""F2.4a: motor de alarmas — evaluación, transiciones y notificación."""

from datetime import datetime, timedelta, timezone

import pytest

from app.alarms.engine import AlarmEngine, evaluate
from app.alarms.notifier import Notifier
from app.models.alarm import AlarmEvent, AlarmRule
from app.models.tag import TagValue

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _tv(tag_id: str, value, secs: float = 0) -> TagValue:
    return TagValue(tag_id=tag_id, value=value, ts=_BASE + timedelta(seconds=secs))


class _RecordingNotifier(Notifier):
    def __init__(self):
        self.events: list[AlarmEvent] = []

    async def notify(self, event: AlarmEvent) -> None:
        self.events.append(event)


# --- Evaluación de condiciones ----------------------------------------------

def test_evaluate_conditions():
    assert evaluate(10, "gt", 5) is True
    assert evaluate(3, "gt", 5) is False
    assert evaluate(5, "ge", 5) is True
    assert evaluate(4, "lt", 5) is True
    assert evaluate(5, "le", 5) is True
    assert evaluate(5, "eq", 5) is True
    assert evaluate(6, "ne", 5) is True
    assert evaluate(None, "gt", 5) is False          # sin valor, no alarma
    assert evaluate("texto", "gt", 5) is False        # no comparable


# --- Transiciones y notificación --------------------------------------------

def _engine():
    n = _RecordingNotifier()
    eng = AlarmEngine(notifier=n)
    eng.register_project("P", [AlarmRule(id="hi", tag_id="t", condition="gt",
                                         threshold=80, severity="critical", message="Nivel alto")])
    return eng, n


async def test_alarm_activates_once_on_transition():
    eng, n = _engine()
    await eng.on_tag_update("P", [_tv("t", 50)])   # normal
    assert n.events == []
    await eng.on_tag_update("P", [_tv("t", 90)])   # supera 80 -> activa
    assert len(n.events) == 1 and n.events[0].state == "active"
    await eng.on_tag_update("P", [_tv("t", 95)])   # sigue alta -> NO re-notifica
    assert len(n.events) == 1
    assert [a["rule_id"] for a in eng.active_alarms("P")] == ["hi"]


async def test_alarm_clears_on_return_to_normal():
    eng, n = _engine()
    await eng.on_tag_update("P", [_tv("t", 90)])   # activa
    await eng.on_tag_update("P", [_tv("t", 40)])   # despeja
    assert [e.state for e in n.events] == ["active", "cleared"]
    assert eng.active_alarms("P") == []


async def test_projects_isolated_and_unregister():
    eng, n = _engine()
    eng.register_project("Q", [AlarmRule(id="hi", tag_id="t", condition="gt", threshold=10)])
    await eng.on_tag_update("Q", [_tv("t", 20)])   # activa en Q
    await eng.on_tag_update("P", [_tv("t", 5)])    # normal en P
    assert len(eng.active_alarms("Q")) == 1
    assert eng.active_alarms("P") == []
    eng.unregister_project("Q")
    assert eng.active_alarms("Q") == []
