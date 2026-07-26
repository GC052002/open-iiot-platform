"""Simulador Modbus TCP para desarrollo y CI (Rev 3 / R6).

===============================================================================
STUB PARA RELLENO POR MODELO ECONÓMICO.
===============================================================================
Objetivo: levantar un servidor Modbus TCP con un datastore de valores variables
(p. ej. una senoidal o un contador) para probar el motor sin PLC físico.

TODO(econ) — usar `pymodbus.server.StartAsyncTcpServer` (R6) con un
`ModbusServerContext` poblado. Actualizar algunos holding registers en una tarea
de fondo para que el driver vea datos que cambian (y así ejercitar el deadband).
El puerto se lee de IIOT_MODBUS_SIM_PORT (default 5020).

Este módulo se ejecuta como `python -m app.drivers.modbus_sim` (ver docker-compose).
Debe existir también un **fixture de pytest reutilizable** que arranque/pare este
simulador para los tests de F1.
"""

from __future__ import annotations

import os


def main() -> None:
    port = int(os.environ.get("IIOT_MODBUS_SIM_PORT", "5020"))
    # TODO(econ): construir el datastore y llamar a StartAsyncTcpServer(port=port).
    raise NotImplementedError(
        f"Simulador Modbus pendiente (puerto {port}). Ver TODO(econ) en el módulo."
    )


if __name__ == "__main__":
    main()
