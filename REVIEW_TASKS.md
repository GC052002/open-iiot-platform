# Guía de revisión por fases

> **Flujo de trabajo del proyecto:**
> - **Claude (Opus)** implementa el código **fase por fase**.
> - **GLM y Gemini** actúan como **revisores/críticos**: sobre cada fase entregada,
>   proponen mejoras, alternativas y puntos para hacer el sistema más fluido.
> - Las mejoras aceptadas se integran como una nueva "Rev N" en `ARCHITECTURE.md`
>   / `ROADMAP.md` y luego en el código.
>
> Todo el trabajo vive en la rama `claude/open-iiot-platform-64k96b` (PR #1, sin
> mergear a `main`), que es donde los revisores lo ven.

## Estado por fase

| Fase | Estado | Notas |
|---|---|---|
| **F0 Fundaciones** | ✅ Completa | `pyproject.toml`, estructura, `docker-compose` + simulador Modbus |
| **F1 Núcleo del motor** | ✅ **Completa y verde** | MVP end-to-end: Modbus→TagCache→WS. **14 tests pasan** |
| F2 Drivers reales + persistencia + observabilidad | ⏳ Siguiente | S7, OPC UA, MQTT; SQLite/TagBuffer; alarmas; métricas |
| F3 Frontend canvas | ⏳ | React + React Flow contra el contrato WS ya fijado |
| F4 Escalado/multi-tenant | ⏳ (diferible) | Redis, Casbin, Vault, entry_points, Sparkplug |
| F5 Empaquetado | ⏳ | compose por modo de red |

## Qué entregó la Fase 1 (para revisar)

**Núcleo (Opus):**
- `models/` — `Tag` (deadband R4), nodos discriminados por `type`, `Project` como
  unión discriminada por `schema_version` (R5).
- `ws/protocol.py` — contrato de mensajes WS (R1). `ws/manager.py` — backpressure
  drop-oldest (§3.4).
- `drivers/base.py` (con `write_tag` async), `drivers/registry.py` (Factory + decorador).
- `drivers/modbus_driver.py` — driver real (lectura por bloques contiguos, §3.2).
- `drivers/modbus_sim.py` — simulador Modbus TCP para dev/CI (R6).
- `engine/tag_cache.py` (deadband + copy-on-write R3), `scan_scheduler.py` (neutro
  de protocolo), `runtime.py` (`asyncio.TaskGroup` R2).
- `api/` — REST F1 (`POST /projects`, `GET /projects/current`, `GET /tags`).
- `main.py` — FastAPI + WebSocket `/ws` + lifespan.

**Tests (14 verdes):** deadband abs/pct, backpressure, unión discriminada, registry,
agrupación contigua, roundtrip driver↔simulador, y **end-to-end** API→runtime→tags.

## Foco sugerido para los revisores (GLM / Gemini) sobre F1

- `engine/runtime.py`: ¿el manejo de backoff/reconexión y el `TaskGroup` cubren
  bien el shutdown y el fallo aislado por driver?
- `engine/tag_cache.py`: ¿la política copy-on-write + notificación es correcta bajo
  writers concurrentes marshalados al loop (R3)?
- `ws/manager.py`: ¿el drop-oldest y el `OverflowMsg` son la semántica deseada?
- `drivers/modbus_driver.py`: ¿la agrupación por rangos contiguos y el mapeo de
  direcciones es razonable para escalar a S7/OPC UA en F2?

## Rev 5 — Resultado de la revisión externa (Gemini) de F1 · 2026-07-26

Revisión del commit `01cecf2` (F1). Veredicto: mergeable; 2 críticos que solo se
manifiestan con PLC real (no con el simulador). **Todo lo accionable se corrigió**;
lo pesado orientado a F2 se difiere de forma documentada.

| # | Archivo | Issue | Estado |
|---|---|---|---|
| **R-H1** | runtime.py | `stop()` no cancelaba el TaskGroup → shutdown colgado | ✅ Corregido (guarda tareas y las cancela; `health()`) |
| **D-H2** | modbus_driver.py | cliente sin timeout → PLC black-hole congela el scan loop | ✅ Corregido (`timeout=3`, `retries`, `reconnect_delay`) |
| R-M1 | runtime.py | `sleep(poll_rate)` no interrumpible | ✅ Corregido (`_sleep_or_stop`) |
| R-M2 | runtime.py | runtime moría en silencio, `/health` seguía ok | ✅ Corregido (`_healthy` + `/health` real) |
| T-M1 | tag_cache.py | `_notify` dentro del lock | ✅ Ya estaba fuera del lock; solo se ajustó el docstring |
| T-M2 | tag_cache.py | `set_tags` no limpiaba huérfanos | ✅ Corregido |
| W-M1 | ws/manager.py | orden `OverflowMsg` antes del dato | ✅ Corregido (dato primero) |
| W-m1 | ws/manager.py | `disconnect` no vaciaba la cola | ✅ Corregido |
| D-M3 | modbus_driver.py | ignoraba `data_type` (registro crudo) | ✅ Corregido (`_decode` int/bool/float32/string + ancho de registro) |
| D-m2 | modbus_driver.py | `int(address)` sin try/except | ✅ Corregido (marca `bad`, no crashea) |
| W-M2 | ws/manager.py | sin coalescing de `TagUpdateMsg` | ⏳ Diferido a F2 (TODO en código; no afecta a F1) |
| D-M4 | base.py | plantilla `read_block` no extraída para S7/OPC UA | ⏳ Diferido a F2 (ver ARCHITECTURE §9): generalizar con 2 drivers reales evita abstracción especulativa |

Tests añadidos (`test_rev5_fixes.py`): decode float/bool/int, dirección no numérica,
y shutdown determinista con `stop()`. **Suite: 19 tests verdes.**

## Cómo correr

```bash
pip install -e ".[dev]"
pytest -q            # 14 passed
# demo manual:
python -m app.drivers.modbus_sim &          # simulador en :5020
uvicorn app.main:app --reload               # backend en :8000
```
