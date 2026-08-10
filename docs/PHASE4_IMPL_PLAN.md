# Fase 4 — Plan de implementación (ejecutar en el chat nuevo)

> Objetivo: completar la Fase 4 en **3 lotes** con tests verdes, minimizando tokens sin
> bajar calidad. El **diseño** está cerrado en `docs/PHASE4_DESIGN.md` (leer §8 Rev D1).
> Este documento es la **guía de ejecución**: sigue el orden y las checklists.

## Estrategia de coste (leer primero)

- **3 merges, no 7.** Agrupa así: **Lote A** (backend identidad+permisos+secretos+
  publicación), **Lote B** (frontend gestión + visor cliente), **Lote C** (reportes +
  egress). Cada lote es un PR autocontenido y **revisable por sí solo**.
- **Verificar con tests** (pytest/vitest), no con demos. **Una sola** captura e2e al
  final del Lote B (login → gestor → editor → visor cliente). Nada de screenshots por
  sub-fase.
- **Reusar patrones**: `storage/repository.py` (Repository), `alarms/notifier.py`
  (`QueuedNotifier` para el egress), `security/auth.py` (dependencias FastAPI).
- **Docs al final** de cada lote (una actualización de REVIEW_TASKS/CONTINUATION por
  lote, no por sub-fase).
- Python 3.11–3.13. Backend hoy: 113 tests. Frontend: 66 tests.

---

## LOTE A — Backend: identidad + permisos + secretos + publicación

Cubre F4.0 + F4.1 + F4.1c + F4.1b (parte backend). **Sin tocar frontend todavía.**

### A1. Persistencia de configuración (nuevo `storage/config_repository.py`)
SQLite separado del historiador: `iiot_config.db` (env `IIOT_CONFIG_DB`, default). Tablas:
- `users(username PK, password_hash, salt, role_global, active INT, created_at)`
  — `role_global ∈ {admin, engineer, client}`.
- `projects(project_id PK, name, owner, schema_json TEXT, delivery_version INT DEFAULT 0, updated_at)`
- `project_members(project_id, username, role_proj, PRIMARY KEY(project_id, username))`
  — `role_proj ∈ {owner, editor, operator, viewer}`.
- `project_versions(project_id, version INT, schema_json TEXT, published_at, PRIMARY KEY(project_id, version))`
- `secrets(credential_id PK, ciphertext TEXT, created_at)` — Fernet con **KEK de instancia**.
- Interfaz abstracta `ConfigRepository` + impl `SQLiteConfigRepository` (mismo estilo WAL
  que `SQLiteHistorian`). Métodos: users CRUD, projects upsert/get/list, members add/
  remove/list, versions add/get, secrets put/get.

### A2. User store DB-backed (`security/user_store.py`)
- Sustituir el store por-env por uno respaldado en `ConfigRepository`.
- **Bootstrap**: si `users` está vacía y hay `IIOT_USERS`/`IIOT_BOOTSTRAP_ADMIN`, sembrar
  un admin una vez. Mantener PBKDF2 (`rbac.py`) y tokens Fernet (`auth.py`).

### A3. Autorización por proyecto (`security/authz.py`)
- `project_role(username, project_id) -> role_proj | None` (admin global → "owner").
- Dependencia FastAPI `require_project(perm)` que **extrae `project_id`** de path/query/
  body y verifica el rol. Permisos: `read`(viewer+), `operate`(operator+, = write de
  setpoints), `edit`(editor+), `manage`(owner/admin).
- **WS**: en el handshake, cachear en el cliente un dict `{project_id: role}` (o resolver
  on-demand y cachear). `subscribe` exige `read`; `write` exige `operate`.

### A4. Secretos (`security/secrets.py`)
- KEK de instancia: `IIOT_FERNET_KEY` ya existe → derivar/usar para cifrar `secrets`.
- `put_secret(credential_id, plaintext)`, `resolve_secret(credential_id) -> str|None`.
- Los drivers resuelven config del tipo `{"password": {"$secret": "<credential_id>"}}` en
  `state.start_project` (antes de instanciar el driver). El JSON del proyecto **nunca**
  guarda la contraseña en claro.

### A5. API (extender `api/__init__.py`)
- Usuarios (admin): `POST/GET/PATCH/DELETE /users`.
- Proyectos: `GET /projects` **filtra por membresía**; `GET/POST /projects` y edición
  gated por `require_project`. **Persistir** el proyecto en `POST /projects` y **cargar
  los persistidos al `startup`** (arrancar runtimes).
- Miembros: `GET/POST /projects/{id}/members`, `DELETE /projects/{id}/members/{u}` (manage).
- Publicación: `POST /projects/{id}/publish` → snapshot de `schema_json` en
  `project_versions` + `delivery_version++` (F4.1b). `GET /projects/{id}/versions`.
- Secretos: `POST /secrets` (manage). Todo **auditado** (`state.audit`).

### A6. Wiring (`state.py`, `main.py`)
- `AppState` recibe `ConfigRepository`; en `startup` carga usuarios y proyectos
  persistidos. `main.ws_endpoint` cachea roles por proyecto en el handshake.

### A7. Tests (nuevo `tests/test_f40_identity.py`, `tests/test_f41_authz.py`)
- Users CRUD + bootstrap + hashing.
- `project_role`/`require_project`: **denegar acceso cruzado** (engineer de A no escribe
  en B); operator no puede `edit`; viewer no puede `operate`.
- Persistencia/recarga de proyectos; membresías; publish crea versión; secreto se cifra y
  `resolve_secret` lo recupera; `$secret` se resuelve en `start_project`.
- **Meta: backend ≥ ~135 tests.** `ruff` limpio.

> **Merge Lote A** (PR): "F4.0/F4.1/F4.1c — identidad, permisos por proyecto y secretos".

---

## LOTE B — Frontend: gestión + visor del cliente

Cubre F4.0-UI + F4.1-UI + F4.2. Reusar el `rest.ts` (añadir endpoints) y stores.

### B1. Login real + sesión
- `LoginBar` ya existe; conectar a `/login` real; guardar token (ya) + `role_global`.
- Si `role_global === client` o el rol de proyecto es `operator` → entrar directo al
  **visor**, no al editor (modo Runtime).

### B2. Gestión de usuarios (admin) — `components/UsersPanel.tsx`
- Crear/listar/desactivar usuarios (`/users`). Solo visible para `admin`.

### B3. Gestor de proyectos — `components/ProjectsPanel.tsx`
- Listar `/projects` (ya filtrado por backend), **abrir** uno en el editor
  (`GET /projects/{id}` → `loadGraph`), ver/gestionar **miembros** (`/members`),
  botón **Publicar** (`/publish`).

### B4. Visor HMI del cliente (responsive) — `views/Viewer.tsx` (+ ruta)
- Router simple por rol/hash (`#/edit` vs `#/view`) o query. Modo **Runtime**:
  canvas **solo-lectura** (React Flow `nodesDraggable={false}` etc., sin paleta ni
  toolbar de edición), widgets en vivo.
- **Setpoints**: tags con flag `writable` (añadir en el editor de Tags) → el visor
  muestra un control (input/slider/toggle) que llama `connection.write` (ya existe;
  backend gatea con `operate`). Responsive (mobile-first, 1 columna).
- Export snapshot/histórico (CSV/JSON) — reutiliza `/history`.

### B5. Tests (vitest) + build
- UsersPanel/ProjectsPanel render + acciones (fetch mock). Viewer: modo solo-lectura,
  control de setpoint dispara write. `tsc` + `vite build` limpios.
- **Una** verificación e2e Playwright al final: login → gestor → abrir editor → publicar
  → abrir visor → cambiar un setpoint. (1 captura.)

> **Merge Lote B** (PR): "F4.2 — gestión de usuarios/proyectos + visor del cliente".

---

## LOTE C — Reportes + Egress

Cubre F4.3 + F4.4.

### C1. Reportes (backend `api` + `storage`)
- `GET /reports?project_id&tag_id&from&to&bucket=hour|day|month&agg=avg|sum|min|max|last`.
- **Consumo** para contadores: `last-first` en la ventana con manejo de reinicios
  (suma de incrementos positivos). Query SQL sobre el historiador (índice `(project_id,
  tag_id, ts)` ya existe).
- Gated por `require_project("read")`. Tests de agregación/consumo con datos sembrados.

### C2. Egress a terceros (nuevo `egress/forwarder.py`)
- `ProjectForwarder` = suscriptor **delta** (o raw) del TagCache, config por proyecto:
  `{enabled, protocol: http|mqtt|file, endpoint, format: json|csv, interval_s, tags[], headers/auth}`.
- **Patrón `QueuedNotifier`**: cola acotada + batch por `interval_s` + backoff; async,
  **nunca bloquea el motor**. HTTP con `httpx.AsyncClient`; MQTT con `aiomqtt` (import
  perezoso); file/CSV append. Registrar/desregistrar por proyecto en `state`.
- Config guardada en `projects.schema_json` (campo `egress`) o tabla aparte; gated
  `manage`. Tests: batching, backoff con endpoint mock, formato JSON/CSV.

### C3. Frontend
- Vista de **reportes** (tabla + export CSV) y **config de egress** (form en ajustes del
  proyecto). Tests de render.

> **Merge Lote C** (PR): "F4.3/F4.4 — reportes de consumo + egress a terceros".

---

## Cierre de la Fase 4

- Actualizar `REVIEW_TASKS.md` (entradas F4.0–F4.4), `ROADMAP.md` (marcar completas),
  `CONTINUATION.md` (estado + siguiente), `ARCHITECTURE.md` si cambió algo estructural.
- Preparar `docs/F4_REVIEW_REQUEST.md` + bundle para GLM/Gemini (como en F3).
- **Si el presupuesto aprieta:** el orden por lotes garantiza que **lo mergeado ya es
  coherente y revisable**. Prioridad: Lote A (núcleo de seguridad) > Lote B (producto
  visible) > Lote C (valor añadido). Deja para un 2º chat solo lo que no entre, dejando
  cada lote cerrado y verde.
