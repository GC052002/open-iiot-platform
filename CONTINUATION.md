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

- **F0** ✅ · **F1** ✅ · **F2.0** ✅ · **F2.1** ✅ · **F2.2** ✅ · **F2.3** ✅ — **todo mergeado a `main`** (PRs #1–#9).
- **Tests:** 55 verdes (`pytest -q`).
- **Revisiones integradas:** Rev 1–11 (Gemini + GLM).
- **Demo / PLC real:** ver `DEMO.md` (runbook S7/Modbus/OPC UA + checklist TIA Portal) y
  el preflight `python -m app.tools.plc_check`.
- **Siguiente:** F2.4 — seguridad (Fernet/RBAC/audit) + alarmas + métricas Prometheus.
- **Ramas:** `main` tiene F0–F2.0; F2.1 está en `claude/open-iiot-platform-64k96b`.
  La rama de trabajo se reinicia desde `main` al empezar cada bloque nuevo.

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

## Próximo paso: F2.4 — Seguridad + valor añadido

- **Seguridad:** cifrado **Fernet** de credenciales (clave externa vía env/SOPS, §3.5/§10.4);
  **RBAC** por proyecto (admin/engineer/operator/viewer) impuesto en el backend; **audit log**
  transaccional de escrituras (quién/cuándo/anterior→nuevo) en el patrón Command (§3.6).
- **Alarmas:** motor de alarmas como **suscriptor delta** del `TagCache` (evalúa umbrales)
  + notificación (Telegram/SMTP).
- **Observabilidad:** `observability/metrics.py` (Prometheus `/metrics`) + `health.py`
  granular por driver.
- **Deudas anotadas para F2.4:** escritura MQTT (RPC over MQTT, contrato ya en el docstring),
  QoS/retained MQTT configurable, cap del buffer de reintento del `TagBuffer`.

### Ya hecho (arquitectura relevante)
- **Drivers (F2.3):** S7 (polling, snap7 en to_thread, `DB{n}.{offset}`) y OPC UA (push,
  asyncua subscriptions). D-M4: agrupación por bloques en `drivers/blockutil.py` (Modbus+S7).
- **Unificación poll/push (F2.2):** `BaseDriver.run(publish, stopping)`; el Runtime aporta
  `publish` y el wrapper connect/backoff/disconnect.
- **Ingesta híbrida (F2.2):** `mqtt_driver.py` publica al mismo `TagCache`; respeta `ts`
  del Edge; LWT → bad; `device_topic_index` para múltiples Edge.
- **Persistencia (F2.1):** `storage/` Repository + `SQLiteHistorian` (WAL) + `TagBuffer`
  raw (batch + retry). `GET /history`.

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
