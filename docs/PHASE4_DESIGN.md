# Fase 4 — Diseño: Plataforma multiusuario y entrega a cliente

> **Estado:** propuesta de diseño (cerrar antes de codificar, ROADMAP §0.1).
> **Autor:** Opus, a partir de los requisitos del creador (GC052002).
> **Para revisar:** GLM 5.2 y Gemini (revisión de **diseño**, no de código todavía).

## 0. Objetivo

Pasar de un "editor de proyectos" (Fase 3, ya funcional) a una **plataforma
multiusuario** donde:

- Tú y tus programadores **crean/editan/ven** proyectos con **permisos por proyecto**.
- Un proyecto se **entrega a un cliente**, que recibe una **cuenta única (editor)** y
  una **"ventana" (visor HMI responsive)** para operar: cambiar setpoints permitidos,
  ver estadísticas/consumo y exportar datos.
- El sistema **guarda registros históricos** (mensuales, consumo) y puede **reenviar
  datos a un tercero** (JSON/MQTT/CSV) en tiempo casi real.
- El creador hace **backup del proyecto antes de entregar**; tras la entrega, los
  cambios del cliente quedan bajo su responsabilidad.

Esto concreta el "F4 — Escalado/multi-tenant/hardening" del ROADMAP (ABAC §10.2) y lo
reorienta a las necesidades reales de producto.

## 1. Qué ya existe (no rehacer)

| Pieza | Dónde | Reutilizamos para |
|---|---|---|
| RBAC (roles, PBKDF2, `can()`) | `security/rbac.py` | base de permisos |
| Login + token firmado (Fernet) | `security/auth.py`, `POST /login` | autenticación |
| Multi-tenant por `project_id` | `state.py`, TagCache segmentado | aislamiento de datos |
| Historiador (series + `audit`) | `storage/` + `/history`, `/audit` | registros, reportes, auditoría |
| Repository abstracto (SQLite hoy, Postgres luego) | `storage/repository.py` | persistir usuarios/proyectos |
| Export/Import JSON del proyecto | `editor/projectIO.ts` (F3.3) | **backup antes de entregar** |
| Escritura de setpoints + audit | WS `WriteMsg`, `_handle_write` | "cambiar parámetros" del cliente |
| Suscriptores del TagCache (delta/raw) | `engine/tag_cache.py` | **egress a terceros** (nuevo sink) |

## 2. Qué es nuevo (alcance de F4)

### 2.1 Modelo de identidad y permisos (F4.0 + F4.1)

**Usuarios persistidos** (hoy vienen de la env `IIOT_USERS`):
- Tabla `users(username PK, password_hash, role_global, active, created_at)`.
  `role_global`: `admin` (superusuario) · `engineer` (crea proyectos) · `client`.
- Bootstrap: si la tabla está vacía, se siembra un admin desde env (una sola vez).
- Hashing PBKDF2 (ya en `rbac.py`); tokens Fernet (ya).

**Propiedad y compartición por proyecto** (ABAC ligero, sin Casbin todavía):
- Persistir el proyecto: `projects(project_id PK, name, owner, schema_json, updated_at)`.
  (Hoy el proyecto solo vive en memoria; para compartir/entregar debe persistirse y
  cargarse al arrancar.)
- `project_members(project_id, username, role_proj)` con
  `role_proj ∈ {owner, editor, viewer, operator}`:
  - **owner**: control total del proyecto (incluye gestionar miembros).
  - **editor**: edita topología/lógica/HMI.
  - **operator** (= el **cliente**): NO edita el diseño; solo opera la "ventana"
    (cambiar setpoints permitidos, ver, exportar).
  - **viewer**: solo lectura.
- Resolución efectiva: `project_role(user, project_id)` → rol; `admin` global ve todo.
- **Aplicación server-side** en API (`/projects/*`) y WS (subscribe = viewer+; write =
  operator+/editor). Nunca se confía en el cliente.

> **Decisión:** tabla propia de miembros ahora (menos dependencias, air-gapped);
> Casbin (§10.2) solo si las políticas se vuelven complejas (multi-planta jerárquico).

### 2.2 Visor HMI del cliente — la "ventana" (F4.2)

- **Ruta/vista separada** del editor: HMI en modo operación (widgets en vivo), diseñada
  **responsive/móvil** (no el editor de 3 columnas).
- **Setpoints editables por el cliente**: el diseñador marca qué tags son `writable`
  (flag por tag) y qué widget los controla; el visor muestra un control (slider/toggle/
  input) que envía `WriteMsg` (gated por `operator+` + audit). El resto es solo lectura.
- **Export**: descargar el snapshot/histórico visible (CSV/JSON).

### 2.3 Reportes: registros mensuales y consumo (F4.3)

- El historiador ya guarda crudo. Añadir agregación:
  `GET /reports?project_id&tag_id&from&to&bucket=hour|day|month&agg=avg|sum|min|max|last`.
- **Consumo** (para tags contador): `delta = last - first` en la ventana, o suma de
  incrementos positivos (manejo de reinicios de contador).
- Frontend: vista de reportes + export CSV. Eficiente en SQLite para rangos moderados;
  TimescaleDB (continuous aggregates) cuando escale.

### 2.4 Egress a terceros (F4.4)

- Un **forwarder** = suscriptor del TagCache (como el historiador/alarmas) que **reenvía
  muestras hacia afuera** según config **por proyecto**:
  `{ enabled, protocol: http|mqtt|file, endpoint, format: json|csv, interval_s, tags[], auth }`.
- `interval_s` configurable (puede ser < 1s); **batch + cola acotada + backoff**
  (patrón `QueuedNotifier`), asíncrono, **nunca bloquea el motor**.
- Solo salida; credenciales por env/secreto; TLS para HTTP/MQTT.

> **Decisión:** el egress es **config de proyecto**, no un nodo del canvas (el canvas
> modela la ingesta y el HMI; el egress es infraestructura del proyecto).

### 2.5 Backup y entrega

- **Backup = Exportar** el proyecto JSON (ya existe) + opción de **exportar histórico**
  (CSV/JSON) → un "paquete de entrega".
- **Modelo de despliegue** (fork principal):
  - **A) Por cliente (recomendado OT):** exportas → despliegas una **instancia del
    cliente** (Docker) donde él tiene su cuenta `operator` y su "ventana". Aislado,
    air-gapped. Tras la entrega, sus cambios son suyos. La **plantilla maestra** se
    queda contigo.
  - **B) Central multi-tenant:** una instancia con todos los usuarios/clientes;
    `project_members` controla el acceso. Requiere Postgres + hardening (portal SaaS).
  - Ambos parten del **mismo core**; A se apoya en el empaquetado (Fase 5).

## 3. Persistencia

- Extender el patrón Repository: `UserRepository`, `ProjectRepository`,
  `MembershipRepository`. **SQLite ahora** (mismo estilo que el historiador, air-gapped);
  **PostgreSQL** cuando se active el modo central/nube (misma interfaz, otra impl.).
- `PROJECT_CONTEXT §2` ya prevé PostgreSQL (config) + Timescale (series); se faseará.

## 4. Sub-fases propuestas (cada una cierra verde y se mergea)

| Sub-fase | Entregable | Depende de |
|---|---|---|
| **F4.0** | Usuarios persistidos + API de gestión (`/users`) + UI de admin | — |
| **F4.1** | Proyectos persistidos + propiedad/miembros + permisos por proyecto (API+WS) | F4.0 |
| **F4.2** | Visor HMI responsive del cliente + setpoints `writable` + export | F4.1 |
| **F4.3** | Reportes (mensuales/consumo) + export CSV | F2.1 (historiador) |
| **F4.4** | Egress a terceros (HTTP/MQTT/CSV) | F4.1 |
| **F4.5** (opcional) | Empaquetado por cliente (Docker) = solapa con Fase 5 | F4.1 |

Orden recomendado: **F4.0 → F4.1** (identidad es la base) → luego F4.2/F4.3/F4.4 en el
orden que priorices.

## 5. Seguridad (transversal)

- Contraseñas PBKDF2; tokens Fernet con TTL; **fail-closed**.
- **Autorización por proyecto siempre en el servidor** (API y WS); el frontend solo
  oculta, no autoriza.
- **Audit** de todo lo sensible: alta/baja de usuarios, cambios de miembros/roles,
  escrituras de setpoint, exportaciones, cambios de config de egress.
- Egress: solo saliente, credenciales fuera del código, TLS.

## 6. Preguntas para los revisores (diseño)

1. **Roles por proyecto**: ¿`owner/editor/operator/viewer` son suficientes? ¿El
   "cliente" es exactamente `operator` (opera+exporta, no edita diseño)?
2. **ABAC**: ¿tabla propia ahora y Casbin solo si crece, o Casbin ya?
3. **Egress**: ¿config de proyecto (propuesto) o un `SinkNode` en el canvas?
4. **"Editable por cliente"**: ¿flag `writable` por **tag** (propuesto) o por widget?
5. **Persistencia**: ¿SQLite ahora → Postgres luego (propuesto), o Postgres ya?
6. **Despliegue**: ¿por-cliente (A, recomendado) o central multi-tenant (B)? Marca el
   alcance de F4.1 y de la Fase 5.
7. **Consumo**: para contadores, ¿`last-first` con manejo de reinicios, o suma de deltas
   positivos? ¿Algún estándar del sector que debamos seguir?

## 7. Fuera de alcance de F4 (diferido)

- Redis multi-worker (escala horizontal), Vault (rotación de secretos), Sparkplug B,
  tracing OpenTelemetry — quedan como **F4-infra** / Fase 5 según necesidad.
- WASM para `LogicNode` (Python real) — aislamiento definitivo de cómputo no-confiable.

---

## 8. Revisión de diseño D1 (GLM + Gemini) — decisiones integradas · 2026-08-09

El diseño se validó como correcto. Se integran **4 refinamientos** (obligatorios antes
de implementar) y se **cierran las 7 preguntas** con estas decisiones:

### 8.1 Refinamientos aceptados (BLOCKERS de diseño)

1. **Autorización server-side estricta por `project_id` (no confiar en el frontend).**
   - **Dependencia/middleware FastAPI** que extrae `project_id` (de path, query o body)
     y verifica el rol del usuario para ESE proyecto **en cada endpoint**. Sin esto, un
     `engineer` podría escribir en la entrega de otro cliente.
   - **WS:** verificar en el **handshake** y **cachear** `project_id` permitido + rol en
     la sesión del cliente (ya cacheamos rol en el handshake, Rev 12 — se extiende a
     `project_id`). `subscribe`/`write` se validan contra esa caché.
   - El frontend solo **oculta**; la autorización real es del backend.

2. **Plantilla → Publicación → Entrega = snapshot INMUTABLE + versionado.**
   - **Plantilla (Authoring):** editable, inestable, contra simuladores/PLCs de prueba.
     Vive en el entorno del integrador.
   - **Entrega (Delivery):** **instantánea inmutable y versionada** de la plantilla,
     contra PLCs de producción. El operador solo interactúa con la Entrega.
   - Actualizar = **"Publicar"** una nueva versión de la plantilla → **nueva instantánea**
     (nueva `delivery_version`). **Sin hot-reload de topología en producción.**
   - Migración al publicar: si cambia la topología, el `TagCache` del proyecto se
     reinicia; **el histórico se conserva** (tags borrados → datos huérfanos pero
     auditables). Campo `schema_version`/`delivery_version` gobierna la migración.

3. **Gestión de secretos: credenciales de PLC FUERA del JSON.**
   - El JSON (plantilla/entrega) **nunca** contiene contraseñas (S7/OPC UA/MQTT TLS).
     Referencia un **`credential_id`** (p. ej. `vault://plc_planta_a` o
     `secret://<id>`). El backend lo **resuelve en runtime** e inyecta en memoria.
   - Almacén: **Fernet con una KEK por cliente/instancia** ahora (extiende `crypto.py`,
     F2.4b); **Vault/SOPS** cuando se necesite rotación/centralización. Así el JSON de
     entrega se puede loguear/compartir sin riesgo.

4. **Air-gapped de verdad en la entrega.**
   - El build de producción del frontend **vendoriza todo** (sin CDNs/fuentes externas);
     el **backend sirve los estáticos**; **cero llamadas a APIs externas** desde el
     código del cliente. (Vite ya produce bundle autocontenido; se formaliza como regla
     y se verifica en Fase 5.)

### 8.2 Respuestas cerradas a las 7 preguntas

1. **Acceso multi-proyecto:** tabla de unión `user_project_roles(user_id, project_id,
   role)` (= nuestro `project_members`). `project_id` = **tenant id**; Runtime/TagCache
   ya aislados por proyecto (F2.0). ✅
2. **Plantilla vs Entrega:** Plantilla = editable/pruebas; Entrega = inmutable/versionada/
   producción, creada por un "commit" (publicación) de la plantilla. ✅ (ver 8.1.2)
3. **¿El operador necesita cuenta?** Sí, **mínima**: login atado a **un `project_id` de
   entrega** con rol `operator`; entra **directo a su entrega** (no ve lista de proyectos).
   Air-gapped: posible auth pasiva por IP/certificado de máquina.
4. **Evitar que el operador edite la topología:** frontend con **dos modos** —
   *Authoring* (paleta+inspector) vs *Runtime* (canvas solo-lectura, inspector muestra
   valores en vivo). **La seguridad real en el backend:** `POST /projects`/edición
   **rechaza** que un `operator` cambie topología.
5. **Credenciales de PLC:** referencia `credential_id`, resuelta en runtime (ver 8.1.3).
6. **Métricas y alarmas:** `/metrics` Prometheus = **global de infraestructura** (no por
   proyecto); **alarmas aisladas por `project_id`** (ya, F2.4a); **notificadores por
   proyecto**, no globales.
7. **Versionado de entregas:** publicar nueva versión → migración de estado; topología
   nueva → reset del TagCache del proyecto; **histórico conservado** (tags borrados →
   huérfanos pero auditables); `delivery_version` gobierna la migración.

### 8.3 Ajuste de sub-fases (tras D1)

- **F4.0** — Usuarios persistidos + `/users` + UI admin. *(sin cambios)*
- **F4.1** — Proyectos **persistidos** + `user_project_roles` + **middleware de
  autorización por `project_id`** (REST+WS). Incluye el rechazo server-side de edición
  por `operator`.
- **F4.1b (nuevo)** — **Publicación Plantilla→Entrega**: snapshot inmutable +
  `delivery_version` + migración (reset TagCache, histórico conservado).
- **F4.2** — Visor del cliente: **modo Runtime** (solo-lectura) + setpoints `writable` +
  export. *(el modo Authoring/Runtime se decide por rol)*
- **F4.1c (nuevo, seguridad)** — **`credential_id` + KEK Fernet por instancia**: sacar
  las credenciales del JSON. *Prerrequisito para cualquier entrega real.*
- **F4.3** Reportes · **F4.4** Egress (config por proyecto; notificadores por proyecto).

**Orden recomendado (post-D1):** F4.0 → F4.1 (+middleware) → **F4.1c (secretos)** →
F4.1b (publicación) → F4.2 → F4.3/F4.4. La autorización estricta y la gestión de
secretos son **prerrequisitos** de una entrega comercial.

**Diseño CERRADO para implementar.**
