# Tareas de revisión y relleno — Fase 1 (andamiaje)

> Este andamiaje (interfaces + engine core) fue escrito por **Opus** siguiendo
> `ARCHITECTURE.md`. Está **en revisión en el PR #1** (rama
> `claude/open-iiot-platform-64k96b`, sin mergear a `main`). Aquí se listan las
> piezas marcadas `TODO(econ)` que deben rellenar los **modelos económicos**
> (Gemini Flash / GLM / Sonnet), según el reparto del `ROADMAP.md §0`.
>
> **Regla:** no cambiar las **interfaces** ni las decisiones de `ARCHITECTURE.md`
> sin discutirlo. Rellenar solo la implementación detrás de esos contratos.

## Estado actual

- ✅ Interfaces y contratos base (Opus): `models/`, `ws/protocol.py`,
  `drivers/base.py`, `drivers/registry.py`.
- ✅ Engine core (Opus): `engine/tag_cache.py` (deadband + concurrencia R3),
  `engine/scan_scheduler.py` (neutro de protocolo), `engine/runtime.py`
  (`asyncio.TaskGroup`, R2).
- ✅ WebSocket (Opus): `ws/manager.py` (backpressure drop-oldest), `main.py`.
- ✅ Tests base verdes: `test_tag_cache.py`, `test_manager.py`,
  `test_models_and_registry.py` (**10 passed, 1 skipped**).
- ⏳ Pendiente de relleno económico: driver Modbus, simulador, API REST, tests de
  integración.

## TODO(econ) — asignables a modelos económicos

| # | Archivo | Tarea | Modelo sugerido |
|---|---|---|---|
| 1 | `backend/app/drivers/modbus_driver.py` | Implementar `connect/read_block/write_tag` con `pymodbus>=3.6,<4`. Agrupar por rango contiguo (§3.2). | Económico |
| 2 | `backend/app/drivers/modbus_sim.py` | Simulador Modbus TCP (`StartAsyncTcpServer`) con registros que cambian. | Económico |
| 3 | `backend/tests/conftest.py` | Fixture `modbus_sim` reutilizable (R6). | Económico |
| 4 | `backend/tests/test_modbus_driver.py` | Tests de integración (roundtrip, write→read, deadband end-to-end). | Económico |
| 5 | `backend/app/api/__init__.py` | Router REST F1: `POST /projects`, `GET /projects/current`, `GET /tags`; conectar `manager.on_tag_update` como suscriptor del TagCache y arrancar `runtime.run()`. | Económico (Sonnet para el wiring async) |

## Escenarios de test que define Opus (para que el económico los implemente)

- Driver: reconexión con backoff sin tumbar otros drivers (usar dos drivers, uno
  que falla) — valida `runtime._driver_scan_loop`.
- Integración WS: suscribir → recibir `tag_update` → saturar cola → recibir
  `overflow` (valida el camino completo §3.4).

## Cómo correr

```bash
pip install -e ".[dev]"
pytest -q            # 10 passed, 1 skipped hasta rellenar el driver
```
