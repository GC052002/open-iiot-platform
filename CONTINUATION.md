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
- Rama de trabajo: la que asigne la sesión (p. ej. claude/open-iiot-platform-XXXX).
  Se REINICIA desde main al empezar cada bloque nuevo
  (git fetch origin main && git checkout -B <rama> origin/main).

PONTE AL DÍA leyendo en la rama main, en este orden:
1. CONTINUATION.md   (este archivo: estado, siguiente paso, cómo correr)
2. PROJECT_CONTEXT.md (visión: ingesta híbrida Modbus/MQTT/S7/OPC UA, multi-tenant)
3. ARCHITECTURE.md    (decisiones de diseño; matriz de decisiones §9)
4. ROADMAP.md         (fases; Fase 3 COMPLETA, empezamos Fase 4)
5. REVIEW_TASKS.md    (historial de revisiones Rev 1–16 de Gemini/GLM)
6. docs/PHASE4_DESIGN.md (DISEÑO CERRADO de la Fase 4 — leer §8 "Rev D1")
7. docs/PHASE4_IMPL_PLAN.md (GUÍA DE EJECUCIÓN: 3 lotes, archivo/endpoint/test — SEGUIR)

FLUJO DE TRABAJO:
- Yo (Claude/Opus) implemento fase por fase, con tests verdes, y mergeo a main vía PR
  al cerrar cada bloque. Actualizo este CONTINUATION.md tras cada merge.
- GLM y Gemini son revisores externos: el usuario me trae su feedback y yo lo integro
  como "Rev N" antes de mergear (o después si ya mergeé un bloque autocontenido).
- Prioridad: calidad + modularidad + tests, cuidando el presupuesto de tokens.

ESTADO: Fase 3 COMPLETA (frontend visual funcional end-to-end) y probada en Windows.
El DISEÑO de la Fase 4 está CERRADO (docs/PHASE4_DESIGN.md, con Rev D1 de GLM/Gemini
integrada). SIGUIENTE: implementar Fase 4, empezando por F4.0 (usuarios persistidos en
BD + API/UI de gestión de usuarios). Orden post-D1: F4.0 → F4.1 (proyectos persistidos
+ permisos por proyecto + middleware de autorización por project_id) → F4.1c (secretos:
credential_id, credenciales de PLC fuera del JSON) → F4.1b (publicación Plantilla→Entrega
como snapshot inmutable + versionado) → F4.2 (visor HMI responsive del cliente) → F4.3
(reportes/consumo) → F4.4 (egress a terceros). Implementa por sub-fase con tests verdes
y mergea a main vía PR. Python soportado 3.11–3.13 (NO 3.14, ver R7).

EJECUCIÓN OPTIMIZADA (para gastar menos tokens sin bajar calidad): sigue
docs/PHASE4_IMPL_PLAN.md — agrupa en 3 LOTES (A backend identidad/permisos/secretos/
publicación · B frontend gestión+visor cliente · C reportes+egress), 1 PR por lote,
verifica con tests (pytest/vitest) y deja UNA sola captura e2e al final del Lote B.
Actualiza docs una vez por lote. Cada lote mergeado es coherente y revisable por sí solo.
```

## Estado actual (2026-08-10) — Fase 4, Lotes A y B COMPLETOS

- **Lote B de la Fase 4 implementado** (frontend): **B1** login con `role_global` + enrutado
  por rol (editor vs visor, forzable por hash `#/edit`/`#/view`), **B2** gestión de usuarios
  (admin, `UsersPanel`), **B3** gestor de proyectos (`ProjectsPanel`: listar/abrir/miembros/
  publicar), **B4** **visor HMI del cliente** responsive (`views/Viewer.tsx`, modo Runtime
  solo-lectura + setpoints `writable` + export CSV). Enablers backend: `Tag.writable`,
  `/tags` expone `writable`/`unit`, `/login` devuelve `role`.
- **Tests: backend 134 · frontend 77** (66→77, +11). `tsc` + `vite build` limpios.
- **Pendiente (no bloqueante):** 1 captura e2e Playwright del recorrido completo.
- **Siguiente:** **Lote C** (reportes de consumo F4.3 + egress a terceros F4.4). Ver
  `docs/PHASE4_IMPL_PLAN.md`.

## Estado (2026-08-10) — Fase 4, Lote A COMPLETO

- **Lote A de la Fase 4 implementado** (backend): **F4.0** (usuarios persistidos en BD +
  API `/users`), **F4.1** (proyectos persistidos + `project_members` + **autorización
  server-side por `project_id`** en REST y WS), **F4.1c** (secretos fuera del JSON:
  `credential_id` + KEK Fernet + resolución de `{"$secret": ...}` en `start_project`) y
  **F4.1b** (publicación Plantilla→Entrega: snapshot inmutable + `delivery_version`).
- **BD de configuración separada** `iiot_config.db` (env `IIOT_CONFIG_DB`), patrón
  Repository (`storage/config_repository.py` + `SQLiteConfigRepository`), mismo estilo WAL
  que el historiador. Ver `REVIEW_TASKS.md` → «Fase 4 — Lote A».
- **Tests: backend 134 verdes** (113→134, +21) · frontend 66 (sin cambios en Lote A).
- **Siguiente:** **Lote B** (frontend: gestión de usuarios/proyectos + visor HMI del
  cliente en modo Runtime + setpoints `writable` + export). Luego **Lote C** (reportes +
  egress). Ver `docs/PHASE4_IMPL_PLAN.md`.

## Estado anterior (2026-08-09)

- **Fase 2 COMPLETA.** F0 ✅ · F1 ✅ · F2.0–F2.3 ✅ · monitor web ✅ · **F2.4** (alarmas +
  seguridad + observabilidad) ✅ — todo en `main`.
- **Fase 3 COMPLETA. F3.0–F3.4 ✅** (scaffold+conexión, editor, widgets en vivo, proyecto
  completo, y `LogicNode` sandbox). Frontend visual funcional end-to-end.
  - **F3.0** (scaffold + conexión WS/REST): `frontend/` (React + TS + Vite +
    @xyflow/react + Zustand), tabla de tags en vivo, cliente WS con reconexión/
    re-suscripción, login opcional, persistencia local. **Bugfix backend:** `_Client`
    unhashable rompía el WS (ver `REVIEW_TASKS.md` → F3.0).
  - **F3.1** (editor visual): paleta arrastrable + canvas editable + inspector de
    propiedades; modelo uniforme del editor con mapping puro (round-trip) a los
    `DriverNode/LogicNode/WidgetNode` del backend; diseño persistido en `localStorage`.
  - **F3.2** (widgets en vivo): widgets HMI (tanque/válvula/gráfico) que **leen el valor
    en vivo** del `tagStore` por `props.tag_id`; binding en el inspector como select.
  - **F3.3** (proyecto completo): **editor de Tags** (data points), **import/export** del
    JSON (round-trip probado) y botón **Enviar al backend** (`POST /projects` + conectar).
    Lazo diseño→datos en vivo cerrado y verificado e2e.
- **Tests:** backend **113 verdes** (`pytest -q`) · frontend **66 verdes** (`npm test`).
- **Revisiones integradas:** Rev 1–16 (Gemini + GLM) + R7. **Rev 16** endureció el sandbox
  del LogicNode (allowlist de AST, offload a thread+timeout, detección de ciclos).
- **Probado end-to-end en Windows** (Python 3.13): diseñar → tags → LogicNode → widget en
  vivo → enviar → export/import. **Rama 2 (IOT2050/MQTT) validada** (`tools/mqtt_demo/`:
  broker + edge_sim). **Diseño de la Fase 4 CERRADO** (`docs/PHASE4_DESIGN.md` + Rev D1).
- **Siguiente:** implementar **Fase 4** (plataforma multiusuario + entrega a cliente),
  empezando por **F4.0** (usuarios persistidos + gestión de usuarios). Ver el orden
  post-D1 en el prompt de arranque de arriba y en `docs/PHASE4_DESIGN.md §8.3`.

## Cómo acceder a GitHub (para el agente del chat nuevo)

- Repo: `GC052002/open-iiot-platform`. Rama principal: `main`. Rama de trabajo: la que
  asigne la sesión (reiniciada desde `main` cada bloque).
- Si el repo no está en scope: usar `add_repo` (owner=GC052002, repo=open-iiot-platform)
  y clonar. `list_repos` lo lista si hace falta descubrirlo.
- Commits/push con `git` (proxy de la sesión). PRs y merges con `mcp__github__*`
  (`create_pull_request` / `merge_pull_request`, owner=GC052002, repo=open-iiot-platform).
- Regla de ramas: reiniciar la rama de trabajo desde `main` al empezar cada bloque
  (`git fetch origin main && git checkout -B <rama> origin/main`), implementar,
  `git push -u origin <rama>`, abrir PR a `main` y mergear. Tras el merge, actualizar la
  ref de la rama a main y pushear (evita el aviso de commits sin pushear).
- **Enlaces GitHub (para pasar revisiones a GLM 5.2 / Gemini):**
  - Repo: `https://github.com/GC052002/open-iiot-platform`
  - Archivo en main: `https://github.com/GC052002/open-iiot-platform/blob/main/<ruta>`
  - Árbol: `https://github.com/GC052002/open-iiot-platform/tree/main/<carpeta>`
  - Diff de un PR: `https://github.com/GC052002/open-iiot-platform/pull/<N>/files`
  - Diseño Fase 4: `.../blob/main/docs/PHASE4_DESIGN.md`
  - GLM 5.2 abre enlaces de GitHub; a Gemini se le pasan los archivos/bundle descargados.

## Cómo correr / probar (Linux)

> **Python soportado: 3.11 – 3.13.** Python **3.14 no está soportado** todavía:
> cambia el manejo de anotaciones (PEP 649) y la última Pydantic (2.13.x) rompe al
> importar (R7, `pyproject.toml` fija `requires-python = ">=3.11,<3.14"`; el install
> falla claro en vez de dar un 500 en runtime). En Windows, instala Python 3.13
> (python.org) y usa `py -3.13 -m venv .venv`.

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
- `logic/` (F3.4) — `LogicEngine` (suscriptor delta; publica tags derivados `input`→
  `output`) + `strategies` (scale/avg/deadband puras + `expr` en sandbox **asteval**).
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

## Próximo paso: probar el sistema completo, luego Fase 4/5

- **Fase 3 COMPLETA** (F3.0–F3.4). El frontend visual funciona end-to-end: diseñar →
  enviar al backend → ver datos en vivo → lógica derivada → import/export.
- **`LogicNode`** ✅ en `backend/app/logic/` (`LogicEngine` + estrategias + sandbox
  asteval). El motor publica tags derivados (`input`→`output`). WASM/Python real diferido.
- **Siguiente** ← **probar el sistema completo** en Windows con **Python 3.13** (recorrido
  diseñar→enviar→vivo→logic→export). Después: **Fase 4** (cloud-native: Redis, ABAC/Casbin,
  Vault, TimescaleDB, OTel) o **Fase 5** (empaquetado/despliegue por modo de red).
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
