"""`AlarmEngine` — suscriptor **delta** del TagCache que evalúa umbrales (F2.4a).

Es global (una instancia), como el `ConnectionManager`: se suscribe una vez al
TagCache y mantiene reglas y estado **por `project_id`**. Emite un `AlarmEvent` solo
en las **transiciones** (inactiva→activa = "active"; activa→inactiva = "cleared"),
para no notificar en cada muestra.

Se suscribe como *delta* (solo cambios significativos): basta para evaluar umbrales
sin saturar; el historiador *raw* es otro suscriptor independiente (§11.1).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.alarms.notifier import LogNotifier, Notifier
from app.models.alarm import AlarmEvent, AlarmRule, AlarmState
from app.models.tag import TagValue


def evaluate(value: Any, condition: str, threshold: float) -> bool:
    """¿El valor está en condición de alarma? Comparaciones numéricas seguras."""
    if value is None:
        return False
    try:
        if condition == "gt":
            return value > threshold
        if condition == "lt":
            return value < threshold
        if condition == "ge":
            return value >= threshold
        if condition == "le":
            return value <= threshold
        if condition == "eq":
            return value == threshold
        if condition == "ne":
            return value != threshold
    except TypeError:
        return False
    return False


class AlarmEngine:
    def __init__(self, notifier: Notifier | None = None) -> None:
        self._notifier = notifier or LogNotifier()
        # project_id -> tag_id -> reglas
        self._by_tag: dict[str, dict[str, list[AlarmRule]]] = {}
        # (project_id, rule_id) -> AlarmRule / AlarmState
        self._rules: dict[tuple[str, str], AlarmRule] = {}
        self._state: dict[tuple[str, str], AlarmState] = {}

    # -- Registro de reglas por proyecto -------------------------------------
    def register_project(self, project_id: str, rules: list[AlarmRule]) -> None:
        self.unregister_project(project_id)
        by_tag: dict[str, list[AlarmRule]] = {}
        for rule in rules:
            by_tag.setdefault(rule.tag_id, []).append(rule)
            self._rules[(project_id, rule.id)] = rule
        self._by_tag[project_id] = by_tag

    def unregister_project(self, project_id: str) -> None:
        self._by_tag.pop(project_id, None)
        for key in [k for k in self._rules if k[0] == project_id]:
            self._rules.pop(key, None)
            self._state.pop(key, None)

    # -- Suscriptor delta del TagCache ---------------------------------------
    async def on_tag_update(self, project_id: str, changed: list[TagValue]) -> None:
        rules_by_tag = self._by_tag.get(project_id)
        if not rules_by_tag:
            return
        events: list[AlarmEvent] = []
        for value in changed:
            for rule in rules_by_tag.get(value.tag_id, ()):  # type: ignore[arg-type]
                events.extend(self._apply(project_id, rule, value.value))
        for ev in events:
            await self._notifier.notify(ev)

    def _apply(self, project_id: str, rule: AlarmRule, value: Any) -> list[AlarmEvent]:
        key = (project_id, rule.id)
        in_alarm = evaluate(value, rule.condition, rule.threshold)
        prev = self._state.get(key)
        was = prev.active if prev else False
        if in_alarm == was:
            return []  # sin transición
        self._state[key] = AlarmState(
            active=in_alarm,
            since=datetime.now(timezone.utc) if in_alarm else None,
            value=value,
        )
        return [
            AlarmEvent(
                project_id=project_id, rule_id=rule.id, tag_id=rule.tag_id,
                severity=rule.severity, message=rule.message,
                state="active" if in_alarm else "cleared", value=value,
            )
        ]

    # -- Consulta -------------------------------------------------------------
    def active_alarms(self, project_id: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for (pid, rid), st in self._state.items():
            if pid != project_id or not st.active:
                continue
            rule = self._rules.get((pid, rid))
            if rule is None:
                continue
            out.append({
                "rule_id": rid, "tag_id": rule.tag_id, "severity": rule.severity,
                "message": rule.message, "value": st.value,
                "since": st.since.isoformat() if st.since else None,
            })
        return out
