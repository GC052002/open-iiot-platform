"""Estrategias de `LogicNode` (F3 — cálculos y transformaciones).

Dos familias:
- **Built-in seguras** (sin ejecutar código de usuario): `scale`, `avg`, `deadband`.
- **Expresión del usuario** (`expr`): sandbox con **asteval** — intérprete restringido
  que **no** permite `import`, `open`, acceso a dunder/atributos, ni builtins peligrosos;
  solo aritmética sobre las variables que le damos (`x` + parámetros numéricos).

Contrato de `compute(x) -> float | None`:
- devuelve un número → se publica como tag derivado;
- devuelve `None` → sin salida este ciclo (deadband suprime, o entrada no numérica);
- nunca lanza: los errores (p. ej. expresión inválida) se capturan y devuelven `None`
  (fail-safe: un `LogicNode` roto no puede tumbar el motor).
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Protocol

log = logging.getLogger("iiot.logic")

#: Límite de longitud de una expresión de usuario (anti-DoS / abuso).
MAX_EXPR_LEN = 500


def _as_number(x: Any) -> float | None:
    """Devuelve x como float si es numérico (y no bool disfrazado), si no None."""
    if isinstance(x, bool):
        return float(x)
    if isinstance(x, (int, float)):
        return float(x)
    return None


class Compute(Protocol):
    def __call__(self, x: Any) -> float | None: ...


def _scale(a: float, b: float) -> Compute:
    def compute(x: Any) -> float | None:
        v = _as_number(x)
        return None if v is None else a * v + b
    return compute


class _MovingAverage:
    """Media móvil de las últimas `window` muestras numéricas."""

    def __init__(self, window: int) -> None:
        self.buf: deque[float] = deque(maxlen=max(1, int(window)))

    def __call__(self, x: Any) -> float | None:
        v = _as_number(x)
        if v is None:
            return None
        self.buf.append(v)
        return sum(self.buf) / len(self.buf)


class _Deadband:
    """Filtro: deja pasar `x` solo si cambió al menos `deadband` respecto al último."""

    def __init__(self, deadband: float) -> None:
        self.db = abs(float(deadband))
        self.last: float | None = None

    def __call__(self, x: Any) -> float | None:
        v = _as_number(x)
        if v is None:
            return None
        if self.last is None or abs(v - self.last) >= self.db:
            self.last = v
            return v
        return None


class _SafeExpr:
    """Evalúa una expresión aritmética del usuario en un sandbox asteval.

    asteval bloquea por diseño `import`, `open`, `eval/exec`, acceso a `__dunder__`
    y builtins peligrosos. Aquí, además: límite de longitud, símbolos acotados a
    `x` + parámetros numéricos, y fail-safe (error → None)."""

    def __init__(self, expr: str, params: dict[str, Any]) -> None:
        self.expr = str(expr)
        # Solo parámetros numéricos entran al symtable (nada de callables/objetos).
        self.params = {
            k: float(v)
            for k, v in params.items()
            if k not in ("input", "output", "expr") and isinstance(v, (int, float))
            and not isinstance(v, bool)
        }
        self._interp: Any | None = None

    def _interpreter(self) -> Any:
        from asteval import Interpreter  # import perezoso (dep opcional)

        # minimal=True: intérprete reducido (sin funciones de E/S); sin numpy.
        try:
            return Interpreter(minimal=True, use_numpy=False)
        except TypeError:  # versiones antiguas sin `minimal`
            return Interpreter(use_numpy=False)

    def __call__(self, x: Any) -> float | None:
        if len(self.expr) > MAX_EXPR_LEN:
            log.warning("expr de LogicNode demasiado larga (%d chars), ignorada", len(self.expr))
            return None
        try:
            interp = self._interp or self._interpreter()
            self._interp = interp
            interp.symtable["x"] = x
            for k, v in self.params.items():
                interp.symtable[k] = v
            interp.error = []  # limpia errores previos
            result = interp(self.expr, show_errors=False)
            if interp.error:
                interp.error = []
                return None
            return _as_number(result)
        except Exception as exc:  # noqa: BLE001 - fail-safe: nunca propagar
            log.warning("expr de LogicNode falló: %s", exc)
            return None


def build_compute(strategy: str, params: dict[str, Any]) -> Compute:
    """Factory: devuelve la función `compute(x)` de la estrategia dada.

    Estrategia desconocida → identidad numérica (pasa el valor tal cual)."""
    p = params or {}
    if strategy == "scale":
        return _scale(float(p.get("a", 1.0)), float(p.get("b", 0.0)))
    if strategy == "avg":
        return _MovingAverage(int(p.get("window", 10)))
    if strategy == "deadband":
        return _Deadband(float(p.get("deadband", 0.0)))
    if strategy == "expr":
        return _SafeExpr(str(p.get("expr", "x")), p)
    # Desconocida: identidad (útil como passthrough); no rompe el motor.
    return _as_number  # type: ignore[return-value]


# Reexport para tests / claridad.
scale = _scale
MovingAverage = _MovingAverage
Deadband = _Deadband
SafeExpr = _SafeExpr

__all__ = ["build_compute", "scale", "MovingAverage", "Deadband", "SafeExpr", "MAX_EXPR_LEN"]
