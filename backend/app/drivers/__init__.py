"""Drivers de comunicación industrial.

Factory + Registry (§6): los drivers se auto-registran con `@register_driver`.
Importar este paquete debe registrar los drivers built-in (efecto de importación).
"""

# Importar aquí cada driver built-in para que su @register_driver se ejecute.
from app.drivers import modbus_driver  # noqa: F401

__all__ = ["modbus_driver"]
