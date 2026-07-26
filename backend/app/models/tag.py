"""Modelo `Tag` — unidad de dato leída/escrita en un dispositivo.

Decisiones de diseño relevantes:
- R4 (ARCHITECTURE §3.10): `deadband` y `deadband_mode` viven en el modelo desde
  la Fase 1. `deadband = 0.0` => reportar todo (útil en tests). Esto evita que un
  analógico ruidoso sature el WebSocket al conectar el primer cliente.
- §3.2: el `Tag` es neutro de protocolo; `address` es una cadena que cada driver
  interpreta en su contexto (p. ej. "40001" Modbus, "DB1.DBD0" S7, un NodeId OPC UA).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

DeadbandMode = Literal["abs", "pct"]


class Tag(BaseModel):
    """Definición de un tag dentro de la topología del proyecto."""

    id: str = Field(..., description="Identificador único del tag en el proyecto.")
    name: str = Field(..., description="Nombre legible para la UI.")
    driver_id: str = Field(..., description="ID del nodo driver que posee este tag.")
    address: str = Field(
        ...,
        description="Dirección específica del protocolo, interpretada por el driver (§3.2).",
    )
    data_type: Literal["bool", "int", "float", "string"] = "float"
    unit: str | None = Field(default=None, description="Unidad de ingeniería (opcional).")

    # --- R4: deadband / report-by-exception ---
    deadband: float = Field(
        default=0.0,
        ge=0.0,
        description="Umbral mínimo de cambio para reportar. 0.0 = reportar todo.",
    )
    deadband_mode: DeadbandMode = Field(
        default="abs",
        description="'abs' = valor absoluto; 'pct' = porcentaje respecto al último valor.",
    )

    def is_significant_change(self, previous: Any, current: Any) -> bool:
        """¿El cambio `previous -> current` supera el deadband y debe reportarse?

        Regla (usada por el TagCache, §4):
        - deadband 0.0 o valores no numéricos => siempre significativo.
        - modo 'abs' => |current - previous| >= deadband.
        - modo 'pct' => |current - previous| >= |previous| * (deadband / 100).
        """
        if previous is None:
            return True
        if self.deadband <= 0.0:
            return True
        if not isinstance(current, (int, float)) or not isinstance(previous, (int, float)):
            return current != previous

        delta = abs(current - previous)
        if self.deadband_mode == "pct":
            threshold = abs(previous) * (self.deadband / 100.0)
        else:
            threshold = self.deadband
        return delta >= threshold


class TagValue(BaseModel):
    """Una muestra concreta de un tag (última-lectura-conocida en el TagCache)."""

    tag_id: str
    value: Any
    quality: Literal["good", "bad", "uncertain"] = "good"
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
