# Continuación — retomar el proyecto en un chat nuevo

> Documento de handoff. Si el chat alcanza su límite, abre uno nuevo y pega el
> **prompt de arranque** de abajo. El repo (`main`) es la fuente de verdad; no se
> pierde nada.

## Prompt para pegar en el chat nuevo

```
Estoy desarrollando una plataforma IIoT/SCADA Open Source (repo GitHub:
GC052002/open-iiot-platform). Continúa el trabajo desde donde quedó.

ACCESO A GITHUB (importante): trabajamos sobre GC052002/open-iiot-platform.
- Si el repo no está en el scope de esta sesión, añádelo con la herramienta add_repo
  (o list_repos para verlo). Clónalo si hace falta.
- Los cambios se hacen con git (push/pull van por el proxy de la sesión) y los PRs con
  las herramientas mcp__github__* (create_pull_request / merge_pull_request).
- Rama de trabajo: claude/open-iiot-platform-64k96b. Se REINICIA desde main al empezar
  cada bloque nuevo (git fetch origin main && git checkout -B <rama> origin/main).

PONTE AL DÍA leyendo en la rama main, en este orden:
1. CONTINUATION.md   (este archivo: estado, siguiente paso, cómo correr)
2. PROJECT_CONTEXT.md (visión: ingesta híbrida Modbus/MQTT/S7/OPC UA, multi-tenant)
3. ARCHITECTURE.md    (decisiones de diseño; matriz de decisiones §9)
4. ROADMAP.md         (fases; vamos a empezar F3)
5. REVIEW_TASKS.md    (historial de revisiones Rev 1–13 de Gemini/GLM)

FLUJO DE TRABAJO:
- Yo (Claude/Opus) implemento fase por fase, con tests verdes, y mergeo a main vía PR
  al cerrar cada bloque. Actualizo este CONTINUATION.md tras cada merge.
- GLM y Gemini son revisores externos: el usuario me trae su feedback y yo lo integro
  como "Rev N" antes de mergear (o después si ya mergeé un bloque autocontenido).
- Prioridad: calidad + modularidad + tests, cuidando el presupuesto de tokens.

ESTADO: Fase 2 COMPLETA (backend industrial). SIGUIENTE: F3 (frontend visual, canvas
HMI tipo WinCC/Node-RED). Empieza por F3.0 (scaffold React + React Flow + conexión al
backend), o propón primero un mini-diseño de F3 si lo ves necesario.
```

## Estado actual (2026-08-02)

- **Fase 2 COMPLETA.** F0 ✅ · F1 ✅ · F2.0–F2.3 ✅ · monitor web ✅ · **F2.4** (alarmas +
  seguridad + observabilidad) ✅ — todo en `main`.
- **Fase 3 EN CURSO. F3.0 ✅ · F3.1 ✅**
  - **F3.0** (scaffold + conexión WS/REST): `frontend/` (React + TS + Vite +
    @xyflow/react + Zustand), tabla de tags en vivo, cliente WS con reconexión/
    re-suscripción, login opcional, persistencia local. **Bugfix backend:** `_Client`
    unhashable rompía el WS (ver `REVIEW_TASKS.md` → F3.0).
  - **F3.1** (editor visual): paleta arrastrable + canvas editable + inspector de
    propiedades; modelo uniforme del editor con mapping puro (round-trip) a los
    `DriverNode/LogicNode/WidgetNode` del backend; diseño persistido en `localStorage`.
- **Tests:** backend **82 verdes** (`pytest -q`) · frontend **46 verdes** (`npm test`).
- **Revisiones integradas:** Rev 1–14 (Gemini + GLM). **Rev 14** endureció F3.0/F3.1:
  escritura de comandos sin pérdida silenciosa, persistencia con debounce + sin estado
  transitorio, logout al expirar la sesión, esquema de tipos en el inspector.
- **Siguiente:** **F3.2** — widgets HMI (tanque/válvula/gráfico) con **data-binding por
  `tag_id`** (usar el contrato WS ya fijado; el origen del dato es indiferente).

## Cómo acceder a GitHub (para el agente del chat nuevo)

- Repo: `GC052002/open-iiot-platform`. Rama principal: `main`. Rama de trabajo:
  `claude/open-iiot-platform-64k96b`.
- Si el repo no está en scope: usar `add_repo` (owner=GC052002, repo=open-iiot-platform)
  y clonar. `list_repos` lo lista si hace falta descubrirlo.
- Commits/push con `git` (proxy de la sesión). PRs y merges con `mcp__github__*`.
- Regla de ramas: reiniciar la rama de trabajo desde `main` al empezar cada bloque
  (`git fetch origin main && git checkout -B claude/open-iiot-platform-64k96b origin/main`),
  implementar, `git push -u origin <rama>`, abrir PR a `main` y mergear.

## Cómo correr / probar (Linux)

```bash
pip install -e ".[dev]"          # + asegúrate de tener 'cryptography' funcional
pytest -q                         # 80 passed
# Demo/dev (seguridad fail-closed → requiere el flag):
export IIOT_ALLOW_ANONYMOUS=true
python -m app.drivers.modbus_sim &        # simulador Modbus TCP :5020
uvicorn app.main:app --port 8000          # backend + historiador SQLite (WAL)
# Navegador: http://localhost:8000/ (monitor en vivo) · /docs (Swagger) · /metrics
```
Para conectar a un PLC real (S7/Modbus/OPC UA) ver `DEMO.md` (runbook + preflight
`python -m app.tools.plc_check` + checklist TIA Portal).

**Frontend (F3, `frontend/`):**
```bash
cd frontend && npm install
npm run dev        # http://localhost:5173 (proxy a http://localhost:8000)
npm test           # 24 tests verdes
npm run build      # type-check + build a dist/ (se sirve desde el backend en prod)
```
Con el backend arriba y un proyecto cargado (`POST /projects`), pulsar «Conectar» en
la UI muestra los tags en vivo. Ver `frontend/README.md`.

## Qué hay implementado (backend/app) — Fase 2 completa

- `models/` — `Tag` (deadband), nodos discriminados por `type`, `Project` (unión
  discriminada por `schema_version`, con `project_id` y `alarms`), `AlarmRule` (con `hysteresis`).
- `engine/` — `TagCache` (deadband + orden temporal + segmentado por `project_id` +
  suscriptores delta/raw), `ScanScheduler` (neutro de protocolo), `Runtime`
  (`asyncio.TaskGroup`, backoff, `stop()`).
- `drivers/` — `BaseDriver.run(publish, stopping)` unifica polling y push; `registry`
  (Factory); `modbus_driver` (PDU + decode por tipo), `s7_driver` (snap7 en to_thread,
  DBX/DBB/DBW/DBD), `opcua_driver` (asyncua subscriptions), `mqtt_driver` (aiomqtt, LWT,
  device_topic_index), `blockutil` (D-M4), `modbus_sim`.
- `storage/` — `HistorianRepository` + `SQLiteHistorian` (WAL) + `TagBuffer` (raw, batch,
  retry) + tabla `audit`.
- `alarms/` — `AlarmEngine` (delta, histéresis) + `Notifier` (Log/Telegram/SMTP) +
  `QueuedNotifier` (cola, rate-limit, reintentos).
- `security/` — `crypto` (Fernet, fail-closed), `rbac` (roles + PBKDF2), `auth` (opt-in),
  `context`.
- `observability/` — `metrics` (registro thread-safe → Prometheus).
- `ws/` — `protocol` (mensajes con `project_id`, token), `manager` (backpressure, routing,
  auth cacheada en handshake).
- `state.py` — `AppState` multi-tenant (Runtime/TaskGroup por proyecto; TagCache y
  ConnectionManager globales; historiador; alarmas; métricas).
- `api/` — `/login`, `/projects` (POST/GET), `/projects/{id}`, `/tags`, `/history`,
  `/alarms`, `/audit`, con RBAC. `main.py` — WS `/ws`, `/health`, `/health/drivers`,
  `/metrics`, dashboard `/`.
- `tools/plc_check.py` — preflight de conectividad a PLC real.

## Próximo paso: F3.2 — Widgets HMI + data-binding por `tag_id`

Bloque grande; partir en sub-fases (como F2):
- **F3.0** ✅ — scaffold + store de tags + cliente WS/REST + login + persistencia local.
- **F3.1** ✅ — paleta arrastrable + canvas editable + inspector. El editor produce el
  JSON del backend vía `src/editor/mapping.ts` (`buildProject`), listo para F3.3.
- **F3.2** ← **siguiente** — widgets HMI (tanque, válvula, gráfico) que **leen el valor
  en vivo** del `tagStore` por su `props.tag_id` (ya editable en el inspector). Base:
  `src/editor/nodeTypes.tsx` (nodo widget) + `src/store/tagStore.ts` (valores en vivo).
  Nota: aún no hay UI para **definir Tags** (los data points): en F3.2/F3.3 hay que
  añadir un editor de tags (id/driver/address) para que `POST /projects` tenga qué leer.
- **F3.2** — widgets HMI (tanque, válvula, gráfico) con **data binding por `tag_id`**
  (usar el contrato WS ya fijado; el origen del dato es indiferente).
- **F3.3** — import/export del JSON de proyecto (mismo `schema_version` que el backend)
  + `LogicNode` con sandbox (**asteval** para cálculos; **WASM** Wasmer/Extism para
  Python real — Docker descartado por cold-start).

## Decisiones cerradas (no re-decidir)

- Ingesta híbrida: MQTT respeta el `ts` del Edge; `TagCache` descarta out-of-order (`<`);
  LWT → `quality="bad"`. Multi-tenant: un proceso; `TaskGroup` por proyecto.
- Serializer WS: **JSON** en v1. Seguridad **fail-closed**: dev/demo necesita
  `IIOT_ALLOW_ANONYMOUS=true`; prod define `IIOT_FERNET_KEY` (+ `IIOT_USERS` para RBAC).
- Métricas: labels solo `driver`/`node` (nunca `tag_id`/`address`).
- Diferido a F4: Redis (escala multi-worker), ABAC/Casbin, Vault, entry_points de drivers,
  Sparkplug B (flag ya diseñado), TimescaleDB, tracing OTel, escritura MQTT (RPC over MQTT).
