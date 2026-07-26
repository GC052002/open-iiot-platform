"""Tests de integración del driver Modbus contra el simulador.

===============================================================================
STUB PARA RELLENO POR MODELO ECONÓMICO (usa el fixture `modbus_sim`).
===============================================================================
TODO(econ): una vez implementados modbus_driver.py y modbus_sim.py:
  - test_connect_read_roundtrip: conectar, leer un bloque, verificar TagValue.
  - test_write_then_read: escribir un registro y leerlo de vuelta.
  - test_deadband_end_to_end: valores ruidosos del sim -> el TagCache filtra.
"""

import pytest

pytestmark = pytest.mark.skip(reason="ModbusDriver/simulador pendientes (TODO econ).")


def test_connect_read_roundtrip(modbus_sim):
    ...
