"""Nodos del canvas — unión discriminada por `type` (ARCHITECTURE §3.7, R5).

Tres familias, según la paleta del README:
- DriverNode  -> comunicación (Modbus, S7, OPC UA, MQTT).
- LogicNode   -> lógica/transformación (escalado, filtros) — patrón Strategy (§6).
- WidgetNode  -> HMI (tanques, válvulas, gráficos).

El `type` actúa como discriminador de Pydantic v2: añadir una variante nueva no
toca las existentes.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


class _BaseNode(BaseModel):
    id: str
    label: str = ""
    # Posición en el canvas (React Flow). El backend la persiste pero no la usa.
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})


class DriverNode(_BaseNode):
    type: Literal["driver"] = "driver"
    driver_type: str = Field(
        ...,
        description="Clave registrada en el DriverRegistry (p. ej. 'modbus_tcp').",
    )
    # Parámetros de conexión (IP, puerto, unit_id, polling_rate...). Neutro de
    # protocolo: cada driver valida su propio subconjunto.
    config: dict[str, Any] = Field(default_factory=dict)


class LogicNode(_BaseNode):
    type: Literal["logic"] = "logic"
    strategy: str = Field(..., description="Nombre de la estrategia (scale, deadband, avg...).")
    params: dict[str, Any] = Field(default_factory=dict)


class WidgetNode(_BaseNode):
    type: Literal["widget"] = "widget"
    widget: str = Field(..., description="Tipo de widget HMI (tank, valve, chart...).")
    props: dict[str, Any] = Field(default_factory=dict)


Node = Annotated[
    Union[DriverNode, LogicNode, WidgetNode],
    Field(discriminator="type"),
]
