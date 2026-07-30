# Continuación — retomar el proyecto en un chat nuevo

> Documento de handoff. Si este chat alcanza su límite, abre uno nuevo y usa el
> **prompt de arranque** de abajo. El repo es la fuente de verdad; no se pierde nada.

## Prompt para pegar en el chat nuevo

```
Estoy desarrollando la plataforma IIoT Open Source (GC052002/open-iiot-platform).
Lee en la rama main estos documentos para tener el contexto completo, en este orden:
1. PROJECT_CONTEXT.md  (visión híbrida + decisiones validadas Rev 7)
2. ARCHITECTURE.md     (decisiones de diseño, matriz §9)
3. ROADMAP.md          (fases; vamos por F2, con F2.0 ya completa)
4. REVIEW_TASKS.md     (historial de revisiones Gemini/GLM)
5. CONTINUATION.md     (este archivo)

Flujo de trabajo: yo (Claude/Opus) implemento fase por fase; GLM y Gemini son
revisores externos que critican cada fase y yo integro su feedback como "Rev N".
Desarrollo en la rama claude/open-iiot-platform-64k96b y mergeo a main al cerrar
cada bloque. Prioridad: avanzar con calidad y tests verdes, cuidando el presupuesto
de tokens (ver ROADMAP §0). Retomamos en F2.1 (persistencia SQLite + TagBuffer).
```

## Estado actual (2026-07-30)

- **F0** ✅ · **F1** ✅ (motor Modbus + WS, mergeado a main) · **F2.0** ✅ (núcleo multi-tenant)
- **Tests:** 26 verdes (`pytest -q`).
- **Ramas:** `main` tiene F0/F1 + docs; el trabajo de F2.0 está en
  `claude/open-iiot-platform-64k96b` (pendiente de abrir/mergear PR si se desea).

### Qué hay implementado (backend/app)
- `models/` — `Tag` (deadband), nodos discriminados, `Project` (unión discriminada,
  con `project_id`).
- `engine/` — `TagCache` (deadband + **orden temporal** + segmentado por `project_id`),
  `ScanScheduler` (neutro de protocolo), `Runtime` (`asyncio.TaskGroup`, backoff, `stop()`).
- `drivers/` — `BaseDriver` (async `write_tag`, `bind_tags`), `registry` (Factory),
  `modbus_driver` (real, lectura por bloques con límite PDU + decode por tipo), `modbus_sim`.
- `ws/` — `protocol` (contrato de mensajes, con `project_id`), `manager` (backpressure,
  routing por `(project_id, tag_id)`).
- `state.py` — `AppState` multi-tenant (un `Runtime`/`TaskGroup` por proyecto, TagCache
  compartido, ConnectionManager global).
- `api/` — `POST /projects`, `GET /projects`, `GET /projects/{id}`, `GET /tags?project_id=`.
- `main.py` — FastAPI + WS `/ws` + `/health` por proyecto.

## Próximo paso: F2.1 — Persistencia

- `storage/` con patrón **Repository** (abstrae el motor de BD).
- SQLite para air-gapped; PostgreSQL + **TimescaleDB** en despliegues con recursos
  (particionado por `project_id` + `time`).
- **`TagBuffer`**: suscriptor Observer del `TagCache` que acumula muestras y hace
  *flush* en batch (cada N s o M muestras) para no escribir 1 fila por lectura.
- Config/RBAC/audit en PostgreSQL (RBAC completo es F2.4).

## Decisiones ya cerradas que F2 debe respetar (no re-decidir)

- Ingesta híbrida: MQTT respeta el `ts` del Edge; `TagCache` descarta out-of-order
  (ya implementado); **LWT → `quality="bad"`** (pendiente, F2.2).
- Multi-tenant: un proceso; `TagCache` segmentado; `TaskGroup` por proyecto (hecho).
- Sandbox `LogicNode` (F3): `asteval` para cálculos; **WASM** (Wasmer/Extism) para
  Python real (Docker descartado por cold-start).
- Serializer WS: **JSON** en v1 (msgpack solo si el perfilado lo justifica).

## Cómo correr / probar

```bash
pip install -e ".[dev]"
pytest -q                                  # 26 passed
python -m app.drivers.modbus_sim &         # simulador Modbus :5020
uvicorn app.main:app                       # backend :8000
```
