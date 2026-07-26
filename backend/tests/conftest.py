"""Fixtures compartidas de tests.

TODO(econ, R6): añadir aquí un fixture reutilizable `modbus_sim` que arranque y
pare el simulador `app.drivers.modbus_sim` para los tests de integración del
driver. Debe ser independiente de la versión (pinned pymodbus>=3.6,<4).
"""

import pytest


@pytest.fixture
def modbus_sim():
    pytest.skip("Fixture del simulador Modbus pendiente (TODO econ, R6).")
