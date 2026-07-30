"""Drivers de comunicación industrial.

Factory + Registry (§6): los drivers se auto-registran con `@register_driver`.
Importar este paquete debe registrar los drivers built-in (efecto de importación).
"""

# Importar aquí cada driver built-in para que su @register_driver se ejecute.
# Los drivers de red importan su librería (aiomqtt/snap7/asyncua) de forma perezosa,
# así estos imports no requieren tenerlas instaladas.
from app.drivers import modbus_driver, mqtt_driver, opcua_driver, s7_driver  # noqa: F401

__all__ = ["modbus_driver", "mqtt_driver", "opcua_driver", "s7_driver"]
