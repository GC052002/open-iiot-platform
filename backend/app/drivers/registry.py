"""Factory + Registry de drivers (§6).

Fase 1-2: registro por decorador `@register_driver("modbus_tcp")`.
Fase 3 (§11.3): `discover()` añadirá soporte de `entry_points` para plugins pip
externos (BACnet, EtherNet/IP, DNP3...) sin tocar el core. Placeholder abajo.
"""

from __future__ import annotations

from typing import Callable, Type

from app.drivers.base import BaseDriver
from app.models.node import DriverNode

_REGISTRY: dict[str, Type[BaseDriver]] = {}


def register_driver(driver_type: str) -> Callable[[Type[BaseDriver]], Type[BaseDriver]]:
    """Decorador de auto-registro. Uso:

        @register_driver("modbus_tcp")
        class ModbusDriver(BaseDriver): ...
    """

    def _wrap(cls: Type[BaseDriver]) -> Type[BaseDriver]:
        if driver_type in _REGISTRY:
            raise ValueError(f"driver_type duplicado: {driver_type!r}")
        cls.driver_type = driver_type
        _REGISTRY[driver_type] = cls
        return cls

    return _wrap


def create_driver(node: DriverNode) -> BaseDriver:
    """Instancia el driver adecuado según `node.driver_type` (Factory)."""
    try:
        cls = _REGISTRY[node.driver_type]
    except KeyError as exc:
        raise KeyError(
            f"driver_type no registrado: {node.driver_type!r}. "
            f"Registrados: {sorted(_REGISTRY)}"
        ) from exc
    return cls(node)


def registered_drivers() -> list[str]:
    return sorted(_REGISTRY)


def discover() -> None:
    """[F3, §11.3] Descubrir drivers externos vía importlib.metadata entry_points.

    TODO(F3): cargar entry_points del grupo 'iiot_platform.drivers' y registrarlos
    junto a los built-in. No implementar todavía.
    """
    return None
