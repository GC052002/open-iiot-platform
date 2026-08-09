"""Paquete `logic` — ejecución de `LogicNode` (cálculos/transformaciones).

`LogicEngine` corre en el backend como suscriptor del TagCache y publica tags
derivados. La estrategia `expr` usa un sandbox asteval (ver `strategies.py`).
"""

from app.logic.engine import LogicEngine, LogicRunner

__all__ = ["LogicEngine", "LogicRunner"]
