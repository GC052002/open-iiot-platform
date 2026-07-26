"""Simulador Modbus TCP para desarrollo y CI (Rev 3 / R6).

Levanta un servidor Modbus TCP con Holding Registers que cambian en el tiempo
(una onda "diente de sierra" por registro), de modo que el driver vea datos
variables y se pueda ejercitar el deadband end-to-end sin PLC físico.

Convención de direcciones: `tag.address` es el offset entero del Holding Register
(0-based). El simulador puebla los registros 0..N-1.

Ejecución standalone: `python -m app.drivers.modbus_sim` (ver docker-compose.yml).
Para tests, usar el fixture `modbus_sim` de `backend/tests/conftest.py`.
"""

from __future__ import annotations

import asyncio
import os

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer

_NUM_UPDATED = 16  # registros 0..15 varían con el tiempo (telemetría simulada)
_BLOCK_SIZE = 64  # registros 16..63 quedan estáticos (útiles para tests de escritura)
_HR_FC = 3  # función Modbus de Holding Registers


def build_context() -> ModbusServerContext:
    """Crea el contexto con un bloque de Holding Registers inicializado a 0."""
    block = ModbusSequentialDataBlock(0, [0] * _BLOCK_SIZE)
    slave = ModbusSlaveContext(hr=block)
    return ModbusServerContext(slaves=slave, single=True)


async def _updater(context: ModbusServerContext, period: float = 0.5) -> None:
    """Actualiza los registros con una rampa cíclica para simular telemetría."""
    tick = 0
    while True:
        values = [(tick + i * 3) % 100 for i in range(_NUM_UPDATED)]
        context[0].setValues(_HR_FC, 0, values)
        tick = (tick + 1) % 100
        await asyncio.sleep(period)


async def run(host: str = "0.0.0.0", port: int = 5020) -> None:
    """Arranca el updater y el servidor Modbus TCP (bloquea hasta cancelación)."""
    context = build_context()
    updater = asyncio.create_task(_updater(context))
    try:
        await StartAsyncTcpServer(context=context, address=(host, port))
    finally:
        updater.cancel()


def main() -> None:
    port = int(os.environ.get("IIOT_MODBUS_SIM_PORT", "5020"))
    asyncio.run(run(port=port))


if __name__ == "__main__":
    main()
