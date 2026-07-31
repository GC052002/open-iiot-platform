"""Modelos de alarmas (F2.4a).

Una `AlarmRule` evalúa un tag contra un umbral. El motor mantiene el estado
(activa/inactiva) y emite un `AlarmEvent` solo en las transiciones.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

# gt: >, lt: <, ge: >=, le: <=, eq: ==, ne: !=
Condition = Literal["gt", "lt", "ge", "le", "eq", "ne"]
Severity = Literal["info", "warning", "critical"]


class AlarmRule(BaseModel):
    id: str = Field(..., description="Identificador único de la regla en el proyecto.")
    tag_id: str = Field(..., description="Tag evaluado.")
    condition: Condition = "gt"
    threshold: float = 0.0
    severity: Severity = "warning"
    message: str = ""


class AlarmState(BaseModel):
    active: bool = False
    since: datetime | None = None
    value: Any = None


class AlarmEvent(BaseModel):
    """Notificación de una transición de alarma (activación o despeje)."""

    project_id: str
    rule_id: str
    tag_id: str
    severity: Severity
    message: str
    state: Literal["active", "cleared"]
    value: Any = None
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
