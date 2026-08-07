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

## Rev 6 — Segunda revisión externa (Gemini + GLM), cierre de F1 · 2026-07-26

| # | Archivo | Issue | Estado |
|---|---|---|---|
| **BLOCKER 1** | modbus_driver.py | agrupación sin límite de PDU Modbus (>125 regs falla) y floats partidos entre peticiones (*tearing*) | ✅ `_group_contiguous_spans` (máx 120 regs, no parte spans) |
| **BLOCKER 2** | runtime.py | al cancelar, el `disconnect` no cerraba el socket → conexiones zombie en el PLC | ✅ `asyncio.shield` en `_safe_disconnect` |
| AJUSTE | ws/manager.py | orden del `OverflowMsg` | ✅ Revertido: overflow **antes** del dato (integridad cronológica de tendencias) |
| Diferido F3 | models/tag.py | deadband pct con `previous==0` satura el WS | ⏳ TODO anotado (se resuelve con los LogicNode en F3) |

Aceptado sin reabrir: `_notify` fuera del lock (T-M1), `TaskGroup`+`except*`+`_healthy`,
uniones discriminadas Pydantic. **F1 cerrada — 22 tests verdes.**

## Rev 8 — Revisión externa (Gemini + GLM) de F2.0 · 2026-07-30

| # | Archivo | Issue | Estado |
|---|---|---|---|
| **CRÍTICA** | tag_cache.py | orden temporal con `<=` descartaba polling de alta frecuencia con misma marca de reloj | ✅ Cambiado a `<` (solo estrictamente más viejo; deadband filtra el resto) |
| Apunte F2.1 | tag_cache.py | un único `_notify` haría que el historiador perdiera intermedios (solo delta) | ✅ Interfaz preparada: suscriptores **delta** (WebSocket) vs **raw** (TagBuffer) |
| Verificación | state.py | limpieza de referencias en `stop_project` | ✅ Confirmado: `pop` + `await task` + `drop_project` (sin fugas) |

Aceptado sin cambios: aislamiento por `Runtime`/`TaskGroup` real; sin condiciones de
carrera en `ConnectionManager` (event loop de un solo hilo). **F2.0 lista para merge — 27 tests verdes.**

## Rev 9 — Revisión externa (Gemini) de F2.1 · 2026-07-30

| # | Archivo | Issue | Estado |
|---|---|---|---|
| MEDIA | sqlite_repository.py | lecturas de `/history` vs escrituras batch → `database is locked` | ✅ `PRAGMA journal_mode=WAL` en `init()` |
| MEDIA | tag_buffer.py | un fallo transitorio de disco descartaba el batch (pérdida de telemetría) | ✅ Reencola el batch fallido (retry en el próximo flush; TODO cap en F2.4) |

Aceptado sin cambios: `ts` ISO8601 texto (ordenable, migra a `TIMESTAMPTZ` en F2.4);
índice `(project_id, tag_id, ts)`; diferir downsampling/retención a TimescaleDB;
interfaz `Repository` suficiente para enchufar `TimescaleHistorian`. **F2.1 lista para
merge — 35 tests verdes.**

## Rev 10 — Revisión externa (Gemini) de F2.2 · 2026-07-30

| # | Archivo | Issue | Estado |
|---|---|---|---|
| MEDIA | mqtt_driver.py | wildcard + múltiples Edge con la misma clave se cruzaban | ✅ `device_topic_index` → mapeo compuesto `{device_id}/{clave}` (fallback plano = 1 Edge/driver) |
| BAJA | mqtt_driver.py | QoS 0 por defecto (telemetría industrial) | ✅ `subscribe(..., qos=1)`; retained/QoS configurable → TODO F2.4 |
| F2.4 | mqtt_driver.py | contrato de escritura MQTT | ✅ Documentado: RPC over MQTT `iiot/edge/{device_id}/command/{tag_id}` + ack con timeout |

Aceptado sin cambios: unificación poll/push (`run` + connect/disconnect no-op),
shutdown limpio (`async with Client`), backoff ante `MqttError`. **F2.2 lista para merge — 44 tests verdes.**

## Rev 11 — Revisión externa (Gemini + GLM) de F2.3, previa a PLC real · 2026-07-30

| # | Archivo | Issue | Estado |
|---|---|---|---|
| **CRÍTICA** | s7_driver.py | bool leía siempre bit 0 → `DB1.DBX0.5` daría valor incorrecto | ✅ Direccionamiento S7 completo (`DBX byte.bit`, `DBB/DBW/DBD`); decode/write por bit (read-modify-write) |
| **CRÍTICA** | opcua_driver.py | mapeo NodeId podía no coincidir con la forma canónica → datos ignorados en silencio | ✅ `_handle_map` se completa en `run()` con `node.nodeid.to_string()` canónico |
| Mejora | plc_check.py | fallo de conexión sin pistas accionables | ✅ Mensajes por protocolo (S7: PUT/GET, DB no optimizado, rack/slot; OPC UA; Modbus; MQTT) |
| Checklist | DEMO.md | requisitos TIA Portal para hardware real | ✅ DBs no optimizados, PUT/GET, rack/slot (1500=0/0), puertos 102/4840 |

**F2.3 lista para PLC S7 físico — 55 tests verdes.**

## Rev 12 — Revisión externa (Gemini) de F2.4a + F2.4b · 2026-07-31

| # | Archivo | Issue | Estado |
|---|---|---|---|
| **CRÍTICA** | auth.py | modo anónimo:admin silencioso si falta `IIOT_USERS` | ✅ Fail-closed: anónimo solo con `IIOT_ALLOW_ANONYMOUS=true`; si no, 403 |
| **CRÍTICA** | crypto.py | clave Fernet efímera en prod invalida sesiones/credenciales al reiniciar | ✅ Fail-closed: `IIOT_FERNET_KEY` obligatoria (efímera solo en modo dev) |
| **CRÍTICA** | ws/manager.py + main.py | token descifrado en cada WriteMsg (latencia en el hot path) | ✅ Auth en el handshake (`?token=`); rol cacheado en `_Client`; los WriteMsg solo validan rol |
| Industrial | alarms/engine.py | flapping de alarmas al oscilar en el umbral | ✅ Campo `hysteresis` en `AlarmRule` + banda anti-rebote al despejar |
| Industrial | alarms/notifier.py | notificaciones perdidas por timeout / baneo 429 en ráfaga | ✅ `QueuedNotifier`: cola acotada + rate-limit + reintentos con backoff |

Aceptado sin cambios: audit en la BD del historiador (ok para air-gapped; separada en F4);
Fernet como token opaco (válido mientras sea monolítico). **F2.4 lista para merge — 74 tests verdes.**

## Rev 13 — Revisión externa (Gemini) de F2.4c · 2026-07-31

| # | Archivo | Issue | Estado |
|---|---|---|---|
| **CRÍTICA** | observability/metrics.py | contadores/gauges sin lock → carreras con drivers en `to_thread` | ✅ `threading.Lock` en inc/set/render (instantánea bajo lock) |
| **CRÍTICA** | mqtt_driver.py / opcua_driver.py | drivers push no pasan por `BaseDriver.run` → métricas en cero | ✅ `iiot_driver_messages_received_total` + `iiot_driver_last_message_ts` en sus bucles/callbacks |

Aceptado sin cambios: implementación propia vs `prometheus_client` (histogramas p95/p99 en F4);
`/metrics` abierto (proxy/puerto dedicado en F4); regla de cardinalidad (NUNCA `tag_id`/`address`
como label). **F2.4c lista para merge — 80 tests verdes. Fase 2.4 completa.**

## F3.0 — Frontend: scaffold + conexión (Opus) · 2026-08-02

Primer bloque de la Fase 3. Frontend `frontend/` (React + TS + Vite + @xyflow/react +
Zustand) que consume el contrato WS/REST ya fijado, sin renegociarlo.

- Cliente **REST** tipado (`src/api/rest.ts`) + cliente **WS** con reconexión
  (backoff+jitter) y **re-suscripción** al reconectar (`src/api/ws.ts`).
- Store de tags en tiempo real (reducer puro `applyTagValues`), sesión persistida en
  `localStorage`, login opcional (auth opt-in del backend).
- UI: login, barra de conexión, **tabla de tags en vivo** con sparkline, canvas React
  Flow (esqueleto con las 3 familias de nodos).
- **24 tests Vitest verdes** (helpers WS, reducer del store, cliente REST con fetch
  mockeado, reconexión/re-suscripción del `WsClient`, render de la tabla).

**Bugfix del backend descubierto al integrar (verificación e2e REST+WS contra el
simulador Modbus):**

| # | Archivo | Issue | Estado |
|---|---|---|---|
| **CRÍTICA** | ws/manager.py | `_Client` era un `@dataclass` (eq=True) → **unhashable**, pero se usa como clave de `set`/`dict` de enrutado (`_clients`, `_subs`, `per_client`). El WS lanzaba `TypeError` en `connect()` y **cerraba toda conexión** en runtime. Los tests solo cubrían `_enqueue`, nunca `connect`/`subscribe`, así que no se detectó. | ✅ `@dataclass(eq=False)` (identidad por objeto) + regresión: test de hashabilidad y del camino real `connect→subscribe→on_tag_update`. |

**F3.0 lista para merge — backend 82 tests verdes · frontend 24 tests verdes.**

## F3.1 — Frontend: paleta + canvas editable + inspector (Opus) · 2026-08-07

Segundo bloque de la Fase 3. Editor visual sobre el scaffold de F3.0. Sin cambios en
el backend (el editor es 100% cliente).

- **Modelo uniforme del editor** (`src/editor/model.ts`): un solo `EditorNodeData`
  (`kind`/`subtype`/`params`) para los tres tipos de nodo → la paleta, el store, los
  nodos custom y el inspector no duplican la lógica de config/params/props.
- **Mapping puro** (`src/editor/mapping.ts`): `toProjectNode`/`fromProjectNode`/
  `buildProject` expanden/colapsan al contrato del backend (`models/node.py`).
  Round-trip idempotente probado (deja F3.3 import/export casi hecho).
- **projectStore** (Zustand + persist): nodes/edges/selección/meta, acciones
  add/update/remove/onChanges/onConnect; diseño persistido en `localStorage`.
- **Paleta arrastrable** (HTML5 DnD) → **canvas editable** (`screenToFlowPosition`
  al soltar, conectar, seleccionar, borrar con Supr) → **inspector** (label, subtipo
  que reinicia params, params tipados número/booleano/texto + editor JSON avanzado).
- **39 tests Vitest verdes** (24 previos + 15: paleta/createNode, mapping+round-trip,
  projectStore, inspector render/edición). `tsc` + `vite build` limpios.
- Verificación visual (Playwright): arrastrar 3 nodos, seleccionar y editar params.
- Menor: favicon SVG añadido (elimina el 404 de `/favicon.ico`).

**F3.1 lista para merge — frontend 39 tests verdes · backend sin cambios (82).**

## Rev 14 — Revisión externa (Gemini + GLM) de F3.0 + F3.1 · 2026-08-07

Revisión consolidada de la Fase 3. La arquitectura base (modelo uniforme, WS singleton,
mapping puro, `@dataclass(eq=False)`) se validó como correcta. Hallazgos integrados:

| # | Severidad | Archivo | Issue | Estado |
|---|---|---|---|---|
| 1 | **BLOCKER** | api/ws.ts · connection.ts | Pérdida **silenciosa** de comandos de escritura: si el WS reconecta, `write()` devolvía void y el setpoint se evaporaba sin avisar (crítico en SCADA). | ✅ `WsClient.write()` devuelve `bool` + `isOpen()`; `ConnectionController.write()` **rechaza** el comando y lo hace visible (`connectionStore.setError`) si el socket no está abierto. |
| 2 | **BLOCKER** | store/projectStore.ts | Spam de escritura a `localStorage`: React Flow emite un cambio por píxel arrastrado; el `persist` síncrono congelaba el navegador. | ✅ `storage` con **debounce** (500 ms, agrupa y vuelca en calma) vía `createJSONStorage(debouncedStorage)`. |
| 3 | MEDIA | api/ws.ts | Token expirado → **bucle infinito** de reconexiones fallidas. | ✅ `onclose` detecta códigos de auth (1008/4001/4401) → `onAuthError` (no reconecta); `ConnectionController` fuerza logout (`clearSession`) + aviso. |
| 4 | MEDIA | store/projectStore.ts | Persistía estado transitorio de UI (`selected`/`dragging`/`width`) → nodo "bloqueado" al recargar. | ✅ `partialize` con `sanitizeNodes` (solo `id`/`type`/`position`/`data`). |
| 5 | MEDIA | editor/model.ts | `coerceLike` infería el tipo del **valor actual**: un param `null` degradaba a string y rompía el tipado del backend. | ✅ **Esquema de tipos** `PARAM_TYPES` + `paramType()`/`coerceValue()` (el esquema manda; el valor solo es fallback). |
| 6 | BAJA | api/ws.ts | `onerror` forzaba `ws.close()` → posible doble cierre. | ✅ `onerror` vacío (log); toda la limpieza/reconexión vive en `onclose`. |
| 7 | BAJA | api/ws.ts | Token en la URL del WS (queda en logs si no hay TLS). | ✅ Documentado: **producción exige WSS**; mover a frame de handshake se difiere (cambiaría el contrato backend, hoy `?token=`). |

Aceptado sin reabrir (validado como correcto por los revisores): modelo uniforme
`EditorNodeData`, `ConnectionController` singleton, backoff+jitter+re-suscripción,
y el bugfix `@dataclass(eq=False)`. **F3.0+F3.1 con Rev 14 — frontend 46 tests verdes ·
backend 82.**

## F3.2 — Frontend: widgets HMI + data-binding por tag_id (Opus) · 2026-08-07

Tercer bloque de la Fase 3. Los widgets del canvas ahora **leen el valor en vivo**.
Sin cambios en el backend.

- `editor/widgets.tsx`: helpers puros `tankFillPct` (nivel 0..100 en rango min/max) y
  `valveState` (open/closed/unknown desde bool/número/string) + `WidgetBody`, que se
  suscribe al `tagStore` por `props.tag_id` y pinta según el subtipo: **tanque** (fill),
  **válvula** (indicador de estado), **gráfico** (sparkline de la tendencia).
- `editor/nodeTypes.tsx`: el nodo widget delega en `WidgetBody` (los otros kinds
  mantienen el resumen de params).
- `editor/model.ts`: `defaultParams` por subtipo de widget (tank → min/max; valve →
  open_value); `PARAM_TYPES` amplía min/max/open_value.
- `components/Inspector.tsx`: para widgets, `tag_id` es un **select de los tags en vivo**
  (snapshot REST de `connectionStore`), con fallback a texto para tags no presentes.
- **53 tests verdes** (46 previos + 7: tankFillPct, valveState, render del widget con
  valor en vivo del store). `tsc` + `vite build` limpios.
- Verificación visual e2e (Playwright + backend + simulador Modbus): conectar → soltar
  un tanque → enlazarlo a `nivel` → el widget refleja el valor en vivo.
- El origen del dato es indiferente (Modbus/MQTT/S7/OPC UA): sólo importa el `tag_id`.

**F3.2 lista para merge — frontend 53 tests verdes · backend 82.**

## R7 — Compatibilidad de Python (techo <3.14) · 2026-08-07

Reportado desde una prueba en Windows con Python 3.14 (backend daba 500 / no arrancaba).
Reproducido en 3.14.0rc2: **Pydantic 2.13.4 (la última) rompe al importar en 3.14** —
`AssertionError` en `pydantic/_internal/_typing_extra.py:eval_type_backport` (PEP 649
cambia el manejo de anotaciones y el fallback de Pydantic asume `typing.ForwardRef`).
Sin release de Pydantic que lo arregle aún. Verificado **OK en 3.11/3.12/3.13**.

| # | Archivo | Issue | Estado |
|---|---|---|---|
| R7 | pyproject.toml | Python 3.14 rompe el stack FastAPI/Pydantic (falla al importar → 500/arranque). | ✅ `requires-python = ">=3.11,<3.14"` (falla en el install con mensaje claro, no en runtime) + documentado en CONTINUATION/DEMO. Se subirá el techo cuando Pydantic soporte 3.14. |

Decisión alineada con §0.6 (precedente del pin de pymodbus): no pelear con una librería
en transición; fijar versión soportada y seguir.

## Cómo correr

```bash
pip install -e ".[dev]"
pytest -q            # 14 passed
# demo manual:
python -m app.drivers.modbus_sim &          # simulador en :5020
uvicorn app.main:app --reload               # backend en :8000
```
